#
# Global Commands definition (e.g. "xxx")
#
import datetime

from .. import common

from . import defs
from .defs import (CommandError, Flags, CmdDef)

# Global command list (e.g. "xxx")
_CMDS_GLOBAL = {
    'time'          : CmdDef('Show times',
                             Flags.Direct | Flags.Group),
    'timers'        : CmdDef('Show timers',
                             Flags.Direct | Flags.Admin),
    'su'            : CmdDef('Run a command as a user',
                             Flags.Direct | Flags.Group | Flags.Admin,
                             args=["<user> Player to execute command as",
                                   "<command:subcmd>+ Command string to execute"]),

    # Hidden commands
    'register'      : CmdDef(None,
                             Flags.Direct | Flags.Group),

    'hello'         : CmdDef(None,
                             Flags.Direct | Flags.Group),
    'hi'            : CmdDef(None, None, alias="hello"),
    'yo'            : CmdDef(None, None, alias="hello"),
}


class ClassHandler(defs.ClassHandlerInterface):
    """
    Handler for _CMDS_GLOBAL commands

    """
    def __init__(self, pb):
        self.pb = pb

    @property
    def cmd_defs(self):
        return _CMDS_GLOBAL

    def _cmd_time(self, msg):
        last_boot = str(self.pb.boot_time).split(".")[0]
        text = "Current time is: {}. Last boot: {} UTC".format(
                        datetime.datetime.now().strftime("%H:%M:%S"),
                        last_boot)
        msg.reply(text)

    def _cmd_register(self, msg):
        msg.reply(f"You are already registered {msg.user.name}!")

    def _cmd_hello(self, msg):
        msg.reply(f"Hello there {msg.user.name}!")

    def _cmd_timers(self, msg):
        timers = sorted(self.pb.timer.callbacks,
                        key=lambda t: t[0])
        if timers:
            text = "\n".join(f"{w} -- {c.__self__}.{c.__name__}" for w, c in timers)
            msg.reply(f"```\n{text}\n```\n")
        else:
            msg.reply("No timers")

    def _cmd_su(self, msg):
        # Lookup the user
        email = msg.args["user"]
        if "@" not in email:
            email = f"{email}@{self.pb.config.default_host}"
        user = self.pb.user_manager.lookup_user(email)
        if user is None:
            raise CommandError(f"No such user {email}")
        text = " ".join(msg.args["command"])

        user.admin_override = msg.user.email
        msg.user.send_msg(f"Running {text} as {user} in {msg.room}")
        new_msg = common.Message(user, text, msg.room)
        new_msg.user_reply_override = msg.user
        self.pb.command_handler.handle_message(new_msg)