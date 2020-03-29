import os
import logging
import argparse
import re
import webexteamssdk
import datetime
import asyncio

import paulobot.webex
import paulobot.command

from paulobot.user import UserManager
from paulobot.location import LocationManager
from paulobot.config import Config

from paulobot.common import MD

__version__ = "1.0.0"

LOGGER = logging.getLogger(__name__)

LOGGING_FORMAT = '{asctime:<8s} {name:<20s} {levelname:<8s} {message}'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

TAG_REGEX = r'>([A-Za-z0-9\-_ @]+)</spark-mention>'

MESSAGE_SEND_ATTEMPTS = 2

WELCOME_TEXT = "Welcome to PauloBot, please send 'register' if you would like to use this bot"
REGISTERED_TEXT = "Registration success! Welcome {}!"


class Room:
    def __init__(self, pb, room_id, title):
        self.id = room_id
        self.title = title
        self._pb = pb

    def __str__(self):
        return f"{self.id} ({self.title})"

    def send_msg(self, text):
        self._pb.send_message(text, room_id=self.id)


class Message(object):
    def __init__(self, user, text, room=None):
        self.user = user
        self.text = text
        self.room = room

    @property
    def is_group(self):
        return self.room is not None

    def reply_to_user(self, text):
        # Replies to the user who sent the message
        if self.user is not None:
            self.user.send_msg(text)


class SendMsgHandler(logging.Handler):
    def __init__(self, pb):
        self._pb = pb

        super(SendMsgHandler, self).__init__()

    def emit(self, record):
        log_entry = self.format(record)
        for email in self._pb.notify_list:
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
        #  1) Logging, so modules can log
        #  2) Config
        #  3) Webex client, so modules can lookup stuff from webex
        #  4) Managers
        self._setup_logging(level=args.level)
        self.config = Config()
        self._webex = paulobot.webex.Client(self.config.data["token"],
                                            on_message=self._on_message,
                                            on_room_join=self._on_room_join)
        self.timer = Timer(self)
        self.user_manager = UserManager(self)
        self.loc_manager = LocationManager(self)
        self.command_handler = paulobot.command.Handler(self)
        self.boot_time = datetime.datetime.now()
        self.admins = set(self.config.data.get("admins", []))
        self.notify_list = self.config.data.get("notify", [])
        self.main_loop = asyncio.get_event_loop()

    def run(self):
        self._webex.run(self.main_loop)

    def send_message(self, text, room_id=None, user_email=None):
        """
        Send a message.

        To send markdown, use an instance of common.MD

        """
        if not room_id and not user_email:
            raise Exception("One of room_id or user_email must be specified!")

        # If this is a markdown object, then extract the fields
        if isinstance(text, MD):
            markdown = text.markdown
            text = text.plain
        else:
            markdown = None

        logging.info("Sending %s message to '%s'",
                     "group" if room_id else "direct",
                     self._webex.get_room_title(room_id) if room_id else user_email)

        # Sometimes we get transient errors when sending, so retry until
        # success, or if we reach max retries
        done = False
        attempt = 1
        while not done:
            try:
                done = True
                self._webex.api.messages.create(roomId=room_id,
                                                toPersonEmail=user_email,
                                                text=text,
                                                markdown=markdown)
            except webexteamssdk.exceptions.ApiError as e:
                if attempt > MESSAGE_SEND_ATTEMPTS:
                    logging.exception("Giving up trying to send message text: %s",
                                      markdown if text is None else text)
                else:
                    logging.error("Failed to send message (%s), retrying (%s)...",
                                  e, attempt)
                    done = False
                    attempt += 1

    def lookup_room(self, room_id):
        try:
            room = self._webex.api.rooms.get(room_id)
            return Room(self, room_id, room.title)
        except webexteamssdk.exceptions.ApiError:
            logging.exception(f"Failed to lookup room id: {room_id}")
            return None

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

    def _on_message(self, message):
        text = self._get_message_text(message)
        if message.roomType == "group":
            room = Room(self,
                        message.roomId,
                        self._webex.get_room_title(message.roomId))
        else:
            room = None

        # Lookup user
        user = self.user_manager.lookup_user(message.personEmail)
        if user is None and text == "register":
            self._register_user(message.personId,
                                message.personEmail)
        elif user is None:
            self.send_message(WELCOME_TEXT, user_email=message.personEmail)
        else:
            p_msg = Message(user, text, room)
            self.command_handler.handle_message(p_msg)

    def _register_user(self, person_id, email):
        person = self._webex.api.people.get(person_id)
        user = self.user_manager.create_user(email,
                        person.displayName,
                        person.firstName)
        user.send_msg(REGISTERED_TEXT.format(user.name))
        if user.locations:
            user.send_msg(
                "You have been added to the follow locations: "
                f"{',' .join(l.name for l in user.locations)}")

    def _on_room_join(self, room, email):
        if email is None:
            self.send_message(room_id=room.id,
                              text="Hello everyone!")
        else:
            self.send_message(room_id=room.id,
                              text=f"Welcome {email}")

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
