import pytest

class TestFSM:
    @pytest.fixture(scope="class")
    def game_manager(self):
        return 

    @pytest.fixture
    def game(self, game_manager):
        game = game_manager._create_game()
        yield game
        game_manager._delete_game(game)

    def test_player_added(self, game):
        pass