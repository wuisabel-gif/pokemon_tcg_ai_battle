# Pokémon TCG AI Battle

My agent for the Kaggle competition **[The Pokémon Company – PTCG AI Battle Challenge Simulation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle)** (slug: `pokemon-tcg-ai-battle`).

## What's here

| Path | What it is |
|------|------------|
| `submission/main.py` | The agent — a deck-specific heuristic scorer (currently **Mega Lucario ex**). |
| `submission/deck.csv` | The 60-card deck the agent plays. |
| `submission/cg/` | The competition game engine (Linux `.so` + Python API). |
| `tools/run_match.py` | Runs N local battles (our agent vs random) and reports win rate. |
| `tools/test_local.sh` | Wraps the runner in a Linux Docker container (the engine can't load on macOS). |
| `sample_submission/` | The original untouched template from the competition. |
| `EN_Card_Data.csv`, `JP_Card_Data.csv` | Card reference data. |

Not tracked in git (see `.gitignore`): secrets (`.env`, `kaggle.json`), the large card PDFs, and downloaded Kaggle artifacts (`kaggle_code/`, `rl_mcts_test/`).

## How an agent works

`agent(obs_dict)` is called every time the engine needs a decision:

- **First call** (`obs.select is None`): return your 60-card deck (list of card IDs).
- **Every other call**: the engine offers `obs.select.option` (a list of legal choices —
  play a card, attach energy, attack, retreat, etc.). Return a list of option **indices**,
  length between `minCount` and `maxCount`, no duplicates.

The strong agents score every option with hand-tuned, deck-specific rules and pick the
highest-scoring ones. See `submission/cg/api.py` for the full `Observation` structure.

## Testing locally

Requires Docker Desktop running (the engine is a Linux x86-64 `.so`; it's emulated on
Apple Silicon — slower but works).

```bash
./tools/test_local.sh 20      # play 20 games vs a random opponent
```

A healthy agent beats the random opponent ~85%+.

## Submitting to Kaggle

See [SUBMITTING.md](SUBMITTING.md). In short: a Kaggle notebook packages
`main.py` + `deck.csv` + the `cg` engine into `submission.tar.gz`, then you click
**Submit Agent** on the competition page.
