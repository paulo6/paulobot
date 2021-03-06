SPACE = "&nbsp;"
INDENT = SPACE * 4

SPORT_STATUS = """**{sport} Games status**  
{games}


**{sport} Area status**  
{area}


**Pending {sport} results**  
{pending}
"""


SPORT_STATUS_NO_AREA = """**{sport} Games status**  
{games}


**Pending {sport} results**  
{pending}
"""


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

MAIN_HELP_NO_LOCATION = """You are not in any sport locations."""


HELP_CMD = """
**Help for **`{cmd}`

{usage}

**Arguments** {args}  
{arg_list}
"""

HELP_CMD_USAGE = """
**Usage** _{types}_  
&nbsp;&nbsp;&nbsp;&nbsp;{desc}
"""

HELP_CMD_USAGE2 = """
**Usage** _{type1}_  
&nbsp;&nbsp;&nbsp;&nbsp;{desc1}  
**Usage** _{type2}_  
&nbsp;&nbsp;&nbsp;&nbsp;{desc2}
"""
