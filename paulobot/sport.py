import paulobot.skill

from paulobot.game import GameManager


class Player(paulobot.skill.Player):
    def __init__(self, user):
        self.user = user


class Sport:
    def __init__(self, location, name, desc, area,
                has_scores=True, allow_draws=False):
        self.location = location
        self.name = name
        self.desc = desc
        self.has_scores = has_scores
        self.area = area
        self.players = {}
        self._game_manager = GameManager(self)

    def game_register(self, time, user):
        self._game_manager.register(time,
                                    self.players[user.email])

    def create_player(self, user):
        if user.email not in self.players:
            self.players[user.email] = Player(user)

    def announce(self, message):
        if self.location.room:
            self.location.room.send_msg(f"[{self.name}]: {message}")