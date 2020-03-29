#
# Sport command handler (e.g. "<sport> xxx")
#
import datetime

from .. import common

from . import defs
from .defs import (CommandError, Flags, CmdDef, catch_user_errors)

from paulobot.common import MD_LINE_SPLIT
import paulobot.templates.commands as template

# Default arg string to use for time
_TIME_ARG = "[<time:choice(<time>,now,next)>]"

# Global command list (e.g. "tts xxx")
_CMDS_GLOBAL = {
    # Group and Direct
    'reg'         : CmdDef('Register for a game',
                           Flags.Direct | Flags.Group,
                           args=[_TIME_ARG + " Register for game at this time [default 'now']"]),
    'unreg'       : CmdDef('Unregister for a game',
                           Flags.Direct | Flags.Group,
                           args=[_TIME_ARG + " Unregister for game at this time [default 'now']"]),
    'status'      : CmdDef('Show status of games for this sport',
                           Flags.Direct | Flags.Group),
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

    def get_gtime(self, c_msg, arg_name="time",
                  default=common.TIME_NOW):
        # If this is an optional arg, then use get, else read it
        if c_msg.is_arg_optional(arg_name):
            time = c_msg.args.get(arg_name, default)
        else:
            time = c_msg.args[arg_name]

        if time == common.TIME_NOW:
            gtime = common.GTime(None)
        elif time == defs.TIME_NEXT:
            game = c_msg.sport.get_next_game()
            if not game:
                raise CommandError("There is no next game")
            gtime = game.gtime
        else:
            gtime = common.GTime(time)

        return gtime

    def prefix_string(self, c_msg, text):
        return f"[{c_msg.sport.name.upper()}] {text}"

    @catch_user_errors
    def _cmd_reg(self, c_msg):
        gtime = self.get_gtime(c_msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        c_msg.user.update_last_msg(update_idle_games=False)
        c_msg.sport.game_register(c_msg.user, gtime)
        if not c_msg.room and c_msg.location.room:
            c_msg.reply(f"Registered for game for {gtime} in '{c_msg.location.room.title}'")
        elif not c_msg.room:
            c_msg.reply(f"Registered for game for {gtime}")

    @catch_user_errors
    def _cmd_unreg(self, c_msg):
        gtime = self.get_gtime(c_msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        c_msg.user.update_last_msg(update_idle_games=False)
        c_msg.sport.game_unregister(c_msg.user, gtime)
        if not c_msg.room and c_msg.location.room:
            c_msg.reply(f"Unregistered for game for {gtime} in '{c_msg.location.room.title}'")
        elif not c_msg.room:
            c_msg.reply(f"Unregistered for game for {gtime}")

    @catch_user_errors
    def _cmd_status(self, c_msg):
        games = c_msg.sport.games

        if len(games) == 0:
            text = f"No games"
        else:
            text = MD_LINE_SPLIT.join(self.prefix_string(c_msg, g.pretty)
                                      for g in c_msg.sport.games)

        c_msg.reply(template.SPORT_STATUS.format(
            sport=c_msg.sport.name.upper(),
            games=text,
            area=f"{c_msg.sport.area.name.title()} free",
            pending=f"None",
        ))

