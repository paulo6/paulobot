
import json
import requests
import asyncio
import time
import socket
import traceback
from enum import Enum

import websockets
import uuid
from webexteamssdk import WebexTeamsAPI
import webexteamssdk
import logging
from base64 import b64encode

DEVICES_URL = 'https://wdm-a.wbx2.com/wdm/api/v1/devices'

DEVICE_DATA = {
    "deviceName": "pywebsocket-client",
    "deviceType": "DESKTOP",
    "localizedModel": "python",
    "model": "python",
    "name": "python-spark-client",
    "systemName": "python-spark-client",
    "systemVersion": "0.1"
}

LOGGER = logging.getLogger(__name__)

API_RETRIES = 2
API_RETRY_DELAY = 0.5

RECONNECT_DELAY = 5
RECONNECT_LOG_AFTER = 10

MAX_MESSAGE_LENGTH = 7439


# Something changed in the webex socket API, and now need to build a 'HYDRA ID'
# from the ID in the notification in order to get a object ID (where object is
# a message or room etc).
#
# This fix is based on
# https://github.com/marksull/err-backend-cisco-webex-teams/blob/master/CiscoWebexTeams.py
#
# TODO - Need to look at service catalog (somehow?) to determine cluster
#        for now, static to us cluster
HYDRA_PREFIX = "ciscospark://us"

class HydraTypes(Enum):
    # https://github.com/webex/webex-js-sdk/blob/master/packages/node_modules/%40webex/common/src/constants.js#L62
    ATTACHMENT_ACTION = "ATTACHMENT_ACTION"
    CONTENT = "CONTENT"
    MEMBERSHIP = "MEMBERSHIP"
    MESSAGE = "MESSAGE"
    ORGANIZATION = "ORGANIZATION"
    PEOPLE = "PEOPLE"
    ROOM = "ROOM"
    TEAM = "TEAM"

class ApiError(Exception):
    """
    Raised when an API fails after API_RETRIES.

    """
    pass

class Client(object):
    def __init__(self, access_token, on_message=None,
                 on_room_join=None, on_room_leave=None):
        self.access_token = access_token
        self.api = WebexTeamsAPI(access_token=access_token)
        self.my_emails = []
        self._device_info = None
        self._on_message = on_message
        self._on_room_join = on_room_join
        self._on_room_leave = on_room_leave
        self._room_titles = {}
        self._verb_handlers = {
            "post": self._handle_post,
            "add": self._handle_add,
            "leave": self._handle_leave,
        }

    def get_room_title(self, room_id):
        return self._room_titles.get(room_id, room_id)

    def call_api(self, reraise, api, *args, **kwargs):
        """
        Helper function to call webex teams API and retry on error.

        Sometimes get transient errors so use of this function should
        help alleviate that.

        If reraise is passed then an ApiError is raised if still failing
        after max retries.

        """
        done = False
        attempt = 1
        while not done:
            try:
                done = True
                return api(*args, **kwargs)
            except (webexteamssdk.exceptions.ApiError,
                    requests.exceptions.ConnectionError) as e:
                if attempt > API_RETRIES:
                    if reraise:
                        LOGGER.error("Giving up on API call %s, args %s, kwargs %s"
                                     "\n\nCallstack:\n%s\n",
                                     api.__qualname__, args, kwargs,
                                     "".join(traceback.format_stack()))
                        raise ApiError(str(e)) from e
                    LOGGER.exception(e)
                else:
                    LOGGER.error("API %s failed (%s), retrying (%s)...",
                                 api.__qualname__, e, attempt)
                    time.sleep(API_RETRY_DELAY)
                    done = False
                    attempt += 1

    @staticmethod
    def _build_hydra_id(uuid, message_type=HydraTypes.MESSAGE):
        """
        Convert a UUID into Hydra ID that includes geo routing
        :param uuid: The UUID to be encoded
        :param message_type: The type of message to be encoded
        :return (str): The encoded uuid
        """
        return (
            b64encode(f"{HYDRA_PREFIX}/{message_type.value}/{uuid}".encode("ascii")).decode(
                "ascii"
            )
            if "-" in uuid
            else uuid
        )

    def _handle_post(self, activity):
        message_id = self._build_hydra_id(activity['id'])
        message = self.call_api(True, self.api.messages.get, message_id)
        if message.personEmail in self.my_emails:
            LOGGER.debug("Ignoring self message")
        else:
            LOGGER.info("Received %s message from %s (in '%s'), created %s: %s",
                        message.roomType,
                        message.personEmail,
                        self.get_room_title(message.roomId),
                        message.created,
                        message.text)
            if self._on_message:
                self._on_message(message)

    def _handle_add(self, activity):
        # Only care about adds in groups for now, which can be detected by
        # looking for email.
        if "emailAddress" not in activity["object"]:
            LOGGER.info("Ignoring ADD")
            return
        email = activity["object"]["emailAddress"]
        room_id = self._build_hydra_id(activity['target']['id'],
                                       message_type=HydraTypes.ROOM)
        room = self.call_api(True, self.api.rooms.get, room_id)

        LOGGER.info("Got ADD for %s in '%s'",
                    email, room.title)
        self._room_titles[room.id] = room.title
        if self._on_room_join:
            self._on_room_join(room,
                               None if email in self.my_emails else email)

    def _handle_leave(self, activity):
        # Only care about adds in groups for now, which can be detected by
        # looking for email.
        if "emailAddress" not in activity["object"]:
            LOGGER.info("Ignoring LEAVE")
            return
        room = None
        email = activity["object"]["emailAddress"]

        # If we have left the room, can no longer lookup the room!
        if email not in self.my_emails:
            room_id = self._build_hydra_id(activity['target']['id'],
                                           message_type=HydraTypes.ROOM)
            room = self.call_api(True, self.api.rooms.get, room_id)

        LOGGER.info("Got LEAVE for %s in '%s'",
                    email,
                    room.title if room else "<not available>")
        if room is None:
            self._populate_room_titles()
        if self._on_room_leave:
            self._on_room_leave(room,
                                None if email in self.my_emails else email)

    def _process_message(self, data, raise_errors=False):
        if data['data']['eventType'] == 'conversation.activity':
            activity = data['data']['activity']
            verb = activity['verb']
            if verb in self._verb_handlers:
                try:
                    self._verb_handlers[verb](activity)
                except Exception:
                    LOGGER.exception("Error handling %s", verb)
                    if raise_errors:
                        raise

    def _populate_room_titles(self):
        # Room titles are best effort for logging, so don't bail
        # if this fails.
        rooms = self.call_api(False, self.api.rooms.list)
        if rooms:
            self._room_titles = {r.id: r.title for r in rooms}

    def _get_device_info(self):
        device_info = None
        try:
            resp = self.api._session.get(DEVICES_URL)
            for device in resp['devices']:
                if device['name'] == DEVICE_DATA['name']:
                    device_info = device
        except Exception as e:
            LOGGER.warning("Failed to get devices: %s", e)

        if not device_info:
            LOGGER.info('Device does not exist, creating')

            device_info = self.api._session.post(DEVICES_URL, json=DEVICE_DATA)
            if device_info is None:
                raise Exception("Failed to get device info")
        return device_info

    def _run_prep(self):
        if self._device_info is None:
            self._device_info = self._get_device_info()
        self.my_emails = self.api.people.me().emails
        self._populate_room_titles()

    def run(self, main_loop):
        self._run_prep()
        failed_count = 0
        async def _run():
            nonlocal failed_count
            LOGGER.info("Opening websocket connection to %s", self._device_info['webSocketUrl'])
            async with websockets.connect(self._device_info['webSocketUrl']) as ws:
                failed_count = 0
                LOGGER.info("Connection opened!")
                msg = {
                    'id': str(uuid.uuid4()),
                    'type': 'authorization',
                    'data': {
                        'token': 'Bearer ' + self.access_token
                    }
                }
                await ws.send(json.dumps(msg))

                while True:
                    data = await ws.recv()
                    LOGGER.debug("Received raw data: %s", data)
                    try:
                        msg = json.loads(data)
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, self._process_message, msg)
                    except:
                        LOGGER.exception("Exception occurred while processing message...")

        # Retry on connection errors
        while True:
            try:
                main_loop.run_until_complete(_run())
            except (websockets.exceptions.WebSocketException,
                    socket.gaierror,
                    ConnectionRefusedError) as e:
                failed_count += 1
                # Only error log every certain number of attempts
                if ((failed_count % RECONNECT_LOG_AFTER) == 0):
                    log_fn = LOGGER.error
                else:
                    log_fn = LOGGER.warning
                log_fn("Connection error: %s. Retry (%s) in %ss...", e,
                       failed_count, RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)
