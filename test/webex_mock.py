import random
import unittest.mock as mock
import collections
import datetime
import pytz

import paulobot.webex
from paulobot import PauloBot


Room = collections.namedtuple("Room", ("id", "title"))
Person = collections.namedtuple("Person", ("id", "email", "displayName", "firstName"))

# Email address of the bot
BOT_EMAIL = "test@bot.com"

# Room ID to use for direct chat
DIRECT_ROOMID = "direct_id"

# Test rooms
ROOMID_1 = "room_id_1"
TEST_ROOMS = {
    ROOMID_1: Room(ROOMID_1, "Room-1"),
}

# Test people
TEST_PERSON_1 = "person1@foo.com"
TEST_PERSON_1_ID = "1"
TEST_PERSON_2 = "person2@foo.com"
TEST_PERSON_2_ID = "2"
TEST_PEOPLE = {
    TEST_PERSON_1_ID: Person(TEST_PERSON_1_ID, TEST_PERSON_1, "One Surname", "One"),
    TEST_PERSON_2_ID: Person(TEST_PERSON_2_ID, TEST_PERSON_2, "Two Surname", "Two"),
}


class UnexpectedCall(Exception):
    pass


def mock_run(self, loop):
    self._run_prep()

class MockAPI:
    def __init__(self, access_token):
        self.rooms = MockAPIRooms
        self.messages = MockAPIMessages
        self._session = mock.Mock(spec=["post"])
        self.people = MockAPIPeople
        self.memberships = MockAPIMemberships

#
# Replace WebexTeamsAPI our MockAPI, and stub Client.run
#
paulobot.webex.Client.run = mock_run
paulobot.webex.WebexTeamsAPI = MockAPI

Message = collections.namedtuple("Message",
    ("text", "html", "personEmail", "personId", "roomType", "roomId", "created"))

class MockAPIMessages:
    create = mock.Mock()
    get = mock.Mock(side_effect=UnexpectedCall)

class MockAPIRooms:
    create = mock.Mock()
    get = TEST_ROOMS.get
    list = TEST_ROOMS.values

class MockAPIPeople:
    me = lambda: collections.namedtuple("Me", ("emails",))([BOT_EMAIL])
    get = TEST_PEOPLE.get

class MockAPIMemberships:
    list = lambda roomId: []


class Bot:
    def __init__(self, config_file):
        self.pb = PauloBot(config_file=config_file)
        self.pb.run()
        self.webex = self.pb._webex
        self.api = self.pb._webex.api

    def inject_msg(self, text, uid, room_id=None):
        """
        Inject a message into the bot.

        """
        if room_id is None:
            room_id = f"direct_id_{uid}"
            mtype = "direct"
        else:
            mtype = "group"

        # Reset the mock and set it to return our message details
        now = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        self.api.messages.get.reset_mock(side_effect=UnexpectedCall)
        self.api.messages.get.side_effect = [
            Message(text, text, TEST_PEOPLE[uid].email, uid, mtype, room_id, now)
        ]

        # Inject message
        msg_id = random.randint(1, 1000000000)
        data = {
            "data": {
                "eventType": "conversation.activity",
                "activity": {
                    "verb": "post",
                    "id": msg_id,
                }
            }
        }
        self.webex._process_message(data)

        # Check we got called, and reset mock
        self.api.messages.get.assert_called_once_with(msg_id)
        self.api.messages.get.reset_mock(side_effect=UnexpectedCall)