import sys
import json
import requests
import asyncio
import time
import socket

import websockets
import uuid
from webexteamssdk import WebexTeamsAPI
import logging

DEVICES_URL = 'https://wdm-a.wbx2.com/wdm/api/v1/devices'

DEVICE_DATA={
    "deviceName":"pywebsocket-client",
    "deviceType":"DESKTOP",
    "localizedModel":"python",
    "model":"python",
    "name":"python-spark-client",
    "systemName":"python-spark-client",
    "systemVersion":"0.1"
}

LOGGER = logging.getLogger(__name__)

class Client(object):
    def __init__(self, access_token, on_message=None):
        self.access_token = access_token
        self.api = WebexTeamsAPI(access_token=access_token)
        self._device_info = None
        self._on_message = on_message
        
    def _process_message(self, data):
        if data['data']['eventType'] == 'conversation.activity':
            activity = data['data']['activity']
            if activity['verb'] == 'post':
                LOGGER.debug('activity verb is post, message id is %s', activity['id'])
                message = self.api.messages.get(activity['id'])
                
                if message.personEmail in self.my_emails:
                    LOGGER.debug("Ignoring self message")
                else:
                    LOGGER.info('Message from %s: %s', message.personEmail, message.text)
                    if self._on_message:
                        self._on_message(message)
            elif activity['verb'] == 'add':
                LOGGER.info("Got ADD")
                
    def _get_device_info(self):
        LOGGER.debug('getting device list')
        device_info = None
        try:
            resp = self.api._session.get(DEVICES_URL)
            for device in resp['devices']:
                if device['name'] == DEVICE_DATA['name']:
                    device_info = device
        except Exception as e:
            LOGGER.error("Failed to get devices: %s", e)

        if not device_info:     
            LOGGER.info('Device does not exist, creating')
            
            device_info = self.api._session.post(DEVICES_URL, json=DEVICE_DATA)
            if device_info is None:
                raise Exception("Failed to get device info")
        return device_info
        
    def run(self):
        if self._device_info is None:
            self._device_info = self._get_device_info()                
        self.my_emails = self.api.people.me().emails
            
        async def _run():
            LOGGER.info("Opening websocket connection to %s", self._device_info['webSocketUrl'])
            async with websockets.connect(self._device_info['webSocketUrl']) as ws:
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
                    message = await ws.recv()
                    LOGGER.debug("Received raw message: %s", message)
                    try:
                        msg = json.loads(message)
                        loop = asyncio.get_event_loop()
                        loop.run_in_executor(None, self._process_message, msg)
                    except:
                        LOGGER.exception("An exception occurred while processing message. Ignoring.")

        # Retry on error
        while True:
            try:
                asyncio.get_event_loop().run_until_complete(_run())
            except (websockets.exceptions.ConnectionClosedError, socket.gaierror) as e:
                LOGGER.error("Connection error: %s. Retrying in 1s...", e)
                time.sleep(1)
