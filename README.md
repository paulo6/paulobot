# PauloBot
Webex Teams Bot for organising office sports.

Currently a WIP - results recording and stats in development. Enough of the bot should be in place for simple organising of games.

## Setup

1. Install dependencies from requirements.text
1. Create an account for your bot at https://developer.webex.com/my-apps/new/bot
1. Create a config file named ~/.paulobot.json (see config guide below)

## Config Guide

Configuration is provided via a JSON file, with the follow fields:
 * **token**: Bot auth token
 * **database**: Location of sqlite3 db file (default ~/.paulobot.db) [optional]
 * **admins**: List of admin email address strings [optional]
 * **notify**: List of email address strings to notify for bot error/warning logs [optional]
 * **ready-timeout**: Amount of time in seconds to wait for idle users (default 120) [optional]
 * **idle-time**: Amount of time in seconds before a user is counted as idle (default 180) [optional]
 * **default-host**: Default email host to use when users specify userids without @domain.com [optional]
 * **locations**: List of location objects, representing a sporting location
   * **name**: Name of the location
   * **description**: Description of the location [optional]
   * **room**: Associated webex room id for this location
   * **areas**: List of sporting area objects in the location where sports occur
     * **name**: Name of the area
     * **description**: Description of the area [optional]
     * **size**: Number of concurrent games that can occur in the area (0 for unlimited)
   * **sports**: List of sport objects
     * **name**: Name of the sport
     * **description**: Description of the sport [optional]
     * **team-size**: Number of players in a team, 0 for unlimited
     * **team-count**: Number of teams (default 2) [optional]
     * **min-players**: The minimum players that need to sign up before the game can go [optional]
     * **area**: Area where the sport is played. Omit if area not needed/used

Sample configuration:
```
{
    "token": "insert-bot-auth-token-here",
    "admins": [
        "admin@example.com"
    ],
    "default-host": "example.com",
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
                    "description": "Tabletennis doubles",
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
