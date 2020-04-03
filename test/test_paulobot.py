"""End-to-End testing"""

import pytest
import json
import tempfile
import paulobot.webex
import test.webex_mock as wx_mock

TEST_CONFIG = {
    "token": "test-token",
    "database": tempfile.NamedTemporaryFile().name,
    "locations": [
        {
            "name": "Testing",
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
        bot.inject_msg("register", wx_mock.TEST_PERSON_1_ID)
        assert bot.pb.user_manager.lookup_user(wx_mock.TEST_PERSON_1) != None

        bot.inject_msg("register", wx_mock.TEST_PERSON_2_ID, room_id=wx_mock.ROOMID_1)
        assert bot.pb.user_manager.lookup_user(wx_mock.TEST_PERSON_2) != None