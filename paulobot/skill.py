import itertools
import trueskill
import logging
import mpmath
import math

LOGGER = logging.getLogger(__name__)

# Set the mpmath precision (default 15)
PRECISION = 25
mpmath.mp.dps = PRECISION

# Flag indicating whether skill module is enabled
ENABLED = True

# Flag indicating whether we are using mode that takes into account points
POINTS_MODE_ENABLED = False

# Default draw chance
DEFAULT_DRAW_CHANCE = 0.4


def _get_perms(options, team_size):
    def _results(fixed, poss):
        for rest in itertools.combinations(poss, team_size-1):
            team1 = set(rest)
            team2 = poss - team1
            team1.add(fixed)
            yield (team1, team2)
    options = set(options)
    while len(options) >= 2*team_size:
        fixed = options.pop()
        return (i for i in _results(fixed, options))


def team_permutations(*players):
    """Return all possible unique team1 v team2 permutations. """
    # For 1v1 and 2v2, use hardcoded method for speed
    if len(players) == 2:
        return [((players[0],), (players[1],))]
    elif len(players) == 4:
        matchups = (
            ((0, 1), (2, 3)),
            ((0, 2), (1, 3)),
            ((0, 3), (1, 2)),
        )
        return [((players[p1], players[p2]), (players[p3], players[p4]))
                for (p1, p2), (p3, p4) in matchups]
    elif len(players) == 8:
        return _get_perms(players, 4)
    else:
        raise Exception("Unsupported number of players {}"
                        .format(len(players)))


class Player(object):
    """Wraps a trueskill rating object."""
    def __init__(self, model, rating_string=None, rating_tuple=None):
        self._model = model
        if rating_string is not None:
            mu, sigma = rating_string.split(",")
            self.rating = self._model._env.create_rating(mu=float(mu),
                                             sigma=float(sigma))
        elif rating_tuple is not None:
            mu, sigma = rating_tuple
            self.rating = self._model._env.create_rating(mu=mu, sigma=sigma)
        else:
            self.rating = self._model._env.create_rating()

    def get_rating_string(self):
        return "{:.{}f},{:.{}f}".format(self.rating.mu, PRECISION,
                                        self.rating.sigma, PRECISION)

    def get_skill(self):
        return self._model._env.expose(self.rating)

    def reset_rating(self, values=None):
        self.rating = self._model._env.create_rating()


class Model(object):
    def __init__(self, allow_draws=False):
        if not ENABLED:
            self._env = _DummyEnv()
            LOGGER.info("Skill module disabled")
        elif allow_draws:
            self._env = trueskill.TrueSkill(
                draw_probability=DEFAULT_DRAW_CHANCE,
                backend='mpmath')
            LOGGER.info("Created 'draws' model with %s backend, dps %s",
                        self._env.backend, mpmath.mp.dps)
        else:
            self._env = trueskill.TrueSkill(draw_probability=0.0,
                                            backend='mpmath')
            LOGGER.info("Created 'normal' model with %s backend, dps %s",
                        self._env.backend, mpmath.mp.dps)

    def _rate(self, player_groups, ratings, *args, **kwargs):
        """
        Version of trueskill rate() function for use with PlayerRating.

        Note that this modifies the state of the Rating objects to reflect
        their new rating.

        """
        rgroups = [[p.rating for p in group]
                   for group in player_groups]
        new_ratings = self._env.rate(rgroups, ratings, *args, **kwargs)
        # Since the players and ratings variables are lists of lists, let's
        # convert them to a 'flat' list to make iteration easier.
        flat_players = list(itertools.chain.from_iterable(player_groups))
        flat_ratings = list(itertools.chain.from_iterable(new_ratings))
        for player, rating in zip(flat_players, flat_ratings):
            player.rating = rating
            LOGGER.debug("{} -- {}".format(str(player), rating))


    def _quality_env(self, player_groups, *args, **kwargs):
        """
        Wrapper around the builtin quality method.

        """
        rgroups = [[p.rating for p in group]
                   for group in player_groups]
        return self._env.quality(rgroups, *args, **kwargs)


    def _quality_fast(self, player_groups):
        """
        The Trueskill module's quality method can be slow, as it uses matrices to
        handle the >2 team possiblity. We only ever have 2 teams, so can
        simplify.

        This formula is taken from
        http://research.microsoft.com/pubs/74419/TR-2006-80.pdf equation 4.1

        """
        # Only works for 2 player groups
        team1, team2 = player_groups
        f = 2 * len(team1)

        bs = self._env.beta ** 2
        s = (sum(p.rating.sigma ** 2 for p in team1)
             + sum(p.rating.sigma ** 2 for p in team2))

        mu1 = sum(p.rating.mu for p in team1)
        mu2 = sum(p.rating.mu for p in team2)

        return (math.sqrt(f * bs / (f * bs + s))
                * math.exp( -(mu1 - mu2)**2 / (2. * (f * bs + s))))


    def quality(self, player_groups):
        return self._quality_fast(player_groups)


    def record_match(self, team1, team2, score1, score2):
        """
        Record a match between players and update their rating.

        Arguments are named/based off the results string:
        'ttd result player1 player2 vs player3 player4 score1-score2'

        """
        # Normal mode, just record score.
        # Else experimental take into account games points.
        if not POINTS_MODE_ENABLED:
            # Lower rating is better, so take negative of scores
            self._rate([team1, team2], [-score1, -score2])
        else:
            if score1 < score2:
                winner = team2, score2
                loser = team1, score1
            else:
                winner = team1, score1
                loser = team2, score2

            # Record losing player's wins first, remembering that 2nd argument is
            # game placement not score
            for _ in range(loser[1]):
                self._rate([winner[0], loser[0]], [2, 1])
            for _ in range(winner[1]):
                self._rate([winner[0], loser[0]], [1, 2])


    def best_matchup(self, *players):
        """Construct the 'fairest' matchup of teams."""

        best_quality = 0

        # If there are 'exactly' equal best matches, one of them will be picked
        # arbitrarily...
        best_match = None
        for team1, team2 in team_permutations(*players):
            q = self.quality([team1, team2])
            if q > best_quality:
                best_quality = q
                best_match = (team1, team2)
            # As noted above, ignore the quality in the same case
            # This means we don't have to care about "equivalent" permutations

        return best_quality, best_match


    def win_probability(self, team1, team2):
        """
        Calculate win probablility using
           https://github.com/sublee/trueskill/issues/1#issuecomment-149762508
           http://stackoverflow.com/a/28035456

        """
        delta_mu = (sum([x.rating.mu for x in team1])
                    - sum([x.rating.mu for x in team2]))
        denom = math.sqrt(2 * len(team1) * (self._env.beta ** 2)
                          + sum([x.rating.sigma**2 for x in team1])
                          + sum([x.rating.sigma**2 for x in team2]))
        return self._env.cdf(delta_mu / denom)


class _DummyRating(object):
    def __init__(self):
        self.mu = 0
        self.sigma = 0


class _DummyEnv(object):
    def create_rating(self, *args, **kwargs):
        return _DummyRating()

    def expose(self, *args, **kwargs):
        return 0


# Create models
DEFAULT_MODEL = Model()
DRAW_MODEL = Model(allow_draws=True)
