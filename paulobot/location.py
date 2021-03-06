import logging
import functools

import paulobot.sport
import paulobot.database
import paulobot.game

from paulobot import templates

LOGGER = logging.getLogger(__name__)

@functools.total_ordering
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

        # Manual busy details
        self._manual_busy = None

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self == other

    def __lt__(self, other):
        return self.name < other.name

    @property
    def tag(self):
        return f"<{self.name.upper()}>"

    @property
    def queue_len(self):
        return len(self._queue)

    @property
    def is_null(self):
        return self.name is None

    @property
    def rolling_games(self):
        return self._rolling

    @property
    def game_queue(self):
        return self._queue

    @property
    def in_progress_results(self):
        # @@@ Should probably just store results in the stats
        # class, and this function can go round the sports
        # querying them for their pending results (filtering
        # out ones older than the cut-off)
        return []

    @property
    def pretty(self):
        return templates.area.area_string(self)

    @property
    def pretty_for_direct(self):
        return templates.area.area_string(self, is_direct=True)

    def is_busy(self, game=None):
        # If there's a hold then it's busy!
        if self._manual_busy is not None:
            return True

        # If the area size is 0, then unlimited size!
        if self.size == 0:
            return False

        # If this game is in the rolling queue, then it isn't
        # busy for this game
        if game in self._rolling:
            return False

        # If there is a queue, then will need to wait for
        # those games first
        if self._queue:
            return True

        # See whether there is space for a game to roll
        return len(self.in_progress_results) + len(self._rolling) >= self.size

    def add_to_queue(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game not in self._queue:
            self._queue.append(game)

    def remove_from_queue(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game in self._queue:
            self._queue.remove(game)

    def queue_index(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game in self._queue:
            return self._queue.index(game)
        return None

    def add_to_rolling(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game not in self._rolling:
            self._rolling.append(game)

    def remove_from_rolling(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game in self._rolling:
            self._rolling.remove(game)

    def game_rolled(self, game):
        assert isinstance(game, paulobot.game.Game)
        if game in self._rolling:
            self._rolling.remove(game)
        if game in self._queue:
            self._queue.remove(game)

    def announce(self, message):
        """
        Announce a message in the room associated with this area.

        """
        if self.location.room:
            self.location.room.send_msg(f"{self.tag} {message}")


class Location:
    def __init__(self, pb, name, desc, room):
        self._pb = pb
        self.name = name
        self.desc = desc
        self.room = room
        self._sports = {}
        self._areas = {}
        self.null_area = None
        self.users = set()
        self.game_table = paulobot.database.Table(
                self._pb.database,
                f"games_{self.name}",
                paulobot.game.DB_FIELDS)

    def __str__(self):
        return self.name

    @property
    def sports(self):
        return sorted(self._sports.values())

    @property
    def sport_names(self):
        return sorted(self._sports.keys())

    @property
    def areas(self):
        return sorted(self._areas.values())

    @property
    def area_names(self):
        return sorted(self._areas.keys())

    def get_sport(self, name):
        return self._sports[name]

    def get_area(self, name):
        return self._areas[name]

    def add_user(self, user):
        for sport in self._sports.values():
            sport.create_player(user)

        if user not in self.users:
            self.users.add(user)
            user.locations.add(self)

    def restore_from_db(self):
        recs = sorted(self.game_table.find_all(),
                          key=paulobot.game.db_rec_time_key)
        LOGGER.info("Restoring %s games for location '%s' from DB",
                    len(recs), self.name)
        for rec in recs:
            self._sports[rec['sport']].restore_game(rec)
        LOGGER.info("Restore complete!")


class LocationManager:
    def __init__(self, pb):
        self._pb = pb
        self.locations = {}
        self._load_config()

    def get_room_location(self, room):
        locs = [l for l in self.locations.values()
                  if l.room and l.room.id == room.id]
        if locs:
            return locs[0]
        return None

    def add_user_to_locations(self, user):
        # Check to see whether this user is already in rooms associated with
        # locations
        for loc in (l for l in self.locations.values() if l.room
                      and user not in l.users):
            users = self._pb.get_room_users(loc.room)
            if user in users:
                loc.add_user(user)
                user.save()

    def restore_from_db(self):
        for loc in self.locations.values():
            loc.restore_from_db()

    def _get_null_area(self, loc):
        if loc.null_area is None:
            loc.null_area = Area(None, None, 0)
        return loc.null_area

    def _load_config(self):
        for c_loc in self._pb.config.locations:
            if c_loc.room:
                room = self._pb.lookup_room(c_loc.room)
            else:
                room = None
            loc = Location(self._pb, c_loc.name,
                           c_loc.desc, room)
            self.locations[loc.name] = loc

            for c_area in c_loc.areas:
                area = Area(loc,
                            c_area.name,
                            c_area.desc,
                            c_area.size)
                loc._areas[area.name] = area

            for c_sport in c_loc.sports:
                if c_sport.area is None:
                    area = self._get_null_area(loc)
                else:
                    area = loc.get_area(c_sport.area)

                sport = paulobot.sport.Sport(
                    self._pb,
                    loc,
                    c_sport.name,
                    c_sport.desc,
                    area,
                    team_size=c_sport.team_size,
                    team_count=c_sport.team_count,
                    min_players=c_sport.min_players)
                loc._sports[sport.name] = sport
                area.sports.append(sport)

            # Sort sports by name
            for area in loc.areas:
                area.sports = sorted(area.sports)


