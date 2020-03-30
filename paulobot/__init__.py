import os
import logging
import argparse
import re
import webexteamssdk
import datetime
import pytz
import asyncio
import sys
import traceback

import paulobot.webex
import paulobot.command

from paulobot.user import UserManager
from paulobot.location import LocationManager
from paulobot.config import Config, ConfigError

from paulobot.common import Message, Room

__version__ = "1.0.0"

LOGGER = logging.getLogger(__name__)

LOGGING_FORMAT = '{asctime:<8s} {name:<20s} {levelname:<8s} {message}'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

TAG_REGEX = r'>([A-Za-z0-9\-_ @]+)</spark-mention>'

WELCOME_TEXT = "Welcome to PauloBot, a bot for organising office sports games!  \nPlease send `register` if you would like to use this bot"
REGISTERED_TEXT = "Registration success; welcome {}! Type `help` to find out what I can do."



class SendMsgHandler(logging.Handler):
    def __init__(self, pb):
        self._pb = pb

        super(SendMsgHandler, self).__init__()

    def emit(self, record):
        log_entry = self.format(record)
        for email in self._pb.config.notify_list:
            try:
                self._pb._webex.api.messages.create(
                    toPersonEmail=email,
                    markdown=f"LOG ALERT:\n```\n{log_entry}\n```")
            except webexteamssdk.exceptions.ApiError:
                pass


class Timer:
    def __init__(self, pb):
        self._callbacks = {}
        self._task = None
        self._pb = pb

    def schedule_at(self, when, callback):
        LOGGER.info("Callback %s scheduled for %s",
                    callback, when)
        self._callbacks[callback] = when
        if self._task is None:
            self._task = self._pb.main_loop.create_task(self._checker())

    def is_scheduled(self, callback):
        return callback in self._callbacks

    def cancel(self, callback):
        del self._callbacks[callback]

    @property
    def callbacks(self):
        for callback, when in self._callbacks.items():
            yield (when, callback)

    async def _checker(self):
        while True:
            await asyncio.sleep(0.01)
            self._exec_callbacks()

    def _exec_callbacks(self):
        for callback in self._get_ready_to_exec():
            del self._callbacks[callback]
            try:
                callback()
            except:
                LOGGER.exception("An exception occurred while processing timer "
                                 "event. Ignoring.")

    def _get_ready_to_exec(self):
        now = datetime.datetime.now()
        return {
            callback
            for callback, when in self._callbacks.items()
            if when <= now
        }


class PauloBot:
    def __init__(self, args):
        # Initialization order:
        #  1) Config, as this can control logging
        #  2) Logging, so modules can log
        #  3) Webex client, so modules can lookup stuff from webex
        #  4) Managers
        self.config = Config()
        self._setup_logging(level=args.level)
        self._webex = paulobot.webex.Client(self.config.token,
                                            on_message=self._on_message,
                                            on_room_join=self._on_room_join)
        self.timer = Timer(self)
        self.user_manager = UserManager(self)
        self.loc_manager = LocationManager(self)
        self.command_handler = paulobot.command.Handler(self)
        self.boot_time = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        self.main_loop = asyncio.get_event_loop()

    def run(self):
        self._webex.run(self.main_loop)

    def send_message(self, text, room_id=None, user_email=None):
        """
        Send a message.

        """
        if not room_id and not user_email:
            raise Exception("One of room_id or user_email must be specified!")


        logging.info("Sending %s message to '%s'",
                     "group" if room_id else "direct",
                     self._webex.get_room_title(room_id) if room_id else user_email)
        self._webex.call_api(False,
                             self._webex.api.messages.create,
                             roomId=room_id,
                             toPersonEmail=user_email,
                             markdown=text)

    def lookup_room(self, room_id):
        room = self._webex.api.rooms.get(room_id)
        return Room(self, room_id, room.title)

    def get_room_users(self, room):
        members = self._webex.api.memberships.list(roomId=room.id)
        users = (self.user_manager.lookup_user(m.personEmail) for m in members)

        return [u for u in users if u is not None]

    def _setup_logging(self, logfile=None, level=logging.INFO):
        if logfile:
            logfile = os.path.expanduser(logfile)
            logging.basicConfig(filename=logfile, level=level,
                                format=LOGGING_FORMAT,
                                datefmt=LOGGING_DATE_FORMAT)
            console = logging.StreamHandler()
            console.setLevel(level)
            console.setFormatter(
                logging.Formatter(LOGGING_FORMAT, "%H:%M:%S", style="{"))
            logging.getLogger().addHandler(console)
            logging.info("Logging to STDOUT and {}".format(logfile))
        else:
            logging.basicConfig(level=level, format=LOGGING_FORMAT,
                                datefmt=LOGGING_DATE_FORMAT,
                                style="{")
            logging.info("Logging to STDOUT")

        # Setup a handler for sending error logs to notification list
        notify_list = SendMsgHandler(self)
        notify_list.setLevel(logging.ERROR)
        logging.getLogger().addHandler(notify_list)

    def _on_message(self, wx_msg):
        # Sometimes when we start up, webex plays us old messages.
        # This is useful if we haven't seen them before, but is havoc
        # if its a replay of stuff we saw just before we restarted.
        #
        # So to play it safe, ignore messages from before our boot
        # time.
        if wx_msg.created < self.boot_time:
            LOGGER.info("Ignoring old message")
            return

        text = self._get_message_text(wx_msg)
        if wx_msg.roomType == "group":
            room = Room(self,
                        wx_msg.roomId,
                        self._webex.get_room_title(wx_msg.roomId))
        else:
            room = None

        # Lookup user
        user = self.user_manager.lookup_user(wx_msg.personEmail)
        if user is None and text == "register":
            self._register_user(wx_msg.personId,
                                wx_msg.personEmail)
        elif user is None:
            self.send_message(WELCOME_TEXT, user_email=wx_msg.personEmail)
        else:
            message = Message(user, text, room)
            self.command_handler.handle_message(message)

    def _register_user(self, person_id, email):
        person = self._webex.api.people.get(person_id)
        user = self.user_manager.create_user(email,
                        person.displayName,
                        person.firstName)
        user.send_msg(REGISTERED_TEXT.format(user.name))

    def _on_room_join(self, room, email):
        room = Room(self,
                    room.id,
                    self._webex.get_room_title(room.id))

        if email is None:
            self.send_message(room_id=room.id,
                              text="Hello everyone!")
        else:
            user = self.user_manager.lookup_user(email)
            if user is not None:
                loc = self.loc_manager.get_room_location(room)
                if loc is not None and user not in loc.users:
                    loc.add_user(user)
                    user.send_msg(f"Added to location {loc.name} (room {room.title})")

    def _get_message_text(self, message):
        if message.roomType != "group":
            return message.text

        match = re.search(TAG_REGEX, message.html)
        text = message.text
        if not match:
            logging.info("Tag not found in %s", message.html)
        else:
            tag = match.group(1)
            logging.debug("Found tag: %s", tag)
            if text.startswith(tag):
                text = text[len(tag):].lstrip()
            elif text.endswith(tag):
                text = text[:-len(tag)].rstrip()

        return text


def main(args):
    parser = argparse.ArgumentParser(
        prog="paulobot",
        description="PauloBot: Office Sports Webex Teams Bot")
    parser.add_argument("-l", "--level", type=int, default=logging.INFO,
                        help="Logging level. Lower is more verbose.")
    args = parser.parse_args(args)
    try:
        PauloBot(args).run()
    except KeyboardInterrupt:
        pass
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
