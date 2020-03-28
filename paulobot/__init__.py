import os
import logging
import argparse
import re
import webexteamssdk
import datetime

import paulobot.webex
import paulobot.command

from paulobot.user import UserManager
from paulobot.location import LocationManager
from paulobot.config import Config

__version__ = "1.0.0"

LOGGING_FORMAT = '{asctime:<8s} {name:<20s} {levelname:<8s} {message}'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

TAG_REGEX = r'>([A-Za-z0-9\-_ @]+)</spark-mention>'

MESSAGE_SEND_ATTEMPTS = 2

WELCOME_TEXT = "Welcome to PauloBot, please send 'register' if you would like to use this bot"
REGISTERED_TEXT = "Registration success!"


class Room:
    def __init__(self, pb, room_id, title):
        self.id = room_id
        self.title = title
        self._pb = pb

    def __str__(self):
        return f"{self.id} ({self.title})"

    def send_msg(self, text, markdown=None):
        self._pb.send_message(text=text, markdown=markdown,
                              room_id=self.id)


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

        self.user_manager = UserManager(self)
        self.loc_manager = LocationManager(self)

        self.command_handler = paulobot.command.Handler(self)
        self.boot_time = datetime.datetime.now()

    def run(self):
        self._webex.run()

    def send_message(self, text, markdown=None, room_id=None, user_email=None):
        if not room_id and not user_email:
            raise Exception("One of room_id or user_email must be specified!")
        logging.info("Sending message to '%s': %s",
                     self._webex.get_room_title(room_id) if room_id
                     else user_email,
                     text)

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
                    logging.exception("Giving up trying to send message")
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

        # @@@ Setup a handler for sending error logs to admin(s)

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
            self._register_user(message.personEmail)
        elif user is None:
            self.send_message(WELCOME_TEXT, user_email=message.personEmail)
        else:
            p_msg = Message(user, text, room)
            self.command_handler.handle_message(p_msg)

    def _register_user(self, email):
        self.user_manager.create_user(email, email)
        self.send_message(REGISTERED_TEXT, user_email=email)    

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
