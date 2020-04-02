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

# Sport command list (e.g. "tts xxx")
_CMDS_SPORT = {
    # Group and Direct
    'reg'         : CmdDef('Register for a game',
                           Flags.Direct | Flags.Group,
                           args=[_TIME_ARG + " Register for game at this time [default 'now']"]),
    'unreg'       : CmdDef('Unregister for a game',
                           Flags.Direct | Flags.Group,
                           args=[_TIME_ARG + " Unregister for game at this time [default 'now']"]),
    'status'      : CmdDef('Show status of games for this sport',
                           Flags.Direct | Flags.Group),
    'ready'       : CmdDef('Indicate an flexible game is ready to roll (no min player '
                           'limit game)',
                           Flags.Direct | Flags.Group | Flags.Flexi,
                           args=[_TIME_ARG + " Ready game at this "
                                 "specific time [default 'now']"]),
    'unready'     : CmdDef('Undo a "ready" (no team limit game)',
                           Flags.Direct | Flags.Group | Flags.Flexi,
                           args=[_TIME_ARG + " Unready game at this specific "
                                 "time [default 'now']"]),
}


class ClassHandler(defs.ClassHandlerInterface):
    """
    Handler for _CMDS_SPORT commands

    """
    def __init__(self, pb):
        self.pb = pb

    @property
    def cmd_defs(self):
        return _CMDS_SPORT

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

    def _game_action_reply(self, msg, action, gtime):
        text = f"{action} for **{msg.sport}** game for **{gtime}**"
        if not msg.room and msg.location.room:
            msg.reply(f"{text} in room _{msg.location.room.title}_")
        elif not msg.room:
            msg.reply(f"{text} in location _{msg.location}_")

    def _cmd_reg(self, msg):
        gtime = self.get_gtime(msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        msg.user.update_last_msg(update_idle_games=False)
        msg.sport.game_register(msg.user, gtime)
        self._game_action_reply(msg, "Registered", gtime)

    def _cmd_unreg(self, msg):
        gtime = self.get_gtime(msg)
        msg.sport.game_unregister(msg.user, gtime)
        self._game_action_reply(msg, "Unregistered", gtime)

    def _cmd_ready(self, msg):
        gtime = self.get_gtime(msg)

        # Make sure this player isn't marked as idle, just in case the
        # player is idle now and is the 4th player regging (and so it
        # would announce they are idle and then immediately say they are
        # no longer idle)
        msg.user.update_last_msg(update_idle_games=False)
        msg.sport.game_set_ready_mark(msg.user, gtime, True)
        self._game_action_reply(msg, "Set ready", gtime)

    def _cmd_unready(self, msg):
        gtime = self.get_gtime(msg)
        msg.sport.game_set_ready_mark(msg.user, gtime, False)
        self._game_action_reply(msg, "Set unready", gtime)

    def _cmd_status(self, msg):
        games = msg.sport.games

        if len(games) == 0:
            text = f"No games"
        else:
            text = MD_LINE_SPLIT.join(self.prefix_string(msg, g.pretty)
                                      for g in msg.sport.games)
        if msg.sport.area.is_null:
            msg.reply(template.SPORT_STATUS_NO_AREA.format(
                sport=msg.sport.name.upper(),
                games=text,
                pending=f"None",
            ))
        else:
            msg.reply(template.SPORT_STATUS.format(
                sport=msg.sport.name.upper(),
                games=text,
                area=f"{msg.sport.area.name.title()} free",
                pending=f"None",
            ))

