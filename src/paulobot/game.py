import enum
import transitions
import datetime

class State(enum.Enum):
    Empty          = enum.auto(),
    NotQuorate     = enum.auto(),
    Quorate        = enum.auto(),
    WaitingForTime = enum.auto(),
    WaitingForHold = enum.auto(),
    WaitingForArea = enum.auto(),
    WaitingForIdle = enum.auto(),
    Rolling        = enum.auto(),

class Trigger(enum.Enum):
    PlayerAdded   = enum.auto(),
    PlayerRemoved = enum.auto(),
    TimerFired    = enum.auto(),
    AreaReady     = enum.auto(),
    PlayerUnidled = enum.auto(),
    HoldRemoved   = enum.auto(),
    Roll          = enum.auto(),
    


GAME_STATES = [
    {'name': State.Empty, }
]

GAME_TRANSITIONS = [
    # Player added transitions
    { 
        'trigger': Trigger.PlayerAdded,   'source': State.Empty,      'dest': State.NotQuorate 
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
    }
]


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
        return self._players

    @property
    def has_idle_players(self):
        return False

    @property
    def is_future_game(self):
        return False

    def add_player(self, player):
        if self.has_space:
            self._players.add(player)
            self.PlayerAdded() # pylint: disable=no-member

    # State machine callbacks
    def on_enter_Quorate(self, event):
        # Whenever we enter quorate state, try to roll
        self.Roll() # pylint: disable=no-member


class GameManager:
    def __init__(self, sport):
        self._sport = sport

        # Create the state machine
        self._machine = transitions.Machine(self, states=GAME_STATES,
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
