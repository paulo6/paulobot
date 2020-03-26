import logging
import operator

from collections import namedtuple

from .. import util
from . import global_cmds
from . import defs

from .defs import (ParseError, CommandError,
                   C_SUC, C_MUC, C_ADMIN, C_SCORE, C_HELP)

LOGGER = logging.getLogger(__name__)

class HandlerError(Exception):
    pass

class _MsgContext:
    __slots__ = ["cmd_name", "sub_cmds", "handler_class", "location", "sport", "area"]
    def __init__(self):
        self.cmd_name = None
        self.sub_cmds = []
        self.handler_class = None
        self.location = None
        self.sport = None
        self.area = None

class Handler(object):
    """
    Command handler class for handling MUC and SUC messages that contain a
    ttd command.

    """
    def __init__(self, pb):
        self._pb = pb

        # Global command handler
        self._global_handler = global_cmds.ClassHandler(self._pb)
        self._sport_handler = None
        self._area_handler = None

    def _get_message_context(self, msg):
        ctx = _MsgContext()

        if not msg.text:
            raise HandlerError(None)

        # Split the message, removing any blank portions
        cmds = [seg
                for seg in msg.text.split(" ")
                if seg != ""]

        # If we have a simple help command, then stop
        if cmds[0] in ("?", "help") and len(cmds) == 1:
            ctx.handler_class = self._global_handler
            ctx.cmd_name = cmds[0]
            return ctx

        # By default use the first token as the command
        ctx.cmd_name, *ctx.sub_cmds = cmds

        # Determine what we need to look at to work out what type
        # of command we have here
        if cmds[0] == "help":
            target = cmds[1]
        else:
            target = cmds[0]

        # If this is a global command, then can stop. Else we need
        # to see what's available in the user's locations
        if target in self._global_handler.cmd_defs:
            ctx.handler_class = self._global_handler
        else:
            # Search user locations sports and areas
            for loc in self._pb.loc_manager.get_user_locations(msg.user):
                if target in loc.sports:
                    ctx.handler_class = self._sport_handler
                    ctx.location = loc
                    ctx.sport = loc.sports[target]
                    break

                if target in loc.areas:
                    ctx.location = loc
                    ctx.handler_class = self._area_handler
                    ctx.area = loc.areas[target]
                    break

            if ctx.location is None:
                raise HandlerError(f"Unknown command '{target}'")

            # If this isn't help then shuffle out the sport/area name
            if cmds[0] != "help":
                # Should have at least 1 command
                if len(cmds) < 2:
                    raise HandlerError(f"Missing {cmds[0]} command - see help {cmds[0]}")
                ctx.cmd_name, *ctx.sub_cmds = cmds[1:]

        return ctx

    def handle_message(self, msg):
        # Get the group handler
        try:
            ctx = self._get_message_context(msg)
        except HandlerError as e:
            # Update last seen before stopping
            msg.user.update_last_msg()

            if e.args:
                msg.reply_to_user(e.args[0])
            return
        
        # Get the command definition (create a dummy one for help and ?)
        if ctx.cmd_name in ("help", "?"):
            cmd_def = defs.CmdDef(None, C_SUC | C_MUC,
                                  args=["[<string>]"])
        else:
            cmd_def = ctx.handler_class.cmd_defs.get(ctx.cmd_name)

            # If this is an alias, then update
            if cmd_def is not None and cmd_def.alias is not None:
                ctx.cmd_name = cmd_def.alias
                cmd_def = ctx.handler_class.cmd_defs.get(ctx.cmd_name)

        if cmd_def is None or (cmd_def.has_flag(C_ADMIN) 
                               and not msg.user.is_admin):
            # Use safe_string to handle any strange characters that have
            # been sent
            msg.reply_to_user("Unknown {} command {}. Try help"
                              .format("group-chat" if msg.is_group 
                                      else "direct-chat", 
                                      util.safe_string(ctx.cmd_name)))
            if cmd_def is not None and cmd_def.has_flag(C_ADMIN):
                LOGGER.info("{} just attempted to use admin command: {}"
                            .format(str(msg.user), 
                                    util.safe_string(msg.body)))
        elif msg.is_group and not cmd_def.has_flag(C_MUC):
            msg.reply_to_user("{} does not have a group-chat version"
                                .format(util.safe_string(ctx.cmd_name)))
        elif not msg.is_group and not cmd_def.has_flag(C_SUC):
            msg.reply_to_user("{} does not have a direct-chat version"
                                .format(util.safe_string(ctx.cmd_name)))
        elif cmd_def.has_flag(C_SCORE) and not ctx.handler_class.has_score_support:
            msg.reply_to_user("Sorry, this command is not supported for "
                              "sports without scoring support")
        else:
            c_msg = defs.CMessage(msg.user, cmd_def,
                                  room=msg.room,
                                  location=ctx.location,
                                  sport=ctx.sport,
                                  area=ctx.area)

            # Wrap in an exception catcher to ensure that we do respond to the
            # command in one way or another (else the default handler will
            # kick in and send the unknown command reply)
            try:
                # Parse the arguments (unless the argument is ?)
                if len(ctx.sub_cmds) == 1 and ctx.sub_cmds[0] == "?":
                    cmd_args_help = True
                else:
                    cmd_args_help = False
                    c_msg.parse_args(ctx.sub_cmds)

                # Handle help separately
                if cmd_args_help:
                    self._handle_arg_question(c_msg, cmd_def)
                elif ctx.cmd_name == "help":
                    self._handle_help(msg.user, ctx)
                elif ctx.cmd_name == "?":
                    self._handle_question(c_msg, ctx.handler_class)
                else:
                    if cmd_def.has_flag(C_ADMIN):
                        LOGGER.warning("User {} executing admin command '{}'"
                                       .format(str(msg.user), 
                                               util.safe_string(msg.body)))
                    ctx.handler_class.handle_command(ctx.cmd_name, c_msg)

            except CommandError as e:
                # If the error message is not None, then send error reply. 
                # If it is None, then it is a legacy command that sends its
                # own error
                if e.error_msg is not None:
                    text = "Sorry {}. {}".format(str(c_msg.user),
                                                 e.error_msg)
                    if e.reply_fn is None:
                        c_msg.reply(text)
                    else:
                        e.reply_fn(text)

            #except stats.NoStatsException:
            #    c_msg.reply("This sport does not have scoring support.")

            except Exception as e:
                # Flows for the bot are either triggered by command or 
                # triggered by a timer. So we wrap both these points with an 
                # exception LOGGER to ensure we record any exceptions that 
                # occur.
                reason = "{} from {!s}: {}".format("group-chat" if msg.is_group 
                                                 else "direct-chat",
                                                 msg.user, msg.text)
                LOGGER.exception("Hit exception processing " + reason)
                c_msg.reply("Sorry, hit an exception when processing your "
                            "message")

        # Update last seen now that we have processed the command (this is
        # to ensure ttd unreg when a user was idle does the unregister
        # first, rather than marking them as unidle first which will then
        # roll the game before it can do the unregister)
        msg.user.update_last_msg()

        # Message handled
        return True


    def send_html_msg(self, user, text, room=None):
        markdown = "```\n{}\n```".format(text)
        if room is None:
            self._pb.send_message(user_email=user.email, text=text, markdown=markdown)
        else:
            self._pb.send_message(room_id=room.id, text=text, markdown=markdown)

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

    def _handle_help(self, user, ctx):
        if len(ctx.sub_cmds) > 0 and ctx.handler_class == self._global_handler:
            self._handle_help_cmd(user, "global",
                                  ctx.handler_class, ctx.sub_cmds[0])
        elif len(ctx.sub_cmds) == 1:
            self._handle_help_class(user, ctx.sub_cmds[0], ctx.handler_class)
        elif len(ctx.sub_cmds) > 1:
            self._handle_help_cmd(user, ctx.sub_cmds[0],
                                  ctx.handler_class, ctx.sub_cmds[1])
        else:
            self._handle_help_class(user, "global", ctx.handler_class)

    def _handle_help_class(self, user, group_name, handler_class):
        help = "Help for {} commands".format(group_name)

        cmd_defs = sorted(handler_class.cmd_defs.items(),
                          key=operator.itemgetter(0))

        def add_cmds(flag, is_group):
            help = ""
            for cmd_name, cmd_def in cmd_defs:
                if cmd_def.alias is not None:
                    continue

                if cmd_def.has_flag(C_ADMIN) and not user.is_admin:
                    continue
            
                if (cmd_def.desc is None 
                    or not cmd_def.has_flag(flag)
                    or (not handler_class.has_score_support 
                        and cmd_def.has_flag(C_SCORE))):
                    continue
                
                if is_group and cmd_def.muc_desc is not None:
                    desc = cmd_def.muc_desc 
                else:
                    desc = cmd_def.desc

                help += "\n   {: <12} {}".format(cmd_name, desc)
            return help

        extra_info = handler_class.help_info
        if extra_info is not None:
            help += "\n" + extra_info

        help += "\n\nDirect-chat commands:"
        help += "\n-------------------"
        help += add_cmds(C_SUC, False)

        help += "\n\nGroup-chat commands:"
        help += "\n-------------------"
        help += add_cmds(C_MUC, True)
        help += ("\n\nType 'help {}<cmd>' for more details about a command"
                 .format("" if handler_class == self._global_handler else f"{group_name} "))

        self.send_html_msg(user, help)

    def _handle_help_cmd(self, user, group_name, handler_class, cmd):        
        help = "Help for '{}{}'".format(
            "" if handler_class == self._global_handler else f"{group_name} ",
            cmd)

        # Find the command def
        cmd_def = handler_class.cmd_defs.get(cmd)
        if cmd_def is None:
            raise CommandError("No such command '{}'"
                               .format(util.safe_string(cmd)), 
                               user.send_msg)

        # If alias, then grab alias
        if cmd_def.alias is not None:
            cmd = cmd_def.alias
            cmd_def = handler_class.cmd_defs[cmd]

        # See whether this cmd_def handles its own help
        if cmd_def.has_flag(C_HELP):
            help_msg = defs.CMessage(user, cmd_def)
            help_msg.parse_args(["help"])
            handler_class.handle_command(cmd, help_msg)
            return

        if cmd_def.muc_desc is not None:
            help += "\n  direct-chat usage: " + cmd_def.desc
            help += "\n  group-chat usage: " + cmd_def.muc_desc
        else:
            flags = []
            if cmd_def.has_flag(C_SUC):
                flags.append("direct-chat")
            if cmd_def.has_flag(C_MUC):
                flags.append("group-chat")

            help += "\n  {} usage: {}".format(" & ".join(flags), cmd_def.desc)

        # Three possibile options:
        #  - args None and muc_args None: No arguments at all
        #  - args not None and muc_args None: MUC and SUC share args
        #  - args None and muc_args not None: SUC no args, MUC args
        #  - args not None and len(muc_args) == 0: SUC args, MUC no args

        if (cmd_def.args_def is None or 
            len(cmd_def.args_def) == 0) and cmd_def.muc_args_def is None:
            help += "\n\n  Command takes no arguments"
        else:
            if cmd_def.args_def is not None and len(cmd_def.args_def) > 0:
                prefix = "" if cmd_def.muc_args_def is None else "Direct-chat "
                help += "\n\n  {}Arguments: {}\n".format(prefix, 
                                                       cmd_def.args_str)
                for arg in cmd_def.args_def:
                    if arg.desc is not None:
                        help += "    {}: {}\n".format(arg.name, arg.desc)
            else:
                # If we are here then there must be MUC specific args, so
                # indicate SUC has no args.
                help += "\n  Direct-chat variant has no arguments"

            # Have any MUC args been specified?
            if cmd_def.muc_args_def is not None:
                if len(cmd_def.muc_args_def) == 0:
                    help += "\n  Group-chat variant has no arguments"
                else:
                    help += "\n  Group-chat Arguments: {}\n".format(
                                        cmd_def.muc_args_str)
                for arg in cmd_def.muc_args_def:
                    if arg.desc is not None:
                        help += "    {}: {}\n".format(arg.name, arg.desc)

        self.send_html_msg(user, help)

    def _handle_question(self, c_msg, handler_class):
        # Get set of possible commands
        if c_msg.room is not None:
            cmds = ((cmd, cmd_def)
                        for cmd, cmd_def in handler_class.cmd_defs.items()
                        if cmd_def.has_flag(C_MUC))
        else:
            cmds = ((cmd, cmd_def)
                        for cmd, cmd_def in handler_class.cmd_defs.items()
                        if cmd_def.has_flag(C_SUC))

        # Filter out Admin ones
        cmds = ((cmd, cmd_def)
                    for cmd, cmd_def in cmds
                    if c_msg.user.is_admin or not cmd_def.has_flag(C_ADMIN))

        # Filter out non-score ones
        if not handler_class.has_score_support:
            cmds = ((cmd, cmd_def) 
                        for cmd, cmd_def in cmds
                        if not cmd_def.has_flag(C_SCORE))

        # Filter out hidden ones
        cmds = ((cmd, cmd_def) 
                 for cmd, cmd_def in cmds
                   if cmd_def.desc is not None)

        # Get list of just the cmds
        cmd_names = sorted([cmd for cmd, _ in cmds])

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
        self.send_html_msg(c_msg.user, "Options:\n" + "\n".join(lines),
                           room=c_msg.room)

    def _handle_arg_question(self, c_msg, cmd_def):
        # First see whether there is a muc arg override
        if c_msg.room is not None and cmd_def.muc_args_def is not None:
            # Can have muc ovveride with len 0 if there are no MUC args
            if len(cmd_def.muc_args_def) == 0:
                args_str = "Group-chat variant has no arguments"
            else:
                args_str = "Arguments: " + cmd_def.muc_args_str
        elif cmd_def.args_def is not None and len(cmd_def.args_def) > 0:
            args_str = "Arguments: " + cmd_def.args_str
        else:
            args_str = "Command has no arguments"

        # Print the args
        c_msg.reply(args_str)
