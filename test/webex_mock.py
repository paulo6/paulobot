import random
import unittest.mock as mock
import collections
import datetime
import pytz

from contextlib import contextmanager

import paulobot.webex
from paulobot import PauloBot


Room = collections.namedtuple("Room", ("id", "title"))
Person = collections.namedtuple("Person", ("id", "personEmail", "displayName", "firstName"))

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
TEST_PERSON_0 = "person0@foo.com"
TEST_PERSON_1 = "person1@foo.com"
TEST_PEOPLE = {
    0: Person(0, TEST_PERSON_0, "Zero Surname", "Zero"),
    1: Person(1, TEST_PERSON_1, "One Surname", "One"),
}

MEMBERSHIPS = {
    ROOMID_1: [TEST_PEOPLE[0]],
}


class UnexpectedCall(AssertionError):
    pass


class MockClient(paulobot.webex.Client):
    def run(self, loop):
        self._run_prep()


class MockAPI:
    def __init__(self, access_token):
        self.rooms = MockAPIRooms
        self.messages = MockAPIMessages
        self._session = mock.Mock(spec=["post", "get"])
        self.people = MockAPIPeople
        self.memberships = MockAPIMemberships

#
# Replace WebexTeamsAPI our MockAPI, and stub Client.run
#
paulobot.webex.Client = MockClient
paulobot.webex.WebexTeamsAPI = MockAPI

Message = collections.namedtuple("Message",
    ("text", "html", "personEmail", "personId", "roomType", "roomId", "created"))

class MockAPIMessages:
    create = mock.Mock(side_effect=UnexpectedCall)
    get = mock.Mock(side_effect=UnexpectedCall)

class MockAPIRooms:
    create = mock.Mock()
    get = TEST_ROOMS.get
    list = TEST_ROOMS.values

class MockAPIPeople:
    me = lambda: collections.namedtuple("Me", ("emails",))([BOT_EMAIL])
    get = TEST_PEOPLE.get

class MockAPIMemberships:
    list = lambda roomId: MEMBERSHIPS.get(roomId, [])


@contextmanager
def expect_bot_msgs(bot, messages):
    # Reset mock
    bot.api.messages.create.reset_mock(side_effect=True)
    yield None
    assert bot.api.messages.create.call_count == len(messages)
    for idx, call in enumerate(bot.api.messages.create.call_args_list):
        assert call[1]["markdown"] == messages[idx]
    bot.api.messages.create.reset_mock(side_effect=UnexpectedCall)


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
        self.api.messages.get.reset_mock()
        self.api.messages.get.side_effect = [
            Message(text, text, TEST_PEOPLE[uid].personEmail, uid, mtype, room_id, now)
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
        self.webex._process_message(data, True)

        # Check we got called, and reset mock
        self.api.messages.get.assert_called_once_with(msg_id)
        self.api.messages.get.reset_mock(side_effect=UnexpectedCall)