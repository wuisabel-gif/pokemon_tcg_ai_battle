"""Tests for the engine-independent MCTS adapter; no competition library is imported."""

from dataclasses import dataclass

from tools.mcts_adapter import BoundedMCTS, SparseVector, enumerate_actions


def test_enumerate_actions_is_legal_and_bounded():
    assert enumerate_actions(3, 1, 2) == [[0], [1], [2], [0, 1], [0, 2], [1, 2]]
    assert enumerate_actions(10, 0, 10, max_actions=4) == [[], [0], [1], [2]]


def test_sparse_vector_tracks_words_and_values():
    vector = SparseVector()
    vector.word_start()
    vector.add(4, 2)
    vector.advance(10)
    vector.word_start()
    vector.add_single(1)
    assert vector.index == [4, 10]
    assert vector.value == [2.0, 1.0]
    assert vector.offset == [0, 1]
    assert vector.words == 2


@dataclass
class State:
    step: int
    searchId: int = 7


class FakeGame:
    def __init__(self):
        self.closed = False

    def begin(self, observation):
        return State(0)

    def step(self, state, action):
        return State(state.step + 1)

    def terminal(self, state):
        return state.step >= 1

    def player(self, state):
        return 0

    def value(self, state, root_player):
        return 1.0 if state.step else 0.0

    def observation(self, state):
        return {"select": {"option": ["a", "b"], "minCount": 1, "maxCount": 1}}

    def end(self):
        self.closed = True


class PreferSecond:
    def evaluate(self, encoder, decoder):
        return 0.0, [0.0, 1.0]


def test_bounded_mcts_uses_model_and_closes_injected_game():
    game = FakeGame()
    search = BoundedMCTS(game, PreferSecond(), simulations=3)
    action = search.choose({}, root_player=0, encoder=lambda obs: SparseVector(), decoder=lambda obs, actions: SparseVector())
    assert action == [1]
    assert game.closed
