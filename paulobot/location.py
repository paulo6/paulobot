
import paulobot.sport

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
    def __init__(self, pb, name, room):
        self._pb = pb
        self.name = name
        self.room = room
        self.sports = {}
        self.areas = {}


class LocationManager:
    def __init__(self, pb):
        self._pb = pb
        self.locations = {}
        self._load_config(pb.config.data.get("locations", []))

    def get_user_locations(self, user):
        return []

    def get_room_location(self, room):
        locs = [l for l in self.locations.values()
                  if l.room.id == room.id]
        if locs:
            return locs[0]
        return None

    def _get_null_area(self, loc):
        if None not in loc.areas:
            loc.areas[None] = Area(None, None, 0)
        return loc.areas[None]

    def _load_config(self, c_locations):
        for c_loc in c_locations:
            if "room" in c_loc:
                room = self._pb.lookup_room(c_loc["room"])
            else:
                room = None
            loc = Location(self._pb, c_loc["name"], room)
            self.locations[loc.name] = loc

            for c_area in c_loc.get("areas", []):
                area = Area(c_area["name"],
                            c_area.get("description", ""),
                            c_area.get("size", 1))
                loc.areas[area.name] = area

            for c_sport in c_loc.get("sports", []):
                if "area" not in c_sport:
                    area = self._get_null_area(loc)
                else:
                    area = loc.areas[c_sport["area"]]

                sport = paulobot.sport.Sport(
                    loc,
                    c_sport["name"],
                    "",
                    area,
                    c_sport["players"])


    