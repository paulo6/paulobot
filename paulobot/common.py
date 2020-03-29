"""
Common definitions

"""
import enum
import functools
import datetime

# String for now time
TIME_NOW = "now"

# Granularity of minutes for games at a named time
MINUTE_GRANULARITY = 5

MD_LINE_SPLIT = "  \n"

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
