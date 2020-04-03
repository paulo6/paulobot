import functools

import paulobot.skill
from paulobot.game import GameManager


class Player(paulobot.skill.Player):
    """
    Represents a player for a given sport.

    """
    def __init__(self, sport, user):
        self.sport = sport
        self.user = user

    def __repr__(self):
        return f"<Player({self.sport}, {self.user})>"

    def __hash__(self):
        return hash(self.user)


@functools.total_ordering
class Sport:
    """
    Represents an office sport.

    """
    def __init__(self, pb, location, name, desc, area,
                 team_size, team_count, min_players=None,
                 has_scores=True, allow_draws=False):
        """
        Initialize the office sport.

        Args:
            pb: Main PauloBot instance

            location: The location of this sport

            name: The sport name

            desc: The sport description

            area: The playing area for this sport

            team_size: How many players are in a team

            team_count: Number of team (currently only 1 or 2)

            is_flexible: flexible number of players?

            has_scores: Is this a mode where scores are to be
            recorded

            allow_draws: Are draws allowed?

        """
        self.location = location
        self.name = name
        self.desc = desc
        self.team_size = team_size
        self.team_count = team_count
        self._min_players = min_players
        self.has_scores = has_scores
        self.area = area
        # Players keyed by User object
        self.players = {}
        self._game_manager = GameManager(pb, self)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        self == other

    def __lt__(self, other):
        return self.name < other.name

    @property
    def tag(self):
        return f"[{self.name.upper()}]"

    @property
    def is_flexible(self):
        return self.max_players == 0 or (self.min_players is not None and
                                         self.min_players < self.max_players)

    @property
    def min_players(self):
        if self._min_players is not None:
            return self._min_players
        if self.max_players == 0:
            return 1
        return None

    @property
    def max_players(self):
        """
        The maximum number of players in a game.

        """
        return self.team_size * self.team_count

    @property
    def games(self):
        """
        List of games sorted by gtime, then create time.
        """
        return sorted(self._game_manager.yield_games(),
                      key=lambda g: (g.gtime, g.created_time))

    def game_register(self, user, gtime):
        """
        Register the user for game at the supplied GTime.

        """
        self._game_manager.register(gtime,
                                    self.players[user])

    def game_unregister(self, user, gtime):
        """
        Unregister the user for game at the supplied GTime.

        """
        self._game_manager.unregister(gtime,
                                      self.players[user])

    def game_set_ready_mark(self, user, gtime, mark):
        """
        Set ready mark for game at the supplied GTime.

        """
        self._game_manager.set_ready_mark(gtime,
                                          self.players[user],
                                          mark)

    def get_next_game(self):
        """
        Get the next game.

        """
        return self._game_manager.get_next_game()

    def create_player(self, user):
        """
        Create a player for this sport for the supplied user.

        """
        if user not in self.players:
            self.players[user] = Player(self, user)

    def announce(self, message):
        """
        Announce a message in the room associated with this sport.

        """
        if self.location.room:
            self.location.room.send_msg(f"{self.tag} {message}")

    def restore_game(self, rec):
        self._game_manager.restore_record(rec)
