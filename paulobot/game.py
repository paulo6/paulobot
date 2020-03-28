import enum
import transitions
import datetime


class State(enum.Enum):
    Empty          = enum.auto()
    NotQuorate     = enum.auto()
    Quorate        = enum.auto()
    WaitingForTime = enum.auto()
    WaitingForHold = enum.auto()
    WaitingForArea = enum.auto()
    PlayerCheck    = enum.auto()
    Rolling        = enum.auto()


class Trigger:
    PlayerAdded   = "_trig_player_added"
    PlayerRemoved = "_trig_player_removed"
    TimerFired    = "_trig_timer_fired"
    AreaReady     = "_trig_area_ready"
    HoldAdded     = "_trig_hold_added"
    HoldRemoved   = "_trig_hold_removed"
    PlayerReady   = "_trig_player_ready"
    Roll          = "_trig_roll"


# Functions that block going into PlayerCheck state
PLAYER_CHECK_BLOCKERS = ['is_future_game', 'is_held', 'is_area_busy']


GAME_TRANSITIONS = [
    # Player added transitions
    { 
        'trigger': Trigger.PlayerAdded,   'source': State.Empty,      'dest': State.NotQuorate,
        'conditions': ['has_players']
    },
    { 
        'trigger': Trigger.PlayerAdded,   'source': State.NotQuorate, 'dest': State.NotQuorate,
        'conditions': ['has_space']
    },
    { 
        'trigger': Trigger.PlayerAdded,   'source': State.NotQuorate, 'dest': State.Quorate,
        'unless': ['has_space']
    },

    # Player removed transitions
    { 
        'trigger': Trigger.PlayerRemoved, 'source': '*',              'dest': State.NotQuorate,
        'conditions': ['has_players'] 
    },
    { 
        'trigger': Trigger.PlayerRemoved, 'source': State.NotQuorate, 'dest': State.Empty,
        'unless': ['has_players'] 
    },

    # Hold transitions - hold can be applied in any state
    {
        'trigger': Trigger.HoldAdded,     'source': State.NotQuorate,            'dest': State.NotQuorate,
    },
    {
        'trigger': Trigger.HoldAdded,     'source': State.WaitingForTime,        'dest': State.WaitingForTime,
    },
    {
        'trigger': Trigger.HoldAdded,     'source': State.WaitingForArea,        'dest': State.WaitingForHold,
    },
    {
        'trigger': Trigger.HoldAdded,     'source': State.PlayerCheck,           'dest': State.WaitingForHold,
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
        'trigger': Trigger.HoldRemoved,   'source': State.WaitingForHold,       'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },
    {
        'trigger': Trigger.HoldRemoved,   'source': State.WaitingForHold,       'dest': State.Quorate,
    },

    {
        'trigger': Trigger.AreaReady,     'source': State.WaitingForArea,       'dest': State.PlayerCheck,
        'unless': PLAYER_CHECK_BLOCKERS,
    },
    {
        'trigger': Trigger.AreaReady,     'source': State.WaitingForArea,       'dest': State.Quorate,
    },

    # Can only move out of PlayerCheck if there are no idle players
    {
        'trigger': Trigger.PlayerReady,   'source': State.PlayerCheck,          'dest': State.Rolling,
        'conditions': ['players_ready']
    },
]


class StateException(Exception):
    """
    Exception raised when a bad state transition happens.

    """
    pass


class Game:
    def __init__(self, sport, time=None):
        self.sport = sport
        self._players = set()
        self._not_ready_players = set()
        self._max_players = sport.max_players
        self._time = time
        self._hold_info = None
        self._in_area_queue = False

    # --------------------------------------------------
    # Properties
    # --------------------------------------------------
    @property
    def has_space(self):
        return self._max_players == 0 or len(self._players) < self._max_players

    @property
    def has_players(self):
        return len(self._players) > 0

    @property
    def is_future_game(self):
        return self._time is not None and self._time > datetime.datetime.now()

    @property
    def is_held(self):
        return self._hold_info is not None

    @property
    def is_area_busy(self):
        return self.sport.area.is_busy(self)

    @property
    def players_ready(self):
        return len(self._not_ready_players) == 0


    # --------------------------------------------------
    # Methods for changing game state
    # --------------------------------------------------
    def add_player(self, player):
        if self.has_space:
            self._players.add(player)
            self.trigger(Trigger.PlayerAdded) # pylint: disable=no-member

    def remove_player(self, player):
        if player in self._players:
            self._players.discard(player)
            self.trigger(Trigger.PlayerRemoved) # pylint: disable=no-member

    def add_hold(self, player, reason):
        self._hold_info = (player, reason)
        self.trigger(Trigger.HoldAdded) # pylint: disable=no-member

    def remove_hold(self):
        if self._hold_info is not None:
            self._hold_info = None
            self.trigger(Trigger.HoldRemoved) # pylint: disable=no-member
            

    # --------------------------------------------------
    # State machine callbacks - should *not* be called
    # directly!
    # --------------------------------------------------
    def on_enter_Quorate(self, event):
        # Whenever we enter quorate state, try to roll
        self._trig_roll() # pylint: disable=no-member

    def on_exit_Rolling(self, event):
        raise StateException("Can't leave rolling state")

    def on_enter_WaitingForArea(self, event):
        self.sport.area.add_to_queue(self)

    def on_exit_WaitingForArea(self, event):
        # If we leave waiting for area and do not go to
        # player check, then remove from qyeye
        if event.transition.dest is not State.PlayerCheck:
            self.sport.area.remove_from_queue(self)

    def on_enter_WaitingForTime(self, event):
        # @@@ Start timer
        pass

    def on_exit_WaitingForTime(self, event):
        # @@@ Stop timer
        pass

    def on_enter_PlayerCheck(self, event):
        # First check whether any players are in another rolled game.
        # If so don't do anything else, and let the game manager remove
        # them.
        self._not_ready_players = {
            p for p in self._players if p.is_currently_rolled
        }

        # If there are no clashed players, then count ourselves as rolling
        # from now, so another game doesn't jump the queue whilst we wait
        # for people to ready up.
        if self.players_ready():
            # Count ourselves as rolling from now, so another game
            # don't jump ahead just because we are waiting for our
            # players.
            #
            # The game manager will take care of messaging players.
            self.sport.area.add_to_rolling(self)
            self._not_ready_players = {p for p in self._players if p.is_idle}

            if not self.players_ready():
                # @@@ Start timer
                pass

    def on_exit_PlayerCheck(self, event):
        # Clear not ready players set.
        self._not_ready_players = set()

        # Remove ourselves from the rolling list if we are not
        # rolling.
        if event.transition.dest is not State.Rolling:
            self.sport.area.remove_from_queue(self)

        # @@@ Stop timer


class GameManager:
    def __init__(self, sport):
        self._sport = sport

        # Create the state machine
        self._machine = transitions.Machine(None, states=State,
                                            initial=State.Empty,
                                            transitions=GAME_TRANSITIONS,
                                            send_event=True, queued=True,
                                            finalize_event=self._finalize_event)

    def _finalize_event(self, event):
        if event.model.state is State.Empty:
            # @@@ game is empty, delete it!
            pass

        if event.model.state is State.Rolling:
            # @@@ Let's roll
            pass

        if event.model.state is State.PlayerCheck:
            # @@@ Remove clashed players, announce idlers
            pass

    def _create_game(self):
        game = Game(self._sport)
        self._machine.add_model(game)
        return game

    def _delete_game(self, game):
        self._machine.remove_model(game)
