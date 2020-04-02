#
# Area command handler (e.g. "<area> xxx")
#
import datetime

from .. import common

from . import defs
from .defs import CommandError, Flags, CmdDef

from paulobot.common import MD_LINE_SPLIT
import paulobot.templates.area as template

# Default arg string to use for time
_TIME_ARG = "[<time:choice(<time>,now,next)>]"

# Sport command list (e.g. "tts xxx")
_CMDS_AREA = {
    # Group and Direct
    'status'      : CmdDef('Show area status',
                           Flags.Direct | Flags.Group),
}


class ClassHandler(defs.ClassHandlerInterface):
    """
    Handler for _CMDS_AREA commands

    """
    def __init__(self, pb):
        self.pb = pb

    @property
    def cmd_defs(self):
        return _CMDS_AREA

    def _cmd_status(self, msg):
        return msg.reply(template.area_string(msg.area))