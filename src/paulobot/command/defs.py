#
# Definitions shared between command submodules
#
import datetime
import logging
import re
from collections import namedtuple
from collections.abc import MutableMapping

from .. import util

# String for 'next' game
TIME_NEXT = "next"

# String for 'last' game
TIME_LAST = "last"

# String for challenge game
TIME_CHALLENGE = "challenge"

# Regex for a player
RE_PLAYER = r"\[?([a-z][a-z0-9@.]+)\]?,?"

# Regex for 24 hour in dec and hex
RE_TIME_HH_24 = r"(0?[1-9]|1[0-9]|2[0-4]|0x[0-1]?[1-9a-fA-F])"

# Regex for MM in dec and hex
RE_TIME_MM = r"([0-5][0-9]|0x[1-9a-fA-F]{1,2})"

# Allowed time formats. Tuple of: (description, format, regex)
TIME_FORMATS = [
  ('HH (24 hour)',            '%H',      RE_TIME_HH_24),
  ('HHMM (24 hour)',          '%H%M',    RE_TIME_HH_24 + RE_TIME_MM),
  ('HH:MM (24 hour)',         '%H:%M',   '(0?[1-9]|1[0-9]|2[0-4]):[0-5][0-9]'),
  ('HH:MM<am|pm> (12 hour)',  '%I:%M%p', '([1-9]|1[0-2]):[0-5][0-9](am|pm)'),
  ('HH<am|pm> (12 hour)',     '%I%p',    '([1-9]|1[0-2])(am|pm)')]


# Player icons
DREAM_ICON = ":heart:"
CREAM_ICON = ":poop:"
CHAMP_ICON = ":star:"
ACTIVE_ICON = ":coffee:"


# Command flags
C_SUC    = 0x01
C_MUC    = 0x02
C_ADMIN  = 0x04
C_SCORE  = 0x08
C_HELP   = 0x10


class BadArgValue(Exception):
    def __init__(self, message, bad_value=None):
        self.bad_value = bad_value
        super(BadArgValue, self).__init__(message)


class CommandError(Exception):
    def __init__(self, error_msg, reply_fn=None):
        """
        Initialize CommandError.

        If reply_fn is None, then the default msg reply function will be
        used.

        """
        self.error_msg = error_msg
        self.reply_fn = reply_fn

    def __str__(self):
        return self.error_msg


class ParseError(Exception):
    pass


# Command definition class
class CmdDef(object):
    def __init__(self, desc, flags, alias=None, args=None,
                 muc_desc=None, muc_args=None):
        self.flags = flags
        self.desc = desc
        self.muc_desc = muc_desc
        self.alias = alias
        # If this is an alias then stop now
        if alias is not None:
            return

        if self.has_flag(C_ADMIN):
            self.desc = "[ADMIN] {}".format(self.desc)
            if self.muc_desc is not None:
                self.muc_desc = "[ADMIN] {}".format(self.muc_desc)

        if args is None:
            self.args_def = None
        else:
            self.args_def = [ArgDef(a) for a in args]

        if muc_args is None:
            self.muc_args_def = None
        else:
            self.muc_args_def = [ArgDef(a) for a in muc_args]

    def has_flag(self, flag):
        if self.flags is None:
            return False
        else:
            return (self.flags & flag) == flag

    @property
    def args_str(self):
        if self.args_def is None:
            return None
        else:
            return " ".join(str(a) for a in self.args_def)

    @property
    def muc_args_str(self):
        if self.muc_args_def is None:
            return None
        else:
            return " ".join(str(a) for a in self.muc_args_def)

    def get_args_def(self, is_muc=False):
        if is_muc and self.muc_args_def is not None:
            return self.muc_args_def
        else:
            return self.args_def


# Definition of an argument to a command
class ArgDef(object):
    # Argument types
    ARG_KEYWORD = 1
    ARG_WORD = 2
    ARG_STRING = 3
    ARG_NUM = 4
    ARG_SUBCMD = 5
    ARG_TIME = 6
    ARG_USER = 7
    ARG_TEAM = 8
    ARG_SCORE = 9
    ARG_CHOICE = 10

    # Argument flags
    FLAG_DEFAULT = 0x0
    FLAG_OPTIONAL = 0x1
    FLAG_REPEATED = 0x2
    FLAG_CONDITIONALLY_OPTIONAL = 0x4 # can be omitted if all args omitted

    _ARG_RE = r"[\[{]?<?([a-zA-Z\-:]*choice\(.*\)|[a-zA-Z:0-9\-|]+)>?(\+)?[\]}]?(?: (.*))?"

    def __init__(self, arg_str):
        """
        Arg string format is as follows:
           arg                 -- just a plain keyword arg
           arg|variant         -- keyword arg with a variant
           <arg type>          -- arg of 'arg type'
           <arg name:arg type> -- use a different name instead of arg type
           [<...>]             -- make arg optional
           <...>+              -- arg is repeated
           {<...>}             -- arg is not required if all args omitted

        Anything after arg is the description.

        Supported arg types:
            word        -- a single word
            string      -- consumes the rest of the arguments
            num         -- a number
            subcmd      -- a subcommand argument (behaves like word 
                            @@@ remove?)
            time        -- time argument 
            user        -- user/player argument
            team        -- list of players
            score       -- score argument
            choice(...) -- choice of arguments, seperated by comma

        """
        # The argument type
        self.arg_type = None

        # The flags
        self.flags = self.FLAG_DEFAULT
        
        # The argument description
        self.desc = None

        # Name for the argument
        self.name = None

        # List of ArgDef choices, if ARG_CHOICE
        self.choices = None

        # List of keywords that are allowed in keyword case
        self.keywords = None

        # Time minute granularity
        self.time_granularity = 5

        # Maximum repeat count for repeated/multiple args. Set to a large 
        # number by default
        self.max_count = 100

        self._parse_arg_def_str(arg_str)

    def __str__(self):
        if self.arg_type == self.ARG_KEYWORD:
            arg_str = self.name
        elif self.arg_type == self.ARG_CHOICE and self.name == "choice":
            # If no name has been given to the choice, then display the
            # choices instead
            arg_str = "|".join(str(c) for c in self.choices)
        else:
            arg_str = "<{}>".format(self.name)

        if self.has_flag(self.FLAG_REPEATED):
            arg_str += "+"
        if (self.has_flag(self.FLAG_OPTIONAL) or 
            self.has_flag(self.FLAG_CONDITIONALLY_OPTIONAL)):
            arg_str = "[{}]".format(arg_str)
        return arg_str

    def has_flag(self, flag):
        return (self.flags & flag) == flag

    def _parse_arg_def_str(self, arg):
        # Parse the arg
        match = re.match(self._ARG_RE, arg)
        if match is None:
            raise Exception("Bad arg format: {}".format(arg))

        type_info, opt, self.desc = match.groups()

        # Grab the name.
        #
        # @@@ need to handle no name for choice, but one of the cases having
        # a name!
        if ":" in type_info:
            name, type_info = type_info.split(":", 1)
        else:
            name = None

        # Default name is the type info name
        default_name = type_info

        # Handle special args first. Then handle the normal ones
        if "<" not in arg and ">" not in arg:
            self.arg_type = self.ARG_KEYWORD
            self.keywords = type_info.split("|")
            name = self.keywords[0] 
        elif type_info.startswith("choice"):
            self.arg_type = self.ARG_CHOICE
            default_name = "choice"

            choices = re.match(r"choice\((.*)\)", type_info).groups()[0]
            self.choices = [ArgDef(c) for c in choices.split(",")]
            self.desc += ". One of: {}".format(
                ", ".join(str(c) for c in self.choices))
        else:
            str_to_arg = {
                "word": self.ARG_WORD,
                "string": self.ARG_STRING,
                "num": self.ARG_NUM,
                "subcmd": self.ARG_SUBCMD,
                "time": self.ARG_TIME,
                "user": self.ARG_USER,
                "team": self.ARG_TEAM,
                "score": self.ARG_SCORE,
            }
            if type_info not in str_to_arg:
                raise Exception("Unknown arg type '{}' in arg '{}'"
                            .format(type_info, arg))
            self.arg_type = str_to_arg[type_info]

            # Add info for time
            if self.arg_type == self.ARG_TIME and self.desc is not None:
                self.desc += ". Minutes must be a multiple of {}".format(
                    self.time_granularity)


        # Set the name
        if name is None:
            self.name = default_name
        else:
            self.name = name

        # Check options
        if opt == "+":
            self.flags |= self.FLAG_REPEATED

            # Repeated choices not supported yet
            if self.arg_type is self.ARG_CHOICE:
                raise Exception("Repeated choices not supported")

        elif opt is not None:
            raise Exception("Unknown opt '{}' in arg '{}'"
                            .format(opt, arg))

        # Check if optional
        if arg[0] == "[":
            self.flags |= self.FLAG_OPTIONAL
            if self.desc is not None:
                self.desc = "(Optional) " + self.desc
        elif arg[0] == "{":
            self.flags |= self.FLAG_CONDITIONALLY_OPTIONAL
            if self.desc is not None:
                self.desc = ("(Optional if no other args specified) " + 
                             self.desc)


# Wrapper for choice values to also include the name of the sub-arg picked.
ChoiceVal = namedtuple("ChoiceVal", ["value", "name"])


class ArgParser(MutableMapping):
    def __init__(self, cmd_def, values, is_muc, team_size=None):
        # Dictionary of choice name to the matched arg name
        self.choice_name = {}

        # Select correct args def
        if is_muc and cmd_def.muc_args_def is not None:
            self._args_def = cmd_def.muc_args_def
            self._args_str = cmd_def.muc_args_str
        else:
            self._args_def = cmd_def.args_def
            self._args_str = cmd_def.args_str

        self._curr_idx = 0
        self._args = {}
        self._team_size = team_size

        if self._args_def is None:
            self._args_def = []

        # Ignore values after #, as these are a comment! Note that the hash
        # must be at the start of a value.
        comment_idx = [idx for idx, v in enumerate(values) 
                       if v.startswith("#")]
        if len(comment_idx) > 0:
            values = values[:comment_idx[0]]

        # Values gets consumed as we walk, so check now whether there are any
        values_given = len(values) > 0

        # Walk through the args, consuming values
        for idx, arg_def in enumerate(self._args_def):
            # Update current index
            self._curr_idx = idx

            # If there are no values left, then make sure there are no 
            # mandatory arguments that still need to be specified.
            # 
            # Conditionally optional args are not mandatory if no values have
            # been passed at all
            mand_defs = [
                a for a in self._args_def[idx:]
                if not a.has_flag(arg_def.FLAG_OPTIONAL) and
                   (not a.has_flag(arg_def.FLAG_CONDITIONALLY_OPTIONAL) or
                    values_given)]
            if (len(values) == 0 and len(mand_defs) > 0):
                raise CommandError("You forgot the {} arg. Arguments: {}"
                                   .format(mand_defs[0].name, self._args_str))
            elif len(values) == 0:
                # Done
                break

            result, num = self._process_arg_def(arg_def, values)
            
            # If there was something for this def, then add it and move to
            # next value
            if num > 0:
                # If this is a choice, record the choice name
                if isinstance(result, ChoiceVal):
                    self.choice_name[arg_def.name] = result.name
                    result = result.value

                self._args[arg_def.name] = result
                values = values[num:]

        # Check all commands processed
        if len(values) > 0:
            raise CommandError("Unexpected argument: {}".format(values[0]))

    #
    # MutableMapping methods
    # 
    def __getitem__(self,key):
        return self._args[key]

    def __setitem__(self,key, val): 
        raise RuntimeError('read only object')

    def __delitem__(self,key): 
        raise RuntimeError('read only object')

    def __iter__(self):
        return iter(self._args)

    def __len__(self):
        return len(self._args)    

    def keys(self):
        return self._args.keys()


    #
    # Util
    #
    def _process_arg_def(self, arg_def, values):
        # If this is a repeated arg, then it gets all until next arg matches
        if arg_def.has_flag(arg_def.FLAG_REPEATED):
            result = []
            total_num = 0
            while len(values) > 0 and len(result) < arg_def.max_count:
                val, num = self._process_arg_def_helper(
                                             arg_def, values,
                                             rep_count=len(result))

                # If nothing was found (because optional or reached end)
                # then stop
                if num == 0:
                    break

                # Don't support repeated choices yet
                if isinstance(val, ChoiceVal):
                    raise Exception("Repeated choices not supported")

                # Add to result
                result.append(val)
                total_num += num
                values = values[num:]

                # If the next value(s) match the next definition then stop
                if self._value_matches_next_def(values):
                    break

            # Return our result
            return result, total_num

        # Singleton arg
        else:
            return self._process_arg_def_helper(arg_def, values)


    def _process_arg_def_helper(self, arg_def, values, rep_count=0):
        try:
            return self._parse_type(arg_def, values)
        except BadArgValue as e:
            # This is ok if it is optional, unless this is the last
            # arg def. 
            # 
            # If mandatory and repeated arg, then it is ok if we have at least
            # one value
            if (arg_def.has_flag(arg_def.FLAG_OPTIONAL) and 
                not self._is_last_arg_def):
                return None, 0
            elif (not arg_def.has_flag(arg_def.FLAG_OPTIONAL) and
                  rep_count > 0):
                return None, 0
            elif arg_def.arg_type == arg_def.ARG_KEYWORD:
                raise BadArgValue("Invalid keyword '{}': {}"
                                  .format(util.safe_string(values[0]), 
                                           str(e)))
            else:
                value = e.bad_value if e.bad_value is not None else values[0]
                raise BadArgValue("Invalid {} value '{}': {}"
                                  .format(arg_def.name,
                                           util.safe_string(value),
                                           str(e)))

    def _value_matches_next_def(self, values):
        # The next arg def could be optional, so need to walk them all
        if self._curr_idx < len(self._args_def) - 1:
            for arg_def in self._args_def[self._curr_idx + 1:]:
                try:
                    self._parse_type(arg_def, values)

                    # Successfully parsed!
                    return True
                except BadArgValue:
                    # OK if this is optional
                    if not arg_def.has_flag(arg_def.FLAG_OPTIONAL):
                        return False

        # Does not match next def
        return False

    @property
    def _is_last_arg_def(self):
        return self._curr_idx == len(self._args_def) - 1

    #
    # Value parsing routines
    #
    def _parse_type(self, arg_def, values):
        """
        Process a value string, returning the value. 

        Raises BadArgValue if value is bad.

        """
        funcs = {
            arg_def.ARG_KEYWORD: self._parse_type_keyword,
            arg_def.ARG_TIME: self._parse_type_time,
            arg_def.ARG_CHOICE: self._parse_type_choice,
            arg_def.ARG_SCORE: self._parse_type_score,
            arg_def.ARG_NUM: self._parse_type_num,
            arg_def.ARG_STRING: self._parse_type_string,
            arg_def.ARG_TEAM: self._parse_type_team,
            arg_def.ARG_USER: self._parse_type_user,
        }
        if arg_def.arg_type in funcs:
            return funcs[arg_def.arg_type](arg_def, values)
        else:
            # Default handlers parse a single value
            return values[0], 1

    def _parse_type_time(self, arg_def, values):
        value = values[0]
        if value in (util.TIME_NOW, TIME_NEXT):
            return value, 1
        else:
            try:
                parsed = parse_time_str(value)
            except ValueError:
                raise BadArgValue("There appears to be a bad value in "
                                  "your time")

            if parsed is None:
                raise BadArgValue(
                             "Allowed formats: {}"
                             .format(", ".join(d for d, _, _ in TIME_FORMATS)))

            if parsed.minute % arg_def.time_granularity != 0:
                raise BadArgValue(
                             "Minutes must be a multiple of {}"
                             .format(arg_def.time_granularity))

            now = datetime.datetime.now()
            time = datetime.datetime(now.year, now.month, now.day,
                                     parsed.hour, parsed.minute)

            return time, 1

    def _parse_type_choice(self, arg_def, values):
        # Try each choice arg def in turn
        for choice in arg_def.choices:
            try:
                val, num = self._process_arg_def(choice, values)
                return ChoiceVal(val, choice.name), num
            except BadArgValue:
                pass

        # Value did not match any arg defs
        error_msg = ("Must be one of: {}"
                     .format(", ".join(str(c) for c in arg_def.choices)))

        # Add special detail for time
        if arg_def.ARG_TIME in [a.arg_type for a in arg_def.choices]:
            error_msg += ". Supported time formats: {}".format(
                                ", ".join(d for d, _, _ in TIME_FORMATS))
        raise BadArgValue(error_msg)

    def _parse_type_keyword(self, arg_def, values):
        if values[0] not in arg_def.keywords:
            if len(arg_def.keywords) > 1:
                raise BadArgValue("Expecting '{}' (allowed "
                                  "variants: '{}')"
                                  .format(arg_def.name, 
                                          "', '".join(arg_def.keywords[1:])))
            else:
                raise BadArgValue("Expecting {}"
                                  .format(arg_def.name))
        return values[0], 1

    def _parse_type_score(self, arg_def, values):
        value = values[0]
        if "-" not in value:
            raise BadArgValue("Score is of the form score1-score2")

        scores = value.split("-")
        if len(scores) != 2:
            raise BadArgValue("Score is of the form score1-score2")

        try:
            score1, score2 = int(scores[0]), int(scores[1])
        except:
            raise BadArgValue("Score values must be integers")

        return (score1, score2), 1

    def _parse_type_num(self, arg_def, values):
        try:
            value = int(values[0])
        except:
            raise BadArgValue("Argument must be a number")

        return value, 1

    def _parse_type_string(self, arg_def, values):
        # String eats all values
        return " ".join(values), len(values)

    def _parse_type_user(self, arg_def, values):
        match = re.match("^" + RE_PLAYER + "$", values[0])
        if match is None:
            # Include the bad value, since _parse_type_team uses this to
            # validate each user in the team (so we want this error to point
            # to the 'bad' user)
            raise BadArgValue("User string not valid",
                              values[0])

        return match.group(1), 1

    def _parse_type_team(self, arg_def, values):
        # What is the must number of values we can use? 
        # This assumes that whatever arg_def comes next won't consume args
        # that look like players
        max_count = 0
        for idx, _ in enumerate(values):
            # We want to consume at least 1! After which, stop when we reach
            # a value that matches the next arg deg
            if idx > 0 and self._value_matches_next_def(values[idx:]):
                break
            max_count += 1

        # If we don't have a team size, then use min of 1 and max count (as we
        # want at least one
        if self._team_size is None:
            team_size = max(1, max_count)
        else:
            team_size = self._team_size

        # If max count is less than team size, then we have problems!
        if max_count < team_size:
            raise BadArgValue("Team needs to contain {} players"
                              .format(team_size),
                              " ".join(values[:max_count]))

        # Consume the team!
        return [self._parse_type_user(arg_def, [v])[0]
                for v in values[:team_size]], team_size


class CMessage(object):
    """
    Class that wraps a received message for use in command modules, 
    containing useful information to be used by the handlers.

    """
    def __init__(self, user, cmd_def, room=None,
                 location=None, sport=None, area=None,
                 user_reply_override=None, reply_override=None):
        self.user = user
        self.room = room
        self.location = location
        self.sport = sport
        self.area = area

        # Dictionary of argument name to argument value, parsed from the 
        # command string using the argument definitions for this command.
        #
        # Populated when parse_args called
        self.args = None

        self._cmd_def = cmd_def
        self._user_reply_override = user_reply_override
        self._reply_override = reply_override

    def parse_args(self, arg_list):
        team_size = None if self.sport is None else self.sport.team_size
        try:
            self.args = ArgParser(self._cmd_def, arg_list,
                                  is_muc=self.room is not None,
                                  team_size=team_size)
        
        # Convert to CommandError
        except BadArgValue as e:
            raise CommandError(e)

    def is_arg_optional(self, arg_name):
        if (self.room is not None and 
            self._cmd_def.muc_args_def is not None):
            search_defs = self._cmd_def.muc_args_def
        else:
            search_defs = self._cmd_def.args_def
        # First find the arg_def
        for arg_def in search_defs:
            if arg_name == arg_def.name:
                return arg_def.has_flag(arg_def.FLAG_OPTIONAL)

        # Invalid arg name!
        raise Exception("Invalid arg name: {}".format(arg_name))

    def reply(self, msg):
        """
        Send a reply to the source of the message (room or player)

        """
        if self._reply_override is not None:
            self._reply_override(msg)
        elif self.room is not None:
            self.room.send_msg(msg)
        else:
            self.user_reply(msg)

    def user_reply(self, msg):
        """
        Reply to a user directly (even if message from a room)

        """
        if self._user_reply_override is not None:
            self._user_reply_override(msg)
        else:
            self.user.send_msg(msg)


class ClassHandlerInterface(object):
    """
    Class that defines the handler for a class of commands

    """
    def __init__(self):
        pass

    @property
    def cmd_defs(self):
        return None

    @property
    def help_info(self):
        return None

    @property
    def has_score_support(self):
        return True

    def handle_command(self, cmd_name, c_msg):
        # Get the function and process it
        self.get_cmd_func(cmd_name)(c_msg)

    #
    # Shared utils
    #
    def get_most_active_player(self, sport, include_stats=True):
        def active_key(player_item):
            _, s = player_item
            return (-s.matches_played,
                    -s.games_played,
                    -s.last_game_id)

        # Only include known players
        pairs = ((p, s) 
                 for p, s in sport.stats.player_stats.items()
                 if p.is_known)

        active_sort = sorted(pairs,
                             key=active_key)
        if len(active_sort) == 0:
            return None
        elif include_stats:
            return (active_sort[0])
        else:
            return (active_sort[0][0])

    def get_player_sport_icons(self, m_player, sport):
        icons = []
        team_stats = sport.stats.team_stats
        if (m_player is not None
            and team_stats.dream_team is not None 
            and m_player in team_stats.dream_team):
            icons.append(DREAM_ICON)
        if (m_player is not None
            and team_stats.creamed_team is not None 
            and m_player in team_stats.creamed_team):
            icons.append(CREAM_ICON)

        leader_board = sport.stats.get_leader_board(include_stats=False)
        if (m_player in leader_board 
            and leader_board.index(m_player) == 0):
            icons.append(CHAMP_ICON)
        if m_player == self.get_most_active_player(sport, include_stats=False):
            icons.append(ACTIVE_ICON)
        return icons

    def get_global_player_status(self, g_player):
        now = datetime.datetime.now()
        if g_player.is_afk:
            status = "afk"
        elif g_player.ready_check(now):
            status = "ready"
        elif g_player.get_last_msg() is None:
            status = "idle (unknown)"
        else:
            idle_time = str(now - g_player.get_last_msg()).split(".")[0]
            status = "idle {}".format(idle_time)

        return status

    def get_cmd_func(self, cmd):
        return getattr(self, '_cmd_{}'.format(cmd.replace("-", "_")))


def parse_time_str(time_str):
    # Parse the time by finding which time format has been used, and then
    # parsing with corresponding format.
    #
    # Can return ValueError if time looks like it matches a format but
    # has a bad value in it
    for _, time_format, time_re in TIME_FORMATS:
        if re.match("^" + time_re + "$", time_str) is not None:
            # Convert hex to decimal
            time_str = re.sub('0x[a-fA-F0-9]+(?!x)',
                              lambda m: str(int(m.group(0), 0)),
                              time_str)

            # Parse
            return datetime.datetime.strptime(time_str, time_format)

    return None
