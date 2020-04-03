import logging
import operator
import collections

from .. import common
from . import global_cmds
from . import sport_cmds
from . import area_cmds
from . import defs

from .defs import (ParseError, CommandError, Flags)

from paulobot.templates.commands import (
    MAIN_HELP_PREAMBLE, MAIN_HELP_LOCATION, MAIN_HELP_NO_LOCATION,
    HELP_CMD, HELP_CMD_USAGE, HELP_CMD_USAGE2)
from paulobot.common import CommandType, BadAction, MD_RAW

LOGGER = logging.getLogger(__name__)

class Handler(object):
    """
    Command handler class for handling MUC and SUC messages that contain a
    ttd command.

    """
    def __init__(self, pb):
        self._pb = pb

        # Command handlers
        self._handlers = {
            CommandType.Global: global_cmds.ClassHandler(self._pb),
            CommandType.Sport: sport_cmds.ClassHandler(self._pb),
            CommandType.Area: area_cmds.ClassHandler(self._pb),
        }

    def handle_message(self, msg):
        # If no message, then exit
        if not msg.text:
            msg.user.update_last_msg()
            return

        try:
            self._handle_message_worker(msg)

        except (BadAction, defs.BadArgValue) as e:
            msg.reply(f"Sorry {msg.user.name}. {e}")

        except CommandError as e:
            e.send(msg)

        #except stats.NoStatsException:
        #    msg.reply("This sport does not have scoring support.")

        except Exception as e:
            # Flows for the bot are either triggered by command or
            # triggered by a timer. So we wrap both these points with an
            # exception LOGGER to ensure we record any exceptions that
            # occur.
            reason = "{} from {!s}: {}".format("group-chat" if msg.is_group
                                                else "direct-chat",
                                                msg.user, msg.text)
            LOGGER.exception("Hit exception processing " + reason)
            msg.reply("Sorry, hit an exception when processing your "
                      "message")

        # Update last seen now that we have processed the command (this is
        # to ensure unreg when a user was idle does the unregister
        # first, rather than marking them as unidle first which will then
        # roll the game before it can do the unregister)
        #
        # Places that explicitly need the timestamp updated pre command
        # (like reg) call this manually first
        msg.user.update_last_msg()

    def _set_cmd_type(self, msg):
        # Split the message, removing any blank portions
        cmds = [seg
                for seg in msg.text.split(" ")
                if seg != ""]

        # If we have a simple help command, then stop
        if cmds[0] in ("?", "help") and len(cmds) == 1:
            msg.cmd_type = CommandType.Global
            msg.cmd = cmds[0]
            return []

        # By default use the first token as the command
        msg.cmd, *sub_cmds = cmds

        # Determine what we need to look at to work out what type
        # of command we have here
        if cmds[0] == "help":
            target = cmds[1]
        else:
            target = cmds[0]

        # If this is a global command, then can stop. Else we need
        # to see what's available in the user's locations
        if target in self._handlers[CommandType.Global].cmd_defs:
            msg.cmd_type = CommandType.Global
        else:
            # If this message is from a room, then this room is only
            # associated with a single location, so use that.
            #
            # If this is a direct chat message, then need to search
            # all the user's locations to see which sport/area they
            # are referring to.
            if msg.room is not None:
                loc = self._pb.loc_manager.get_room_location(msg.room)
                if loc is None:
                    LOGGER.error(f"Got message from unknown room {msg.room}")
                    raise CommandError("Room not associated with a location.")
                locs = (loc,)
            else:
                locs = msg.user.locations

            for loc in locs:
                if target in loc.sport_names:
                    msg.cmd_type = CommandType.Sport
                    msg.location = loc
                    msg.sport = loc.get_sport(target)
                    msg.area = msg.sport.area
                    break

                if target in loc.area_names:
                    msg.cmd_type = CommandType.Area
                    msg.location = loc
                    msg.area = loc.get_area(target)
                    break

            if msg.location is None:
                # We haven't matched a location or global command exactly, see if they
                # entered a partial global command.
                if any(k.startswith(target)
                       for k in self._handlers[CommandType.Global].cmd_defs.keys()):
                    msg.cmd_type = CommandType.Global
                else:
                    raise CommandError(f"Unknown command '{target}'. See `help` for supported commands.")

        # Shuffle out the sport/area keyword if not a global command
        if msg.cmd_type != CommandType.Global:
            if cmds[0] != "help":
                # Should have at least 1 command
                if len(cmds) < 2:
                    raise CommandError(f"Missing {cmds[0]} command - see help {cmds[0]}")
                msg.cmd, *sub_cmds = cmds[1:]
            else:
                # If we have "help xxx" or "help xxx foo", then get rid of the xxx as
                # we know help and the handler.
                sub_cmds = cmds[2:]

        return sub_cmds


    def _handle_message_worker(self, msg):
        # Set the command type
        sub_cmds = self._set_cmd_type(msg)
        handler_class = self._handlers[msg.cmd_type]
        if handler_class is None:
            raise CommandError("This is not implemented yet")

        # Sanitize command
        msg.cmd = common.safe_string(msg.cmd)

        # Get the command definition (create a dummy one for help and ?)
        if msg.cmd in ("help", "?"):
            cmd_def = defs.CmdDef(None, Flags.Direct | Flags.Group,
                                  args=["[<string>]"])
        else:
            cmd_def = handler_class.cmd_defs.get(msg.cmd)

        if cmd_def is None:
            # See if a partial match (ignoring aliases)
            matches = [(n, c) for n, c in handler_class.cmd_defs.items()
                        if n.startswith(msg.cmd) and
                           not c.alias and
                           self._cmd_flag_check(msg, c)]
            if len(matches) > 1:
                raise CommandError(f"Multiple commands start with '{msg.cmd}': "
                                    f"{', '.join(m[0] for m in matches)}")
            elif len(matches) == 1:
                msg.cmd, cmd_def = matches[0]

        # If this is an alias, then update
        if cmd_def is not None and cmd_def.alias is not None:
            msg.cmd= cmd_def.alias
            cmd_def = handler_class.cmd_defs.get(msg.cmd)

        # Do some checks
        if cmd_def is None or (cmd_def.has_flag(Flags.Admin)
                               and not msg.user.is_admin):
            if cmd_def is not None and cmd_def.has_flag(Flags.Admin):
                LOGGER.info(f"{msg.user} just attempted to use admin command: {msg.cmd}")

            raise CommandError("Unknown {} command {}. Try `help {}`"
                               .format("group-chat" if msg.is_group
                                       else "direct-chat",
                                       msg.cmd, msg.cmd),
                                reply_to_user=True,
                                include_sorry=False)

        if msg.is_group and not cmd_def.has_flag(Flags.Group):
            raise CommandError(f"`{msg.cmd}` does not have a group-chat version",
                               reply_to_user=True)

        if not msg.is_group and not cmd_def.has_flag(Flags.Direct):
            raise CommandError(f"`{msg.cmd}` does not have a direct-chat version",
                               reply_to_user=True)

        if not self._cmd_flag_check(msg, cmd_def, Flags.Score):
            raise CommandError("this command is not supported for "
                               "sports without scoring support")

        if not self._cmd_flag_check(msg, cmd_def, Flags.Flexi):
            raise CommandError("this command is not supported for sports with "
                               "fixed team sizes")

        # Catch all check for any flags without specific handling above
        if not self._cmd_flag_check(msg, cmd_def):
            raise CommandError("this command cannot be used here")


        # Parse the arguments (unless the argument is ?)
        if len(sub_cmds) == 1 and sub_cmds[0] == "?":
            cmd_args_help = True
        else:
            cmd_args_help = False
            msg.args = defs.ArgParser(cmd_def, sub_cmds,
                                      is_group=msg.is_group,
                                      sport=msg.sport)

        # Handle help separately
        if cmd_args_help:
            self._handle_arg_question(msg, cmd_def)
        elif msg.cmd == "help":
            self._handle_help(msg, sub_cmds)
        elif msg.cmd == "?":
            self._handle_question(msg, handler_class)
        else:
            if cmd_def.has_flag(Flags.Admin):
                LOGGER.warning("User %s executing admin command '%s'",
                                msg.user,
                                common.safe_string(msg.text))
            handler_class.handle_command(msg.cmd, msg)

    def get_table(self, widths, aligns, titles, rows, pad=4):
        # Check we have a consistent number of stuff
        if len(widths) != len(aligns) or len(widths) != len(titles):
            raise Exception("Inconsistent element counts")

        # Set widths for those that are 0
        orig_widths = widths
        rows = list(rows)
        for row in rows:
            if len(row) != len(widths):
                raise Exception("Inconsistent element counts")
            new_widths = []
            for item, width, orig in zip(row, widths, orig_widths):
                if orig == 0 and (len(str(item)) + 1) > width:
                    width = len(str(item)) + 1
                new_widths.append(width)
            widths = new_widths

        # Create format string and make sure widths can accomodate titles
        format_elems = []
        new_widths = []
        for title, width, align in zip(titles, widths, aligns):
            if len(title) > width:
                width = len(title)
            format_elems.append("{:" + align + str(width) + "}")
            new_widths.append(width)
        widths = new_widths
        format_str = (" " * pad) + " ".join(format_elems)

        # Now create lines of table
        lines = []
        lines.append(format_str.format(*titles))
        lines.append(format_str.format(*("-" * w for w in widths)))
        for row in rows:
            lines.append(format_str.format(*row))
        return "\n".join(lines)

    def _handle_help(self, msg, sub_cmds):
        if len(sub_cmds) > 0 and msg.cmd_type is CommandType.Global:
            self._handle_help_cmd(msg, sub_cmds[0])
        elif (len(sub_cmds) == 0 and
              msg.cmd_type is not CommandType.Global):
            self._handle_help_class(msg)
        elif len(sub_cmds) > 0:
            self._handle_help_cmd(msg, sub_cmds[0])
        else:
            self._handle_help_global(msg)

    def _handle_help_global(self, msg):
        global_help = self._get_help_for_class(msg)
        if not msg.user.locations:
            locations = MAIN_HELP_NO_LOCATION
        else:
            sports = []
            areas = []
            for loc in msg.user.locations:
                sports.extend(loc.sports)
                areas.extend(loc.areas)

            def sport_str(s):
                info = []
                if not s.area.is_null:
                    info.append(f"area: {s.area}")
                if s.is_flexible:
                    info.append(f"min-players: {s.min_players}")
                if s.team_count == 1 and s.team_size == 0:
                    info.append(f"max-players: any")
                elif s.team_count == 1 and s.team_size > 0:
                    info.append(f"max-players: {s.team_size}")
                else:
                    info += [f"team-size: {s.team_size}",
                             f"team-count: {s.team_count}"]
                return (f"{s.name} - {s.desc} _({', '.join(info)})_")

            locations = MAIN_HELP_LOCATION.format(
                "  - " + "\n  - ".join(sport_str(s)
                                       for s in sports),
                "  - " + "\n  - ".join(f"{a.name} - {a.desc} _(location: {a.location})_"
                                       for a in areas))

        help = MAIN_HELP_PREAMBLE.format(locations, global_help)
        msg.reply_to_user(help)

    def _get_help_for_class(self, msg):
        help = ""
        handler_class = self._handlers[msg.cmd_type]
        cmd_defs = sorted(handler_class.cmd_defs.items(),
                          key=operator.itemgetter(0))

        def add_cmds(flag, is_group):
            help = ""
            for cmd_name, cmd_def in cmd_defs:
                if cmd_def.alias is not None:
                    continue

                if not self._cmd_flag_check(msg, cmd_def):
                    continue

                if (cmd_def.desc is None
                    or not cmd_def.has_flag(flag)):
                    continue

                if is_group and cmd_def.grp_desc is not None:
                    desc = cmd_def.grp_desc
                else:
                    desc = cmd_def.desc

                help += "\n   {: <12} {}".format(cmd_name, desc)
            return help

        extra_info = handler_class.help_info
        if extra_info is not None:
            help += "\n" + extra_info

        help += f"\n\n**{msg.cmd_type_title} direct-chat commands**"
        help += "\n```\n"
        help += add_cmds(Flags.Direct, False)
        help += "\n```\n"

        help += f"\n**{msg.cmd_type_title} group-chat commands**"
        help += "\n```\n"
        help += add_cmds(Flags.Group, True)
        help += "\n```\n"
        help += ("\nType `help {}<cmd>` for more details about a command"
                 .format(f"{msg.cmd_type_name} " if msg.cmd_type_name  else ""))
        return help


    def _handle_help_class(self, msg):
        msg.reply_to_user(self._get_help_for_class(msg))

    def _handle_help_cmd(self, msg, cmd):
        handler_class = self._handlers[msg.cmd_type]
        help = "**Help for:** `{}{}`".format(
            "" if msg.cmd_type_name is None else f"{msg.cmd_type_name} ",
            cmd)

        # Find the command def
        cmd_def = handler_class.cmd_defs.get(cmd)
        if cmd_def is None:
            raise CommandError(f"No such command '{cmd}'",
                               reply_to_user=True)

        # If alias, then grab alias
        if cmd_def.alias is not None:
            cmd = cmd_def.alias
            cmd_def = handler_class.cmd_defs[cmd]

        # See whether this cmd_def handles its own help
        # @@@@ Do we still need this?
        if cmd_def.has_flag(Flags.Help):
             raise Exception()
        #    help_msg = defs.CMessage(user, cmd_def)
        #    help_msg.parse_args(["help"])
        #    handler_class.handle_command(cmd, help_msg)
        #    return

        cmd_name = "{}{}".format(
            "" if msg.cmd_type_name is None else f"{msg.cmd_type_name} ",
            cmd)
        if cmd_def.grp_args_def is None:
            if not cmd_def.args_def:
                arg_str = "None"
                arg_list = ""
            else:
                arg_str = cmd_def.args_str
                arg_list = "\n".join(f"- {arg.name}: {arg.desc}"
                                     for arg in cmd_def.args_def)

            if cmd_def.grp_desc is not None:
                usage = HELP_CMD_USAGE2.format(type1="direct-chat",
                                               desc1=cmd_def.desc,
                                               type2="group-chat",
                                               desc2=cmd_def.grp_desc)
            else:
                flags = []
                if cmd_def.has_flag(Flags.Direct):
                    flags.append("direct-chat")
                if cmd_def.has_flag(Flags.Group):
                    flags.append("group-chat")
                usage = HELP_CMD_USAGE.format(types=" & ".join(flags),
                                              desc=cmd_def.desc)

            help = HELP_CMD.format(cmd=cmd_name,
                                   usage=usage,
                                   args=arg_str,
                                   arg_list=arg_list)
        else:
            # @@@ Handle different direct vs group arguments
            pass

        msg.reply_to_user(help)

    def _handle_question(self, msg, handler_class):
        # Get set of possible commands
        if msg.room is not None:
            cmds = ((cmd, cmd_def)
                        for cmd, cmd_def in handler_class.cmd_defs.items()
                        if cmd_def.has_flag(Flags.Group))
        else:
            cmds = ((cmd, cmd_def)
                        for cmd, cmd_def in handler_class.cmd_defs.items()
                        if cmd_def.has_flag(Flags.Direct))

        # Filter out commands that don't match
        cmds = ((cmd, cmd_def)
                    for cmd, cmd_def in cmds
                    if self._cmd_flag_check(msg, cmd_def))

        # Filter out hidden ones
        cmds = ((cmd, cmd_def)
                 for cmd, cmd_def in cmds
                   if cmd_def.desc is not None)

        cmds = (c for c, _ in cmds)

        # If global then add sports/areas
        if msg.cmd_type is CommandType.Global:
            cmds = (list(cmds) + [s for l in msg.user.locations
                                    for s in l.sport_names] +
                                 [a for l in msg.user.locations
                                    for a in l.area_names])

        # Get list of just the cmds
        cmd_names = sorted(cmds)

        # Find the longest, and add two for max column width
        col_width = max(len(cmd) for cmd in cmd_names) + 2

        # Make sure we don't exceed our max width
        col_count = 80 // col_width

        # Print commands in batches
        lines = []
        for idx in range(0, len(cmd_names), col_count):
            lines.append("".join("{1:{0}}".format(col_width, c)
                                 for c in cmd_names[idx:idx + col_count]))

        # Send results, to room if this was from a room
        msg.reply("Options:\n" + MD_RAW("\n".join(lines)))

    def _handle_arg_question(self, msg, cmd_def):
        # First see whether there is a group arg override
        if msg.room is not None and cmd_def.grp_args_def is not None:
            # Can have group ovveride with len 0 if there are no MUC args
            if len(cmd_def.grp_args_def) == 0:
                args_str = "Group-chat variant has no arguments"
            else:
                args_str = f"Arguments: {cmd_def.grp_args_str}"
        elif cmd_def.args_def is not None and len(cmd_def.args_def) > 0:
            args_str = f"Arguments: {cmd_def.args_str}"
        else:
            args_str = "Command has no arguments"

        # Print the args
        msg.reply(args_str)

    def _cmd_flag_check(self, msg, cmd_def, flag=None):
        if flag is None:
            flags = Flags
        else:
            flags = (flag, )

        checks = {
            Flags.Admin: msg.user.is_admin,
            Flags.Score: msg.sport and msg.sport.has_scores,
            Flags.Flexi: msg.sport and msg.sport.is_flexible,
        }

        return all(checks[f]
                   for f in flags
                   if f in checks and cmd_def.has_flag(f))
