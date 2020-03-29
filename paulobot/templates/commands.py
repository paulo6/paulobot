from paulobot.common import MD

SPORT_STATUS = MD("""**{sport} Games status**  
{games}


**{sport} Area status**  
{area}


**Pending {sport} results**  
{pending}
""")


MAIN_HELP_PREAMBLE = """
###Welcome to PauloBot!

PauloBot's purpose in life is to help you organise games in the office, and track results.

{}

{}
"""

MAIN_HELP_LOCATION = """
---
**Sports available for your location(s)**
{}

Type `help <sport>` for details about sports commands.

---
**Playing areas in your location(s)**
{}

Type `help <area>` for details about area commands.

---
"""