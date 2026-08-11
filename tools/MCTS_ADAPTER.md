# Kaggle RL/MCTS adapter (first phase)

`mcts_adapter.py` contains the reusable, engine-independent portion of the
Kiyota RL/MCTS sample. It intentionally does not import `submission.cg`,
PyTorch, weights, or any competition dependency. This makes syntax and unit
tests safe on macOS, where the shipped Linux `libcg.so` cannot load.

## Integration boundary

1. Convert the engine observation to feature words and use `SparseVector` (or
   another implementation of the model's input contract) for encoder/decoder
   inputs.
2. Inject a model implementing `evaluate(encoder, decoder)`, returning a value
   and one policy score per legal action.
3. Inject `search_begin`, `search_step`, and `search_end` using
   `make_search_game`; provide observation, terminal, player, and value
   callbacks for the engine's `SearchState` shape.
4. Call `BoundedMCTS.choose` with explicit simulation and `max_actions` bounds.

`enumerate_actions` mirrors the notebook's combination enumeration but fixes a
hard cap and validates `minCount`/`maxCount`. The adapter is not wired into
`submission/main.py` yet: the existing crash-safe heuristic remains the
production fallback until Linux-engine integration and model training are
validated separately.
