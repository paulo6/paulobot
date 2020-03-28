class Sport:
    def __init__(self, name, desc, has_scores, area):
        self.name = name
        self.desc = desc
        self.has_scores = has_scores
        self.area = area


class Area:
    def __init__(self, name, desc, size=1):
        self.name = name
        self.desc = desc
        self.size = size
        self.sports = []

        # Queue of waiting games
        self._queue = []

        # Games that are currently rolling in this area
        self._rolling = []

        # Results for games that are in progress
        self._in_progress = []

        # Manual busy details
        self._manual_busy = None

    def is_busy(self, game=None):
        # If there's a hold then it's busy!
        if self._manual_busy is not None:
            return True

        # If this game is in the rolling queue, then it isn't
        # busy for this game
        if game in self._rolling:
            return False

        # If there is a queue, then will need to wait for
        # those games first
        if self._queue:
            return True

        # See whether there is space for a game to roll
        return len(self._in_progress) + len(self._rolling) >= self.size

    def add_to_queue(self, game):
        if game not in self._queue:
            self._queue.append(game)

    def remove_from_queue(self, game):
        if game in self._queue:
            self._queue.remove(game)

    def game_rolled(self, game, result):
        if game in self._rolling:
            self._rolling.remove(game)
        self._in_progress.append(result)


class Location:
    def __init__(self, pb, name):
        self._pb = pb
        self.name = name
        self.sports = {}
        self.areas = {}


class LocationManager:
    def __init__(self, pb):
        self._pb = pb
        self.locations = {}

    def get_user_locations(self, user):
        return []
    