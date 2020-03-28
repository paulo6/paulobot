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
    WaitingForIdle = enum.auto()
    Rolling        = enum.auto()


class Trigger:
    PlayerAdded   = "_trig_player_added"
    PlayerRemoved = "_trig_player_removed"
    TimerFired    = "_trig_timer_fired"
    AreaReady     = "_trig_area_ready"
    PlayerUnidled = "_trig_player_unidled"
    HoldRemoved   = "_trig_hold_removed"
    Roll          = "_trig_roll"
    

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

    # Roll transitions
    #   Make sure that we priotise waiting states in this order:
    #     - Time
    #     - Hold
    #     - Area
    #     - Idle
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForTime,
        'conditions': ['is_future_game'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForHold,
        'conditions': ['is_held'],        'unless': ['is_future_game'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForArea,
        'conditions': ['is_area_busy'],   'unless': ['is_future_game', 'is_held'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.WaitingForIdle,
        'conditions': ['has_idle_players'], 'unless': ['is_future_game', 'is_held', 'is_area_busy'],
    },
    {
        'trigger': Trigger.Roll,          'source': State.Quorate,             'dest': State.Rolling,
        'unless': ['is_future_game', 'is_held', 'is_area_busy', 'has_idle_players'],
    },

    # Remove WaitingForxxx triggers
    {
        'trigger': Trigger.TimerFired,    'source': State.WaitingForTime,       'dest': State.Quorate,
    },
    {
        'trigger': Trigger.HoldRemoved,   'source': State.WaitingForHold,       'dest': State.Quorate,
    },
    {
        'trigger': Trigger.AreaReady,     'source': State.WaitingForArea,       'dest': State.Quorate,
    },
    {
        'trigger': Trigger.PlayerUnidled, 'source': State.WaitingForIdle,       'dest': State.Quorate,
        'unless': ['has_idle_players'],
    },
]


class StateException(Exception):
    """
    Exception raised when a bad state transition happens.

    """
    pass


class Game:
    def __init__(self, sport, time=None):
        self._players = set()
        self._max_players = sport.max_players
        self._time = time

    @property
    def has_space(self):
        return self._max_players == 0 or len(self._players) < self._max_players

    @property
    def has_players(self):
        return len(self._players) > 0

    @property
    def is_future_game(self):
        return False

    @property
    def is_held(self):
        return False

    @property
    def is_area_busy(self):
        return False

    @property
    def has_idle_players(self):
        return False

    def add_player(self, player):
        if self.has_space:
            self._players.add(player)
            self._trig_player_added() # pylint: disable=no-member

    def remove_player(self, player):
        self._players.discard(player)
        self._trig_player_removed() # pylint: disable=no-member

    # State machine callbacks
    def on_enter_Quorate(self, event):
        # Whenever we enter quorate state, try to roll
        self._trig_roll() # pylint: disable=no-member

    def on_exit_Rolling(self, event):
        raise StateException("Can't leave rolling state")


class GameManager:
    def __init__(self, sport):
        self._sport = sport

        # Create the state machine
        self._machine = transitions.Machine(None, states=State,
                                            initial=State.Empty,
                                            transitions=GAME_TRANSITIONS,
                                            send_event=True, queued=True,
                                            finalize_event=self._finalize_event)

    def _finalize_event(self, event_data):
        pass

    def _create_game(self):
        game = Game(self._sport)
        self._machine.add_model(game)
        return game

    def _delete_game(self, game):
        self._machine.remove_model(game)
