#
# Global Commands definition (e.g. "sports xxx")
#
import datetime
from collections import defaultdict

from .. import util

from . import defs 
from .defs import (CommandError,
                   CmdDef, C_SUC, C_MUC, C_ADMIN, C_SCORE, C_HELP)

# Sports modules that are used by this module. Used when reloading plugin.
USED_MODULES = ["dashboard", "database", "util", "command.defs"]


# Global command list (e.g. "sports xxx")
_CMDS_GLOBAL = {
    'time'          : CmdDef('Show times',
                             C_SUC | C_MUC),
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

    