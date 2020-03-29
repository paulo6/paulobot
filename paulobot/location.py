
import paulobot.sport

class Area:
    def __init__(self, location, name, desc, size=1):
        self.location = location
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

    def __str__(self):
        return self.name

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

    def add_to_rolling(self, game):
        if game not in self._rolling:
            self._rolling.append(game)

    def remove_from_rolling(self, game):
        if game not in self._rolling:
            self._rolling.remove(game)

    def queue_index(self, game):
        if game in self._queue:
            return self._queue.index(game)
        return None

    def game_rolled(self, game, result):
        if game in self._rolling:
            self._rolling.remove(game)
        self._in_progress.append(result)


class Location:
    def __init__(self, pb, name, room):
        self._pb = pb
        self.name = name
        self.room = room
        self.sports = {}
        self.areas = {}
        self.users = set()

    def __str__(self):
        return self.name

    def add_user(self, user):
        for sport in self.sports.values():
            sport.create_player(user)

        if user not in self.users:
            self.users.add(user)
            user.locations.add(self)


class LocationManager:
    def __init__(self, pb):
        self._pb = pb
        self.locations = {}
        self._load_config()

    def get_room_location(self, room):
        locs = [l for l in self.locations.values()
                  if l.room.id == room.id]
        if locs:
            return locs[0]
        return None

    def add_user_to_locations(self, user):
        # Check to see whether this user is already in rooms associated with
        # locations
        for loc in (l for l in self.locations.values() if l.room):
            users = self._pb.get_room_users(loc.room)
            if user in users:
                loc.add_user(user)


    def _get_null_area(self, loc):
        if None not in loc.areas:
            loc.areas[None] = Area(None, None, 0)
        return loc.areas[None]

    def _load_config(self):
        for c_loc in self._pb.config.locations:
            if c_loc.room:
                room = self._pb.lookup_room(c_loc.room)
            else:
                room = None
            loc = Location(self._pb, c_loc.name, room)
            self.locations[loc.name] = loc

            for c_area in c_loc.areas:
                area = Area(loc,
                            c_area.name,
                            c_area.desc,
                            c_area.size)
                loc.areas[area.name] = area

            for c_sport in c_loc.sports:
                if c_sport.area is None:
                    area = self._get_null_area(loc)
                else:
                    area = loc.areas[c_sport.area]

                sport = paulobot.sport.Sport(
                    self._pb,
                    loc,
                    c_sport.name,
                    c_sport.desc,
                    area,
                    c_sport.team_size)
                loc.sports[sport.name] = sport


