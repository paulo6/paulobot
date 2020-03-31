"""
Common shared definitions, classes and util functions

"""
import enum
import functools
import datetime

# -----------------------------------------------------------
# Common definitions
# -----------------------------------------------------------

# String for now time
TIME_NOW = "now"

# Granularity of minutes for games at a named time
MINUTE_GRANULARITY = 5

MD_LINE_SPLIT = "  \n"

def MD_RAW(s):
    return "```\n{}\n```".format(s)


# -----------------------------------------------------------
# Common Exceptions
# -----------------------------------------------------------
class BadAction(Exception):
    """
    Exception representing a bad user action. Can be raised by
    any module, and will be caught and its contents sent to the
    user.

    """
    pass


# -----------------------------------------------------------
# Common classes
# -----------------------------------------------------------
class GameState(enum.Enum):
    """
    Enumeration of game states.

    """
    Empty           = enum.auto()
    NotQuorate      = enum.auto()
    Quorate         = enum.auto()
    WaitingForTime  = enum.auto()
    WaitingForHold  = enum.auto()
    WaitingForArea  = enum.auto()
    PlayerCheck     = enum.auto()
    PlayersNotReady = enum.auto()
    Rolling         = enum.auto()


class PlayerList(list):
    """
    Class that represents a list of players.

    """
    def __init__(self, iterable=None, sport=None):
        self._team_size = 0 if sport is None else sport.team_size
        if iterable is not None:
            super().__init__(iterable)
        else:
            super().__init__()

    def __str__(self):
        return self._str(lambda p: p.user.username)

    @property
    def tagged(self):
        return self._str(lambda p: p.user.tag)

    @property
    def spaced(self):
        return self._str(lambda p: p.user.username, sep=" ")

    def _str(self, fn, sep=", "):
        if self._team_size == 1 and len(self) == 2:
            return f"{fn(self[0])} v {fn(self[1])}"
        return sep.join(fn(p) for p in self)


@functools.total_ordering
class GTime:
    """
    Class that represents a game time, which can either be "now" or a specific time.

    Can be compared with DateTimes

    """
    def __init__(self, val):
        """
        Initialize the time.

        Args:
            val: The time value. Can either be None for now, or
            a datetime value.

        """
        self.val = val

    @property
    def is_for_now(self):
        return self.val == None

    def __str__(self):
        return format_time(self.val)

    def __repr__(self):
        return f"<GTime({self})>"

    def __hash__(self):
        return hash(self.val)

    def __eq__(self, other):
        if isinstance(other, datetime.datetime):
            if self.val is None:
                return False
            return self.val == other
        return self.val == other.val

    def __lt__(self, other):
        if isinstance(other, datetime.datetime):
            if self.val is None:
                return True
            return self.val < other

        if self.val is None and other.val is not None:
            return True

        if self.val is not None and other.val is None:
            return False

        if self == other:
            return False

        return self.val < other.val


class TimeDelta:
    """
    Class that wraps a timedelta to give it a nice string, and to
    allow GTimes to be diffed

    """
    __slots__ = ["val"]
    def __init__(self, val1, val2):
        if isinstance(val1, GTime):
            val1 = val1.val
        if isinstance(val2, GTime):
            val2 = val2.val
        self.val = val1 - val2

    def __str__(self):
        return str(self.val).split(".")[0]


class CommandType(enum.Enum):
    Global = enum.auto()
    Area = enum.auto()
    Sport = enum.auto()


class Message(object):
    """
    Represents a message

    """
    def __init__(self, user, text, room=None):
        self.user = user
        self.text = text
        self.room = room

        # -------------------------------------------------
        # Fields below are filled out by the command parser
        # -------------------------------------------------
        self.location = None
        self.sport = None
        self.area = None

        # The command name
        self.cmd = None

        # The CommandType
        self.cmd_type = None

        # Instance of commands.defs.ArgParser
        # Can be accessed like a dictionary of arg-name -> value
        self.args = None

    @property
    def is_group(self):
        return self.room is not None

    @property
    def cmd_type_title(self):
        if self.cmd_type is CommandType.Global:
            return "Global"

        if self.cmd_type is CommandType.Sport:
            return self.sport.name.upper()

        if self.cmd_type is CommandType.Area:
            return self.area.name.title()

        return "Unknown"

    @property
    def cmd_type_name(self):
        if self.cmd_type is CommandType.Global:
            return None

        if self.cmd_type is CommandType.Sport:
            return self.sport.name

        if self.cmd_type is CommandType.Area:
            return self.area.name

        return "???"

    def reply(self, text):
        """
        Send a reply to the source of the message (room or player)

        """
        if self.room is not None:
            self.room.send_msg(text)
        else:
            self.reply_to_user(text)

    def reply_to_user(self, text):
        """
        Send a reply to the user who sent the message

        """
        if self.user is not None:
            self.user.send_msg(text)


class Room:
    def __init__(self, pb, room_id, title):
        self.id = room_id
        self.title = title
        self._pb = pb

    def __str__(self):
        return f"{self.id} ({self.title})"

    def send_msg(self, text):
        self._pb.send_message(text, room_id=self.id)


# -----------------------------------------------------------
# Common util functions
# -----------------------------------------------------------
def ordinal(n):
    return str(n) + {1: 'st', 2: 'nd', 3: 'rd'}.get(10 <= n % 100 <= 20
                                                    and n or n % 10, 'th')

def safe_string(msg):
    """
    Make the string safe, by trying to convert each character in turn to
    string, replacing bad ones with ?

    """
    def map_char(c):
        try:
            return str(c)
        except:
            return "?"

    return "".join(map_char(c) for c in msg)

def format_time(time_val, format_str='%H:%M', allow_now=True):
    """Function to get pretty time string."""
    if time_val is None and allow_now:
        return TIME_NOW
    elif time_val is None:
        return "None"
    else:
        return time_val.strftime(format_str)
