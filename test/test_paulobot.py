"""End-to-End testing"""

import pytest
import json
import tempfile
import paulobot.webex
import paulobot
import test.webex_mock as wx_mock

LOCATION_NAME = "Testing"

TEST_CONFIG = {
    "token": "test-token",
    "database": tempfile.NamedTemporaryFile().name,
    "locations": [
        {
            "name": LOCATION_NAME,
            "room": wx_mock.ROOMID_1,
            "sports": [
                {
                    "name": "tts",
                    "description": "Tabletennis singles",
                    "team-size": 1,
                },
            ]
        }
    ]
}


class TestBasic:
    @pytest.fixture(scope="function")
    def bot(self):
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(json.dumps(TEST_CONFIG).encode())
            fp.seek(0)
            yield wx_mock.Bot(fp.name)

    def test_register(self, bot):
        with wx_mock.expect_bot_msgs(bot, [paulobot.REGISTERED_TEXT.format(wx_mock.TEST_PEOPLE[0].firstName)]):
            bot.inject_msg("register", wx_mock.TEST_PEOPLE[0].id)
            user = bot.pb.user_manager.lookup_user(wx_mock.TEST_PERSON_0)
            assert user != None
            assert {l.name for l in user.locations} == {LOCATION_NAME}

        with wx_mock.expect_bot_msgs(bot, [paulobot.REGISTERED_TEXT.format(wx_mock.TEST_PEOPLE[1].firstName)]):
            bot.inject_msg("register", wx_mock.TEST_PEOPLE[1].id, room_id=wx_mock.ROOMID_1)
            user = bot.pb.user_manager.lookup_user(wx_mock.TEST_PERSON_1)
            assert user != None
            assert user.locations == set()