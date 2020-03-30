#
# Sport command handler (e.g. "<sport> xxx")
#
import datetime

from .. import common

from . import defs
from .defs import CommandError, Flags, CmdDef

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
    'ready'       : CmdDef('Indicate an open game is ready to roll (no team '
                           'limit game)',
                           Flags.Direct | Flags.Group | Flags.Open,
                           args=[_TIME_ARG + " Ready game at this "
                                 "specific time [default 'now']"]),
    'unready'     : CmdDef('Undo a "ready" (no team limit game)',
                           Flags.Direct | Flags.Group | Flags.Open,
                           args=[_TIME_ARG + " Unready game at this specific "
                                 "time [default 'now']"]),
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

    def get_gtime(self, msg, arg_name="time",
                  default=common.TIME_NOW):
        # If this is an optional arg, then use get, else read it
        if msg.args.is_arg_optional(arg_name, msg.is_group):
            time = msg.args.get(arg_name, default)
        else:
            time = msg.args[arg_name]

        if time == common.TIME_NOW:
            gtime = common.GTime(None)
        elif time == defs.TIME_NEXT:
            game = msg.sport.get_next_game()
            if not game:
                raise CommandError("There is no next game")
            gtime = game.gtime
        else:
            gtime = common.GTime(time)

        return gtime

    def prefix_string(self, msg, text):
        return f"[{msg.sport.name.upper()}] {text}"

    def _cmd_reg(self, msg):
        gtime = self.get_gtime(msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        msg.user.update_last_msg(update_idle_games=False)
        msg.sport.game_register(msg.user, gtime)
        if not msg.room and msg.location.room:
            msg.reply(f"Registered for game for {gtime} in '{msg.location.room.title}'")
        elif not msg.room:
            msg.reply(f"Registered for game for {gtime}")

    def _cmd_unreg(self, msg):
        gtime = self.get_gtime(msg)
        msg.sport.game_unregister(msg.user, gtime)
        if not msg.room and msg.location.room:
            msg.reply(f"Unregistered for game for {gtime} in '{msg.location.room.title}'")
        elif not msg.room:
            msg.reply(f"Unregistered for game for {gtime}")

    def _cmd_ready(self, msg):
        gtime = self.get_gtime(msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        msg.user.update_last_msg(update_idle_games=False)
        msg.sport.game_set_ready_mark(msg.user, gtime, True)
        if not msg.room and msg.location.room:
            msg.reply(f"Game for {gtime} marked as ready '{msg.location.room.title}'")
        elif not msg.room:
            msg.reply(f"Game for {gtime} marked as ready")

    def _cmd_unready(self, msg):
        gtime = self.get_gtime(msg)
        msg.sport.game_set_ready_mark(msg.user, gtime, False)
        if not msg.room and msg.location.room:
            msg.reply(f"Game for {gtime} marked as unready '{msg.location.room.title}'")
        elif not msg.room:
            msg.reply(f"Game for {gtime} marked as unready")

    def _cmd_status(self, msg):
        games = msg.sport.games

        if len(games) == 0:
            text = f"No games"
        else:
            text = MD_LINE_SPLIT.join(self.prefix_string(msg, g.pretty)
                                      for g in msg.sport.games)

        msg.reply(template.SPORT_STATUS.format(
            sport=msg.sport.name.upper(),
            games=text,
            area=f"{msg.sport.area.name.title()} free",
            pending=f"None",
        ))

