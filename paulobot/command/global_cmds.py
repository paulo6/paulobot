#
# Global Commands definition (e.g. "xxx")
#
import datetime

from .. import common

from . import defs
from .defs import (CommandError, Flags, CmdDef)

from paulobot.common import MD

# Global command list (e.g. "xxx")
_CMDS_GLOBAL = {
    'time'          : CmdDef('Show times',
                             Flags.Direct | Flags.Group),
    'register'      : CmdDef(None,
                             Flags.Direct | Flags.Group),
    'timers'        : CmdDef('Show timers',
                             Flags.Direct | Flags.Admin),
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

    def _cmd_time(self, c_msg):
        last_boot = str(self.pb.boot_time).split(".")[0]
        msg = "Current time is: {}. Last boot: {}".format(
                        datetime.datetime.now().strftime("%H:%M:%S"),
                        last_boot)
        c_msg.reply(msg)

    def _cmd_register(self, c_msg):
        c_msg.reply(f"You are already registered {c_msg.user.name}!")

    def _cmd_timers(self, c_msg):
        msg = "\n".join(f"{w} {c}" for w, c in sorted(self.pb.timer.callbacks,
                                                      key=lambda t: t[0]))
        c_msg.reply(MD(f"```\n{msg}```\n"))
