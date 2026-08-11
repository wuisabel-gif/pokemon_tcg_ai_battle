"""Safe, engine-independent integration primitives for the Kaggle RL/MCTS sample.

This module deliberately has no import of ``submission.cg`` (and no torch import).
The competition engine ships a Linux-only ``libcg.so``, so these pieces can be
unit-tested on macOS and used by an optional runner that injects the engine's
``search_begin/search_step/search_end`` functions.

The adapter is intentionally a first phase, not a replacement for
``submission/main.py``:

* :func:`enumerate_actions` enumerates only legal-sized combinations and caps
  work before it becomes exponential.
* :class:`SparseVector` is the small, torch-compatible sparse bag format used by
  the notebook.  Feature extraction is supplied by callers, keeping card/API
  version details out of this module.
* :class:`BoundedMCTS` accepts an injected search/evaluation interface.  It can
  therefore be tested with a tiny fake game and only connected to the real
  engine in a Linux/Kaggle environment.

A model need only implement ``evaluate(encoder, decoder) -> (value, policy)``.
Values are from the player represented by ``root_player`` and policies must
have one score per action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import sqrt
from typing import Any, Callable, Iterable, Protocol, Sequence


@dataclass
class SparseVector:
    """Sparse EmbeddingBag input: flattened indices/values and word offsets."""

    index: list[int] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    offset: list[int] = field(default_factory=list)
    position: int = 0

    def word_start(self) -> None:
        self.offset.append(len(self.index))

    def add(self, index: int, value: float = 1.0) -> None:
        if index < 0:
            raise ValueError("sparse feature indices must be non-negative")
        if value:
            self.index.append(self.position + index)
            self.value.append(float(value))

    def advance(self, width: int) -> None:
        if width < 0:
            raise ValueError("feature width must be non-negative")
        self.position += width

    def add_single(self, value: float, *, width: int = 1) -> None:
        self.add(0, value)
        self.advance(width)

    @property
    def words(self) -> int:
        return len(self.offset)


def encode_words(words: Iterable[Iterable[tuple[int, float]]], widths: Iterable[int]) -> SparseVector:
    """Build a sparse vector from ``(feature, value)`` words and their widths."""
    result = SparseVector()
    for entries, width in zip(words, widths):
        result.word_start()
        for feature, value in entries:
            result.add(feature, value)
        result.advance(width)
    return result


def enumerate_actions(
    option_count: int,
    min_count: int,
    max_count: int,
    *,
    max_actions: int = 64,
) -> list[list[int]]:
    """Return bounded, duplicate-free legal selections from option indices.

    The engine's ``minCount``/``maxCount`` define legal action sizes.  Actions
    are emitted in deterministic lexicographic order.  ``max_actions`` is a
    hard safety bound; a model/search integration must not silently enumerate
    an unbounded power set.
    """
    if option_count < 0 or min_count < 0 or max_count < min_count:
        raise ValueError("invalid action-count bounds")
    if max_count > option_count:
        raise ValueError("max_count exceeds option_count")
    if max_actions <= 0:
        raise ValueError("max_actions must be positive")
    actions: list[list[int]] = []
    for size in range(min_count, max_count + 1):
        for action in combinations(range(option_count), size):
            if len(actions) >= max_actions:
                return actions
            actions.append(list(action))
    return actions


class Model(Protocol):
    def evaluate(self, encoder: SparseVector, decoder: SparseVector) -> tuple[float, Sequence[float]]: ...


class SearchGame(Protocol):
    def begin(self, observation: Any) -> Any: ...
    def step(self, state: Any, action: list[int]) -> Any: ...
    def terminal(self, state: Any) -> bool: ...
    def player(self, state: Any) -> int: ...
    def value(self, state: Any, root_player: int) -> float: ...
    def observation(self, state: Any) -> Any: ...


@dataclass
class _Node:
    state: Any | None
    parent: _Node | None
    action: list[int] | None = None
    prior: float = 0.0
    visits: int = 0
    total: float = 0.0
    children: list[_Node] = field(default_factory=list)


class BoundedMCTS:
    """Small PUCT search with explicit simulation and action-count bounds."""

    def __init__(self, game: SearchGame, model: Model, *, simulations: int = 10, c_puct: float = 0.4, max_actions: int = 64):
        if simulations < 1 or max_actions < 1:
            raise ValueError("simulations and max_actions must be positive")
        self.game, self.model = game, model
        self.simulations, self.c_puct, self.max_actions = simulations, c_puct, max_actions

    def choose(self, observation: Any, *, root_player: int, encoder: Callable[[Any], SparseVector], decoder: Callable[[Any, list[list[int]]], SparseVector]) -> list[int]:
        root_state = self.game.begin(observation)
        try:
            root = _Node(root_state, None)
            for _ in range(self.simulations):
                node = root
                while True:
                    if self.game.terminal(node.state):
                        value = self.game.value(node.state, root_player)
                        break
                    if not node.children:
                        value = self._expand(node, root_player, encoder, decoder)
                        break
                    child = max(node.children, key=lambda c: self._score(node, c, root_player))
                    if child.state is None:
                        child.state = self.game.step(node.state, child.action or [])
                    node = child
                self._backprop(node, value)
            if not root.children:  # Defensive fallback for an unusual terminal state.
                return []
            return max(root.children, key=lambda child: child.visits).action or []
        finally:
            close = getattr(self.game, "end", None)
            if close is not None:
                close()

    def _expand(self, node: _Node, root_player: int, encoder: Callable, decoder: Callable) -> float:
        if self.game.terminal(node.state):
            return self.game.value(node.state, root_player)
        obs = self.game.observation(node.state)
        select = getattr(obs, "select", None) if not isinstance(obs, dict) else obs.get("select")
        if select is None:
            raise ValueError("search observation has no selection context")
        options = getattr(select, "option", None) if not isinstance(select, dict) else select.get("option")
        lo = getattr(select, "minCount", None) if not isinstance(select, dict) else select.get("minCount")
        hi = getattr(select, "maxCount", None) if not isinstance(select, dict) else select.get("maxCount")
        if options is None or lo is None or hi is None:
            raise ValueError("selection context is missing option/count fields")
        actions = enumerate_actions(len(options), lo, hi, max_actions=self.max_actions)
        value, policy = self.model.evaluate(encoder(obs), decoder(obs, actions))
        if len(policy) != len(actions):
            raise ValueError("model policy length does not match legal actions")
        priors = [float(p) for p in policy]
        if priors:
            scale = sum(max(0.0, p) for p in priors) or 1.0
            priors = [max(0.0, p) / scale for p in priors]
        # Delay Search API advancement until a simulation actually selects a
        # child. Advancing every candidate here exhausts the engine's search
        # state and is not equivalent to the Kaggle sample's lazy children.
        node.children = [_Node(None, node, action, prior) for action, prior in zip(actions, priors)]
        return float(value)

    def _score(self, parent: _Node, child: _Node, root_player: int) -> float:
        mean = child.total / child.visits if child.visits else 0.0
        if self.game.player(parent.state) != root_player:
            mean = -mean
        return mean + self.c_puct * child.prior * sqrt(max(1, parent.visits)) / (1 + child.visits)

    @staticmethod
    def _backprop(node: _Node, value: float) -> None:
        while node is not None:
            node.visits += 1
            node.total += value
            node = node.parent


def make_search_game(search_begin: Callable, search_step: Callable, search_end: Callable, *, observation: Callable[[Any], Any] = lambda state: state, terminal: Callable[[Any], bool] = lambda state: False, player: Callable[[Any], int] = lambda state: 0, value: Callable[[Any, int], float] = lambda state, root: 0.0) -> SearchGame:
    """Adapt Kaggle ``search_begin/step/end`` functions without importing them."""
    class _Injected:
        def begin(self, obs): return search_begin(obs)
        def step(self, state, action): return search_step(state.searchId, action)
        def terminal(self, state): return terminal(state)
        def player(self, state): return player(state)
        def value(self, state, root): return value(state, root)
        def observation(self, state): return observation(state)
        def end(self): search_end()
    return _Injected()
