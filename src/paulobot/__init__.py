import os
import logging
import argparse

import paulobot.webex

__version__ = "1.0.0"

LOGGING_FORMAT = '{asctime:<8s} {name:<20s} {levelname:<8s} {message}'
LOGGING_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

class PauloBot:
    def __init__(self, args):
        with open(os.path.expanduser("~/.paulobot"), "r") as f:
            token = f.read()
        self._setup_logging(level=args.level)

        self._webex = paulobot.webex.Client(token,
                                            self._on_message)
    def run(self):
        self._webex.run()

    def send_message(self, text, markdown=None, room_id=None, user_email=None):
        if not room_id and not user_email:
            raise Exception("One of room_id or user_email must be specified!")
        logging.info("Sending message to %s: %s",
                     room_id if room_id else user_email, text)
        self._webex.api.messages.create(roomId=room_id,
                                        toPersonEmail=user_email,
                                        text=text,
                                        markdown=markdown)

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

    def _on_message(self, message):
        self.send_message(room_id=message.roomId,
                          text=f"I received: {message.text}")


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