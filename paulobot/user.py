import datetime
import functools

import paulobot.game
import logging
from paulobot.common import GameState
from paulobot.database import Table, FieldType

LOGGER = logging.getLogger(__name__)

class User:
    def __init__(self, pb, email, full_name, first_name,
                 update_cb):
        self.email = email
        self.full_name = full_name
        self.first_name = first_name
        self.locations = set()
        self.in_games = []
        self.db_id = None
        self._pb = pb
        self._last_msg = None
        self._update_cb = functools.partial(update_cb, self)

    def __hash__(self):
        return hash(self.email)

    def __str__(self):
        return self.email

    def __repr__(self):
        return f"<User({self.email})>"

    @property
    def name(self):
        return self.first_name if self.first_name else self.full_name

    @property
    def username(self):
        return self.email.split("@")[0]

    @property
    def tag(self):
        return "<@personEmail:{}|{}>".format(self.email, self.username)

    @property
    def is_admin(self):
        return self.email in self._pb.config.admins

    @property
    def is_idle(self):
        # If we haven't heard the user speak at all yet, assume idle
        if self._last_msg is None:
            return True

        # Has the player spoken recently?
        if (datetime.datetime.now() - self._last_msg).seconds < self._pb.config.idle_time:
            return False

        # Player hasn't spoken recently, but see whether they are in a game
        # that started to roll when they weren't idle. If they are, then we
        # don't want to make them idle (else we can have chains of people
        # becoming idle in games in TIMEOUT mode)
        for game in self.in_games:
            player = game.sport.players[self]

            # Don't check the game state to see whether we are in PlayerCheck,
            # as this function is called before not_ready_players is populated
            # when we are in this state.
            #
            # Instead, see if the idle time is running
            if (game.idle_secs_left and
                player not in game.not_ready_players):
                return False

        return True

    @property
    def is_currently_rolled(self):
        return False

    def send_msg(self, text):
        self._pb.send_message(text, user_email=self.email)

    def update_last_msg(self, update_idle_games=True):
        self._last_msg = datetime.datetime.now()

        if update_idle_games:
            # Need to take a copy of in_games, as it could change as we
            # update game state (triggering game to be deleted on roll)
            for game in list(self.in_games):

                # If the game was waiting for this player, then update the game
                player = game.sport.players[self]
                if player in game.not_ready_players:
                    game.player_is_ready(player)

    def save(self):
        self._update_cb()


class UserManager:
    DB_FIELDS = {
        "email": FieldType.TEXT,
        "data": FieldType.JSON,
    }

    def __init__(self, pb):
        self._pb = pb
        self._users = {}
        self._table = Table(self._pb.database, "users", self.DB_FIELDS)

    def lookup_user(self, email):
        return self._users.get(email)

    def create_user(self, email, full_name, first_name):
        user = self._create_user(email, full_name, first_name)
        user.db_id = self._table.create(self._user_to_db_fields(user))
        self._pb.loc_manager.add_user_to_locations(user)
        return user

    def restore_from_db(self):
        recs = self._table.find_all()
        LOGGER.info("Restoring %s users from DB", len(recs))
        for rec in recs:
            user = self._create_user(email=rec["email"],
                                     full_name=rec["data"]["full_name"],
                                     first_name=rec["data"]["first_name"])
            user.db_id = rec.id

            # Restore loctions from DB, then check whether the user has
            # joined any new locations since the last DB update
            for loc in (self._pb.loc_manager.locations[l]
                        for l in rec["data"]["locations"]):
                loc.add_user(user)
            self._pb.loc_manager.add_user_to_locations(user)
        LOGGER.info("Restore complete!")

    def _create_user(self, email, full_name, first_name):
        if email in self._users:
            return Exception(f"User {email} already exists!")

        user = User(self._pb, email, full_name, first_name,
                    update_cb=self._update_db)
        self._users[email] = user
        return user

    def _user_to_db_fields(self, user):
        return {
            "email": user.email,
            "data": {
                "full_name": user.full_name,
                "first_name": user.first_name,
                "locations": [l.name for l in user.locations],
            }
        }

    def _update_db(self, user):
        self._table.update_record(user.db_id,
                                  self._user_to_db_fields(user))