import pytest
import transitions
import functools

import paulobot.game

from paulobot.game import (Trigger, State)

def patch_property(fn):
    @functools.wraps(fn)
    def wrapped(s):
        return getattr(s, f"p_{fn.__name__}", False)
    return wrapped

class DummyGame(paulobot.game.Game):
    def __init__(self):
        # Initialize the properties we want to return true by default.
        self.p_has_space = True

    @property
    @patch_property
    def has_space(self):
        pass

    @property
    @patch_property
    def has_players(self):
        pass

    @property
    @patch_property
    def is_future_game(self):
        pass

    @property
    @patch_property
    def is_held(self):
        pass

    @property
    @patch_property
    def is_area_busy(self):
        pass

    @property
    @patch_property
    def has_idle_players(self):
        pass

    def on_enter_Quorate(self, event):
        pass
    

class TestFSM:
    @pytest.fixture
    def game(self):
        game = DummyGame()
        transitions.Machine(game, states=State,
                            initial=State.Empty,
                            transitions=paulobot.game.GAME_TRANSITIONS,
                            send_event=True, queued=True)
        return game

    def test_event_player_added(self, game):
        assert game.state == State.Empty

        # Test: Empty -> Empty
        game.trigger(Trigger.PlayerAdded)
        assert game.state == State.Empty

        # Test: Empty -> NotQuorate (has players)
        game.p_has_players = True
        game.trigger(Trigger.PlayerAdded)
        assert game.state == State.NotQuorate

        # Test: NotQuorate -> Quorate (no space)
        game.p_has_space = False
        game.trigger(Trigger.PlayerAdded)
        assert game.state == State.Quorate

    def test_event_player_remove(self, game):
        assert game.state == State.Empty

        # Test: Empty -> Empty
        game.trigger(Trigger.PlayerRemoved)
        assert game.state == State.Empty

        # Test: NotQuorate -> Empty
        game.state = State.NotQuorate
        game.trigger(Trigger.PlayerRemoved)
        assert game.state == State.Empty

        # Test: NotQuorate -> NotQuorate
        game.p_has_players = True
        game.state = State.NotQuorate
        game.trigger(Trigger.PlayerRemoved)
        assert game.state == State.NotQuorate

        # Test: Quorate -> NotQurate
        game.state = State.Quorate
        game.p_has_space = True
        game.trigger(Trigger.PlayerRemoved)
        assert game.state == State.NotQuorate

    def test_event_roll(self, game):
        assert game.state == State.Empty

        # Test: Quorate -> Roll
        game.state = State.Quorate
        game.trigger(Trigger.Roll)
        assert game.state == State.Rolling

    def test_state_waiting_for_time(self, game):
        game.state = State.Quorate
        game.p_is_future_game = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForTime

        # Make sure future game takes precendence
        game.state = State.Quorate
        game.p_is_future_game = True
        game.p_is_held = True
        game.p_is_area_busy = True
        game.p_has_idle_players = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForTime

        # Should return to quorate
        game.p_is_future_game = False
        game.trigger(Trigger.TimerFired)
        assert game.state == State.Quorate

    def test_state_waiting_for_hold(self, game):
        game.state = State.Quorate
        game.p_is_held = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForHold

        # Make sure it takes precedence
        game.state = State.Quorate
        game.p_is_held = True
        game.p_is_area_busy = True
        game.p_has_idle_players = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForHold

        # Should return to quorate
        game.p_is_held = False
        game.trigger(Trigger.HoldRemoved)
        assert game.state == State.Quorate

    def test_state_waiting_for_area(self, game):
        game.state = State.Quorate
        game.p_is_area_busy = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForArea

        # Make sure it takes precedence
        game.state = State.Quorate
        game.p_is_area_busy = True
        game.p_has_idle_players = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForArea

        # Should return to quorate
        game.p_is_area_busy = False
        game.trigger(Trigger.AreaReady)
        assert game.state == State.Quorate

    def test_state_waiting_for_idle(self, game):
        game.state = State.Quorate
        game.p_has_idle_players = True
        game.trigger(Trigger.Roll)
        assert game.state == State.WaitingForIdle

        # Test staying in state
        game.trigger(Trigger.PlayerUnidled)
        assert game.state == State.WaitingForIdle

        # Should return to quorate
        game.p_has_idle_players = False
        game.trigger(Trigger.PlayerUnidled)
        assert game.state == State.Quorate
