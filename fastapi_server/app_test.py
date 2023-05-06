from fastapi_server.app import Game, Connection
import pytest
import uuid

game_names = ["Kampvuur", "Stamhok"]


@pytest.fixture
def games():
    return [Game(name=name) for name in game_names]


def test_game_names(games):
    for name, game in zip(game_names, games):
        assert name == game.name


def test_game_connect(games):
    for game in games:
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
