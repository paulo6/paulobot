# PauloBot
Webex Teams Bot for organising office sports

## Setup

1. Install dependencies from requirements.text
1. Create an account for your bot at https://developer.webex.com/my-apps/new/bot
1. Create a config file named ~/.paulobot.json (see config guide below)

## Config Guide

Sample configuration:
```
{
    "token": "insert-bot-auth-token-here",
    "admins": [
        "admin@example.com"
    ],
    "locations": [
        {
            "name": "Office1",
            "description": "Office building 1",
            "room": "room-id1",
            "areas" : [
                {
                    "name": "tabletennis",
                    "description": "Table tennis tables",
                    "size": 2
                },
                {
                    "name": "kitchen",
                    "description": "Pool and darts table (but not at the same time)",
                    "size": 1
                }
            ],
            "sports": [
                {
                    "name": "tts",
                    "description": "Tabletennis singles",
                    "team-size": 1,
                    "area": "tabletennis"
                },
                {
                    "name": "ttd",
                    "description": "Tabletennis singles",
                    "team-size": 2,
                    "area": "tabletennis"
                },
                {
                    "name": "dto",
                    "description": "Darts open",
                    "team-size": 0,
                    "team-count": 1,
                    "area": "kitchen"
                },
                {
                    "name": "pool",
                    "description": "Pool singles",
                    "team-size": 2,
                    "area": "kitchen"
                }
            ]
        },
        {
            "name": "Internet Gaming",
            "room": "room-id2",
            "sports": [
                {
                    "name": "speed",
                    "description": "Speed runners",
                    "team-size": 4,
                    "team-count": 1,
                    "min-players": 2
                }
            ]
        }
    ]
}
```
