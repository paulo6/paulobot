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
