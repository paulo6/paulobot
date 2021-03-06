import asyncio
import enum
import transitions
import datetime
import collections
import functools
import logging

import paulobot.templates.game as template
from paulobot.common import GameState as State
from paulobot.common import PlayerList, GTime, BadAction
from paulobot.database import FieldType


class Trigger:
    PlayersAdded   = "_trig_players_added"
    PlayersRemoved = "_trig_players_removed"
    TimerFired     = "_trig_timer_fired"
    AreaReady      = "_trig_area_ready"
    HoldSet        = "_trig_hold_set"
    HoldCleared    = "_trig_hold_cleared"
    PlayerReady    = "_trig_player_ready"
    Roll           = "_trig_roll"


# Functions that block going into PlayerCheck state
PLAYER_CHECK_BLOCKERS = ['is_future_game', 'is_held', 'is_area_busy']

GTIME_NOW = GTime(None)

LOGGER = logging.getLogger(__name__)

DB_FIELDS = {
    "sport":        FieldType.TEXT,
    "gtime":        FieldType.DATETIME,
    "created_time": FieldType.DATETIME,
    "quorate_time": FieldType.DATETIME,
    "data":         FieldType.JSON,
}

GAME_TRANSITIONS = [
    # Player added transitions
    {
        'trigger': Trigger.PlayersAdded,   'source': State.Empty,      'dest': State.NotQuorate,
        'conditions': ['has_players', "has_space"]
    },
    {
        'trigger': Trigger.PlayersAdded,   'source': State.NotQuorate, 'dest': State.NotQuorate,
        'conditions': ['has_space']
    },
    {
        'trigger': Trigger.PlayersAdded,   'source': [State.Empty, State.NotQuorate], 'dest': State.Quorate,
        'unless': ['has_space']
    },

    # Player removed transitions
    {
        'trigger': Trigger.PlayersRemoved, 'source': '*',              'dest': State.NotQuorate,
        'conditions': ['has_players', 'has_space'], # Make sure we only change state if there is space
    },
    {
        'trigger': Trigger.PlayersRemoved, 'source': '*',              'dest': State.Empty,
        'unless': ['has_players']
    },

    # Hold transitions - hold can be applied in any state
    {
        'trigger': Trigger.HoldSet,     'source': State.NotQuorate,            'dest': State.NotQuorate,
    },
    {
        'trigger': Trigger.HoldSet,     'source': State.WaitingForTime,        'dest': State.WaitingForTime,
    },
    {
        'trigger': Trigger.HoldSet,     'source': State.WaitingForArea,        'dest': State.WaitingForHold,
    },
    {
        'trigger': Trigger.HoldSet,     'source': State.PlayerCheck,           'dest': State.WaitingForHold,
    },

    # Roll transitions - see whether we can go to PlayerCheck or whether we need to wait for an event
    #   Make sure that we priotise waiting states in this order:
    #     - Time
    #     - Hold
    #     - Area
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForTime,
        'conditions': ['is_future_game'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForHold,
        'conditions': ['is_held'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForArea,
        'conditions': ['is_area_busy'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },

    # Removal WaitingForxxx triggers either puts us back into quorate if something else is stopping us,
    # else moves into PlayerCheck state
    {
        'trigger': Trigger.TimerFired,    'source': State.WaitingForTime,       'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },
    {
        'trigger': Trigger.TimerFired,    'source': State.WaitingForTime,       'dest': State.Quorate,
    },

    {
        'trigger': Trigger.HoldCleared,   'source': State.WaitingForHold,       'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },
    {
        'trigger': Trigger.HoldCleared,   'source': State.WaitingForHold,       'dest': State.Quorate,
    },

    {
        'trigger': Trigger.AreaReady,     'source': State.WaitingForArea,       'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },
    {
        'trigger': Trigger.AreaReady,     'source': State.WaitingForArea,       'dest': State.Quorate,
    },

    # If the timer fires in PlayerCheck, then that means gave up waiting for players
    {
        'trigger': Trigger.TimerFired,   'source': State.PlayerCheck,          'dest': State.PlayersNotReady,
    },

    # Can only move out of PlayerCheck if there are no idle players
    {
        'trigger': Trigger.PlayerReady,   'source': State.PlayerCheck,          'dest': State.Rolling,
        'conditions': ['are_players_ready']
    },
]


class StateException(Exception):
    """
    Exception raised when a bad state transition happens.

    """
    pass


class Game:
    def __init__(self, pb, sport, game_manager, gtime):
        self.sport = sport
        self.gtime = gtime

        self.created_time = datetime.datetime.now()
        self.quorate_time = None
        self.rolled_time = None

        self.db_id = None

        self._game_manager = game_manager
        self._pb = pb
        self._timeout_fire_time = None
        self._flexible_ready = False
        self._pb = pb
        # Need to use a list for players because sign up order is important.
        self._players = PlayerList(sport=self.sport)
        self._not_ready_players = set()
        self._hold_info = None
        self._in_area_queue = False

    def __repr__(self):
        # pylint: disable=no-member
        return f"<Game({self.sport.name}, {self.gtime}, {self.state})>"


    # --------------------------------------------------
    # Properties used by state machine
    # --------------------------------------------------
    @property
    def has_space(self):
        return self.spaces_left is None or self.spaces_left > 0

    @property
    def has_players(self):
        return len(self._players) > 0

    @property
    def is_future_game(self):
        return self.gtime is not None and self.gtime > datetime.datetime.now()

    @property
    def is_held(self):
        return self._hold_info is not None

    @property
    def is_area_busy(self):
        return self.sport.area.is_busy(self)

    @property
    def are_players_ready(self):
        return len(self._not_ready_players) == 0

    # --------------------------------------------------
    # Properties
    # --------------------------------------------------
    @property
    def spaces_left(self):
        # If flexible ready, then no spaces left
        if self._flexible_ready:
            return 0

        # Max plaers of 0 means infinite spaces!
        if self.sport.max_players == 0:
            return None

        return self.sport.max_players - len(self._players)

    @property
    def players(self):
        return self._players

    @property
    def not_ready_players(self):
        return PlayerList(self._not_ready_players)

    @property
    def idle_secs_left(self):
        if self._timeout_fire_time is None:
            return None
        return (self._timeout_fire_time - datetime.datetime.now()).seconds

    @property
    def pretty(self):
        """
        Pretty string for use in messaging rooms.

        Has user webex-tags but not sport tag.

        """
        return template.game_string(self)

    @property
    def pretty_for_direct(self):
        """
        Pretty string for direct messages.

        Has no user webex-tags, but has a sport tag prefix

        """
        return f"{self.sport.tag} {template.game_string(self, no_tags=True)}"

    @property
    def held_by(self):
        return self._hold_info[0] if self._hold_info else None

    @property
    def flexible_ready(self):
        return self._flexible_ready

    @flexible_ready.setter
    def flexible_ready(self, val):
        if not self.sport.is_flexible:
            raise Exception("Cannot set flexible_ready for a non-flexible game")
        if val and not self.flexible_ready:
            self._flexible_ready = val
            self.do_trigger(Trigger.PlayersAdded)
        if not val and self.flexible_ready:
            self._flexible_ready = val
            self.do_trigger(Trigger.PlayersRemoved)

    @property
    def time_index(self):
        """
        What position is this game in in the game managers list of games for
        this time?

        """
        return self._game_manager.get_game_time_index(self)


    # --------------------------------------------------
    # Methods for changing game state
    # --------------------------------------------------
    def add_player(self, player):
        self.add_players((player,))

    def add_players(self, players, flexible_ready=False):
        if flexible_ready and not self.sport.is_flexible:
            raise Exception("Cannot set flexible_ready for a non-flexible game")
        changed = False
        for player in (p for p in players if p not in self._players):
            if self.has_space:
                self._players.append(player)
                player.user.in_games.append(self)
                changed = True

        if changed:
            self._flexible_ready = flexible_ready
            self.do_trigger(Trigger.PlayersAdded)

    def remove_player(self, player):
        self.remove_players((player,))

    def remove_players(self, players):
        changed = False
        for player in (p for p in players if p in self._players):
            self._players.remove(player)
            player.user.in_games.remove(self)
            changed = True

        if changed:
            self.do_trigger(Trigger.PlayersRemoved)

    def add_hold(self, player, reason):
        self._hold_info = (player, reason)
        self.do_trigger(Trigger.HoldSet)

    def remove_hold(self):
        if self._hold_info is not None:
            self._hold_info = None
            self.do_trigger(Trigger.HoldCleared)

    def player_is_ready(self, player):
        self._not_ready_players.remove(player)
        self.do_trigger(Trigger.PlayerReady)

    def do_trigger(self, trigger):
        start_state = self.state # pylint: disable=no-member
        self.trigger(trigger) # pylint: disable=no-member
        self._game_manager._game_event(self, start_state)

    # --------------------------------------------------
    # State machine callbacks - should *not* be called
    # directly!
    # --------------------------------------------------
    def on_enter_NotQuorate(self, event):
        # Whenever we enter NotQuorate, reset flexi ready and quorate time
        self._flexible_ready = False
        self.quorate_time = None

    def on_enter_Quorate(self, event):
        # Whenever we enter quorate state, try to roll
        self.quorate_time = datetime.datetime.now()

    def on_enter_Rolling(self, event):
        self.rolled_time = datetime.datetime.now()

    def on_exit_Rolling(self, event):
        raise StateException("Can't leave rolling state")

    def on_enter_WaitingForArea(self, event):
        self.sport.area.add_to_queue(self)

    def on_exit_WaitingForArea(self, event):
        # If we leave waiting for area and do not go to
        # player check, then remove from queue/
        #
        # If we move to PlayerCheck, then that means the
        # area gave us the go ahead and so moved us from
        # the waiting queue to the rolling list
        if _event_dest_is_state(event, State.PlayerCheck):
            self.sport.area.remove_from_queue(self)

    def on_enter_PlayerCheck(self, event):
        # First check whether any players are in another rolled game.
        # If so don't do anything else, and let the game manager remove
        # them.
        self._not_ready_players = {
            p for p in self._players if p.user.is_currently_rolled
        }

        # If there are no clashed players, then count ourselves as rolling
        # from now, so another game doesn't jump the queue whilst we wait
        # for people to ready up.
        if self.are_players_ready:
            # Count ourselves as rolling from now, so another game
            # don't jump ahead just because we are waiting for our
            # players.
            #
            # The game manager will take care of messaging players.
            self.sport.area.add_to_rolling(self)
            self._not_ready_players = {p for p in self._players if p.user.is_idle}

            if not self.are_players_ready:
                self._start_timeout_timer()

    def on_exit_PlayerCheck(self, event):
        # Clear not ready players set if not heading to PlayersNotReady.
        # We need the not ready player list in PlayersNotReady
        if not _event_dest_is_state(event, State.PlayersNotReady):
            self._not_ready_players.clear()

        # Ideally we'd just remove ourselves from the rolling list if we
        # aren't head to rolling. However this could trigger
        # the Area to roll the 2nd game for this time if that game is full.
        #
        # This is problematic for 2 reasons, if this game is heading for
        # PlayersNotReady:
        # 1) We'll announce that 2nd game rolling before we have had
        #    chance to announce this game is no longer rolling
        # 2) If the 2nd game is waiting for players, then when we do
        #    unreg the idle players here, it'll cancel the rolling of
        #    the 2nd game to pull players it - ideally we want to
        #    pull players in before we try to roll that 2nd game.
        #
        # So instead, let GameManager take care of removing from
        # rolling when we don't head to rolling

        self._stop_timeout_timer()

    def on_exit_PlayersNotReady(self, event):
        self._not_ready_players.clear()


    # --------------------------------------------------
    # Private methods
    # --------------------------------------------------
    def _start_timeout_timer(self):
        self._timeout_fire_time = (datetime.datetime.now() +
                    datetime.timedelta(0, self._pb.config.ready_timeout))
        self._pb.timer.schedule_at(self._timeout_fire_time,
                                   self._timeout_timer_cb)

    def _stop_timeout_timer(self):
        if self._pb.timer.is_scheduled(self._timeout_timer_cb):
            self._pb.timer.cancel(self._timeout_timer_cb)
        self._timeout_fire_time = None

    def _timeout_timer_cb(self):
        self.do_trigger(Trigger.TimerFired)


def _reorganize_lock(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if self._reorg_in_progress:
            return
        self._reorg_in_progress = True
        try:
            return fn(self, *args, **kwargs)
        finally:
            self._reorg_in_progress = False
    return inner


class GameManager:
    def __init__(self, pb, sport):
        self._pb = pb
        self._sport = sport

        # Create the state machine
        self._machine = transitions.Machine(None, states=State,
                                            initial=State.Empty,
                                            transitions=GAME_TRANSITIONS,
                                            send_event=True, queued=False)

        self._game_state_handlers = {
            State.Empty: self._event_game_state_empty,
            State.Quorate: self._event_game_state_quorate,
            State.PlayerCheck: self._event_game_state_player_check,
            State.PlayersNotReady: self._event_game_state_players_not_ready,
            State.Rolling: self._event_game_state_rolling,
        }

        # Dictionary of gtime -> list of games.
        # Don't use a defaultdict, to avoid bugs where code looks up
        # a gtime that isn't present and ends up adding an empty list.
        self._games = {}
        self._reorg_in_progress = False
        self._restore_in_progress = False

    def __repr__(self):
        return f"<GameManager({self._sport.name})>"


    # --------------------------------------------------
    # Public methods
    # --------------------------------------------------
    def register(self, gtime, player):
        # Make sure the user is not already in a game for this
        # time.
        if any(g for g in self._games.get(gtime, [])
               if player in g.players):
            raise BadAction(
                f"You are already registered for a game for {gtime}")

        # Check to see whether there is a game with space at this
        # time, if not, create a new one.
        if (gtime not in self._games or
            self._games[gtime][-1].state != State.NotQuorate):
            game = self._create_game(gtime)
        else:
            game = self._games[gtime][-1]

        game.add_player(player)

    def unregister(self, gtime, player):
        if gtime not in self._games:
            raise BadAction(f"There are no games for {gtime}")

        try:
            game = next(g for g in self._games[gtime]
                        if player in g.players)
        except StopIteration:
            raise BadAction(f"You are not registered for a game for {gtime}")

        game.remove_player(player)

    def set_ready_mark(self, gtime, player, mark):
        if not self._sport.is_flexible:
            raise BadAction(f"Cannot use ready for this sport")

        # Find the game
        if gtime not in self._games:
            raise BadAction(f"No game for {gtime}")

        games = [g for g in self._games[gtime] if player in g.players]
        if not games:
            raise BadAction(f"You are not present in game for {gtime}")

        game = games[0]
        if len(game.players) < self._sport.min_players and mark:
            raise BadAction(f"Need at least {self._sport.min_players} players")

        game.flexible_ready = mark

    def get_next_game(self):
        if not self._games:
            return None

        # Return the first earliest game!
        return self._games[sorted(self._games.keys())[0]][0]

    def get_game_time_index(self, game):
        return self._games[game.gtime].index(game)

    def yield_games(self):
        for game in (g for gs in self._games.values()
                       for g in gs):
            yield game

    def restore_record(self, rec):
        self._restore_in_progress = True
        try:
            game = self._create_game(GTime(rec['gtime']), True)
            game.created_time = rec['created_time']
            game.quorate_time = rec['quorate_time']
            game.db_id = rec.id
            game.add_players((self._sport.players[self._pb.user_manager.lookup_user(e)]
                             for e in rec['data']['players']),
                             flexible_ready=rec['data'].get('flexible_ready', False))
        finally:
            self._restore_in_progress = False


    # --------------------------------------------------
    # Private game state handlers
    # --------------------------------------------------
    def _game_event(self, game, start_state):
        # First do any custom state handling before announcing
        announce_game = True
        if game.state in self._game_state_handlers:
            try:
                announce_game = self._game_state_handlers[game.state](
                    game, start_state)
            except Stop:
                return

        # Announce the game if a handler hasn't already
        if announce_game:
            self._announce_game(game)

        # Now do some post announce handling

        # Game reorg! If this is a not quorate old game, then move it to now
        #
        # Else, if a player was removed, see if any players can be shuffled
        # in from other games for this time
        if game.state is State.NotQuorate:
            self._move_old_games(game.gtime)
            self._combine_games(game.gtime)

        # After we have done the announcing and re-orging, remove ourselves
        # from area in_progress queue if we have hit not Quorate via:
        # - PlayerCheck -> NotQuorate/Empty
        # - PlayerCheck -> PlayerNotReady -> NotQuorate/Empty
        #
        # See comment in on_exit_PlayerCheck for more details about why we
        # have to do it here
        if (game.state in (State.NotQuorate, State.Empty) and
            start_state in (State.PlayersNotReady, State.PlayerCheck)):
            self._sport.area.remove_from_rolling(game)

        self._save_game(game)

    def _event_game_state_empty(self, game, start_state):
        self._delete_game(game)
        # Don't announce deletes if this is during a reorg, as we may be
        # moving a game into its place.
        if not self._reorg_in_progress:
            self._sport.announce(f"Game for {game.gtime} removed!")

        # We want no further processing
        raise Stop

    def _event_game_state_quorate(self, game, start_state):
        # When we reach quorate, try to roll
        self._save_game(game)
        game.do_trigger(Trigger.Roll)
        raise Stop

    def _event_game_state_rolling(self, game, start_state):
        # Announce ASAP!
        self._announce_game(game)

        game_text = game.pretty_for_direct
        for player in game.players:
            player.user.send_msg(game_text)

        self._sport.area.game_rolled(game)
        self._delete_game(game)

        # Stop!
        raise Stop

    def _event_game_state_player_check(self, game, start_state):
        # If there are no players to wait for, then just move to
        # rolling and stop
        if game.are_players_ready:
            game.do_trigger(Trigger.PlayerReady)
            raise Stop

        # By default announce each time we hit this state
        announce = True

        # First check for any players in other games
        clashed = PlayerList(p for p in game.not_ready_players
                            if p.user.is_currently_rolled)
        if clashed:
            self._sport.announce(
                f"Unreg {clashed} as they are currently playing another game.")
            game.remove_players(clashed)

            # Don't announce the game as it'll be announced when the PlayersRemoved
            # event occurs
            announce = False

        # Only message players when we enter this state
        elif start_state is not State.PlayerCheck:
            text = template.PLAYER_IDLE.format(
                        sport=self._sport.name,
                        time=game.gtime,
                        room=self._sport.location.room.title,
                        secs=game.idle_secs_left)
            for player in game.not_ready_players:
                player.user.send_msg(text)

            # Don't announce when we enter this state if everyone
            # is good
            announce = not game.are_players_ready

        return announce

    def _event_game_state_players_not_ready(self, game, start_state):
        # Remove the idle players
        idlers = game.not_ready_players
        self._sport.announce(f"Unreg {idlers} due to idleness")
        game.remove_players(idlers)

        # Don't do anything further, as the removal will trigger
        # the game_event handling.
        raise Stop

    # --------------------------------------------------
    # Private Utils
    # --------------------------------------------------
    def _save_game(self, game):
        rec = {
            'sport':        self._sport.name,
            'gtime':        game.gtime.val,
            'created_time': game.created_time,
            'quorate_time': game.quorate_time,
            'data': {
                'players': [p.user.email for p in game.players],
            }
        }
        if game.sport.is_flexible:
            rec['data']['flexible_ready'] = game.flexible_ready
        if game.db_id is None:
            game.db_id = self._sport.location.game_table.create(rec)
        else:
            self._sport.location.game_table.update_record(
                game.db_id, rec)

    def _rearm_future_timer(self):
        if self._pb.timer.is_scheduled(self._future_timer_cb):
            self._pb.timer.cancel(self._future_timer_cb)
        now = datetime.datetime.now()
        times = sorted(t for t in self._games.keys()
                       if not t.is_for_now and t > now)
        if times:
            self._pb.timer.schedule_at(times[0].val,
                                       self._future_timer_cb)

    def _future_timer_cb(self):
        now = datetime.datetime.now()

        # Prod each old game that is waiting for the timer
        past_times = sorted(t for t in self._games.keys()
                            if not t.is_for_now and t <= now)
        LOGGER.info("Future timer fired! %s past times found",
                    len(past_times))
        for game in (g for t in past_times
                       for g in self._games[t]
                       if g.state is State.WaitingForTime):
            # If this is an flexi game, and we have the min players,
            # set ready mark so it rolls as timer fires
            if (self._sport.is_flexible and
                len(game.players) >= self._sport.min_players):
                game.flexible_ready = True
            game.do_trigger(Trigger.TimerFired)

        # See whether there are any non quorate games that
        # can be purged!
        for time in past_times:
            self._move_old_games(time)

        # Re-arm the timer for next future game
        self._rearm_future_timer()

    def _create_game(self, gtime, restore=False):
        # Don't allow a new game in the past
        if not restore and not gtime.is_for_now and gtime < datetime.datetime.now():
            raise BadAction("Cannot start a game in the past!")
        game = Game(self._pb, self._sport, self, gtime)
        self._machine.add_model(game)
        new_time = gtime not in self._games
        if new_time:
            self._games[gtime] = [game]
        else:
            self._games[gtime].append(game)

        # Re-arm the future timer as this game might be sooner than
        # the previous future game time.
        if not gtime.is_for_now and new_time:
            self._rearm_future_timer()
        return game

    def _delete_game(self, game):
        self._machine.remove_model(game)
        self._games[game.gtime].remove(game)
        if len(self._games[game.gtime]) == 0:
            del self._games[game.gtime]

            # Re-arm the future timer as this game might have been the
            # game the timer was armed for
            if not game.gtime.is_for_now:
                self._rearm_future_timer()

        # Remove game from linked players (if this game is being
        # deleted with players present, e.g. roll)
        for player in game.players:
            player.user.in_games.remove(game)

        # Make sure we definitely are not in any area queues
        self._sport.area.remove_from_rolling(game)
        self._sport.area.remove_from_queue(game)

        self._sport.location.game_table.delete_record(game.db_id)

    def _announce_game(self, game):
        self._sport.announce(game.pretty)

    @_reorganize_lock
    def _move_old_games(self, old_gtime):
        if (old_gtime not in self._games or
            old_gtime.is_for_now or
            old_gtime > datetime.datetime.now()):
            return

        LOGGER.info("Try to move old games for %s", old_gtime)

        # Move any non-quorate games. Games that are quorate leave alone
        # to preserve the player group so they can roll in peace!
        old_games = [g for g in self._games[old_gtime]
                        if g.state is State.NotQuorate]
        if old_games:
            if GTIME_NOW in self._games:
                self._games[GTIME_NOW].extend(old_games)
            else:
                self._games[GTIME_NOW] = old_games
            for game in old_games:
                self._games[old_gtime].remove(game)
                game.gtime = GTIME_NOW

                # Need to save the game now we have changed the time.
                self._save_game(game)

            # Remove time entry from list if we moved all
            # the games
            if len(self._games[old_gtime]) == 0:
                del self._games[old_gtime]

            # Now sort the games for now by creation time given we have added some
            self._games[GTIME_NOW].sort(key=lambda g: g.created_time)
            self._sport.announce(f"Changed {len(old_games)} past game(s) for {old_gtime} "
                                 "into games for now")

            # Check and remove duplicate players - players in these old games could also
            # be in a game for now, so make sure they only appear in the earliest created
            # game.
            seen_players = set()
            for game in self._games[GTIME_NOW]:
                # Get players to remove that we have in earlier games
                duplicates = [p for p in game.players if p in seen_players]

                # Update our seen players
                seen_players.update(game.players)

                # Remove the duplicates
                if duplicates:
                    game.remove_players(duplicates)

            # See whether any games for now can be combined post this.
            # The removals above won't have done a combine because we are
            # holding the re-org lock.
            self._reorg_in_progress = False
            self._combine_games(GTIME_NOW)

    @_reorganize_lock
    def _combine_games(self, gtime):
        # If there a multiple games for the combine game time, then see whether
        # they can be combined.
        if gtime not in self._games or len(self._games[gtime]) <= 1:
            return

        # Do a first pass to see whether there are gaps so we can announce only
        # if we are going to do a combine.
        if all(not g.has_space for g in self._games[gtime][:-1]):
            return

        self._sport.announce(
            f"Checking to see if any players can be promoted for games for {gtime}...")

        # Start at the first game and shuffle players down from the
        # one above, if there is space. Walk the list by index as
        # we may delete the game ahead of us if we empty it.
        games = self._games[gtime]
        idx = 0
        while idx < len(games) - 1:
            if games[idx].has_space:
                spaces = games[idx].spaces_left
                if spaces == 0:
                    spaces = len(games[idx])

                players = games[idx + 1].players[:spaces]
                games[idx + 1].remove_players(players)
                games[idx].add_players(players)
            # Move onto next game
            idx += 1


def db_rec_time_key(rec):
    if rec['quorate_time'] is None:
        ready = datetime.datetime.max
    else:
        ready = rec['quorate_time']

    return ready, rec['created_time']


def _event_dest_is_state(event, state):
    return event.transition.dest == state.name


class Stop(Exception):
    pass
