import functools

# String for now time
TIME_NOW = "now"

# Granularity of minutes for games at a named time
MINUTE_GRANULARITY = 5

#
# General utils
#
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

@functools.total_ordering
class Time:
    """
    Class that represents either a time value or "now"

    """
    def __init__(self, val):
        """
        Initialize the time.

        Args:
            val: The time value. Can either be None for now, or
            a datetime value.

        """
        self.val = val

    def __str__(self):
        return format_time(self.val)

    def __repr__(self):
        return f"<Time({self})>"

    def __hash__(self):
        return hash(self.val)

    def __eq__(self, other):
        return self.val == other.val

    def __lt__(self, other):
        if self.val is None and other.val is not None:
            return True

        if self.val is not None and other.val is None:
            return False

        if self == other:
            return False

        return self.val < other.val
