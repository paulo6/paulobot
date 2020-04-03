#
# Global Commands definition (e.g. "xxx")
#
import datetime

from .. import common

from . import defs
from .defs import (CommandError, Flags, CmdDef)

import paulobot.templates.commands as template
from paulobot.game import State as GameState

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
    'join-location' : CmdDef('Add self to a location',
                             Flags.Direct | Flags.Admin,
                             args=["<location:string> Location name"]),
    'users'         : CmdDef('Show users for your location(s)',
                             Flags.Direct),
    'status'        : CmdDef('Show status for your location(s)',
                             grp_desc='Show status for this room location',
                             flags=Flags.Direct | Flags.Group),
    'locations'     : CmdDef('Show your location(s)',
                             Flags.Direct),

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

    def _cmd_set_join_location(self, msg):
        loc_name = msg.args["location"]
        loc = self.pb.loc_manager.locations.get(loc_name)
        if loc is None:
            raise CommandError(f"No location named '{loc_name}'")
        loc.add_user(msg.user)
        msg.user.save()
        msg.reply(f"Added to location {loc_name}")

    def _cmd_users(self, msg):
        # Update idle time now
        msg.user.update_last_msg()

        if msg.user.is_admin:
            locations = self.pb.loc_manager.locations.values()
        else:
            locations = msg.user.locations

        users = sorted({u for l in locations
                          for u in l.users},
                        key=lambda u: u.email)

        text = f"**Users in your location(s)**\n\n"
        for u in users:
            text += f"**{u.full_name}** ({u.email})"
            extras = []
            if u.is_idle:
                extras.append("is idle")
            if u.is_admin:
                extras.append("is admin")
            if extras:
                text += " " + ", ".join(extras)

            locs = "', '".join(l.name for l in u.locations)
            if locs:
                text += "  \n" + template.INDENT
                text += f"_Locations: '{locs}'_"
            text += "  \n"

        msg.reply(text)

    def _cmd_status(self, msg):
        if msg.room is None:
            locs = msg.user.locations
        else:
            locs = (self.pb.loc_manager.get_room_location(msg.room),)

        # First gather null areas
        areas = [l.null_area for l in locs if l.null_area]

        areas += sorted(a for l in locs for a in l.areas)
        text = ""

        for area in areas:
            text += area.pretty
            text += "\n\n"

        msg.reply(text)

    def _cmd_locations(self, msg):
        text = ""
        for loc in msg.user.locations:
            desc = f" _{loc.desc}_" if loc.desc else ""
            text += f"**{loc.name}**{desc}  \n"
            text += f"{template.INDENT}Sports: {', '.join(s.name for s in loc.sports)}  \n"
            text += f"{template.INDENT}Room: {loc.room.title if loc.room else 'none'}  \n"

        if not text:
            text = "You are not in any locations"

        msg.reply(text)