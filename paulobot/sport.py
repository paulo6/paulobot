import paulobot.skill

from paulobot.game import GameManager


class Player(paulobot.skill.Player):
    def __init__(self, user):
        self.user = user

    def __repr__(self):
        return f"<Player({self.user})>"


class Sport:
    def __init__(self, location, name, desc, area, team_size,
                has_scores=True, allow_draws=False):
        self.location = location
        self.name = name
        self.desc = desc
        self.team_size = team_size
        self.has_scores = has_scores
        self.area = area
        # Players keyed by User object
        self.players = {}
        self._game_manager = GameManager(self)

    @property
    def max_players(self):
        return self.team_size * 2

    def game_register(self, user, time):
        self._game_manager.register(time,
                                    self.players[user])

    def game_unregister(self, user, time):
        self._game_manager.unregister(time,
                                    self.players[user])

    def create_player(self, user):
        if user.email not in self.players:
            self.players[user] = Player(user)

    def announce(self, message):
        if self.location.room:
            self.location.room.send_msg(f"[{self.name.upper()}]: {message}")