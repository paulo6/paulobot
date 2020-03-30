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


class Sport:
    """
    Represents an office sport.

    """
    def __init__(self, pb, location, name, desc, area, team_size,
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

            has_scores: Is this a mode where scores are to be
            recorded

            allow_draws: Are draws allowed?

        """
        self.location = location
        self.name = name
        self.desc = desc
        self.team_size = team_size
        self.has_scores = has_scores
        self.area = area
        # Players keyed by User object
        self.players = {}
        self._game_manager = GameManager(pb, self)

    @property
    def tag(self):
        return f"[{self.name.upper()}]"

    @property
    def max_players(self):
        """
        The maximum number of players in a game.
        
        """
        return self.team_size * 2

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