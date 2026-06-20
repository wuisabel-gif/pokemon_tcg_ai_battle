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
Apple Silicon — slower but works). All args pass through to `tools/run_match.py`.

```bash
./tools/test_local.sh                              # submission vs random, 20 games
./tools/test_local.sh --a submission --b random  -n 30
./tools/test_local.sh --a submission --b baseline -n 40   # head-to-head vs the frozen baseline
```

- `baseline/` is a frozen snapshot of the original sample agent. When you improve
  `submission/`, run it against `baseline` to measure whether the change actually helps.
- Output reports **per-seat** win rate. This matters: going first is a big advantage in
  this game (the sample beats random ~100% as P0 but ~60% as P1), so always judge a
  change by its per-seat numbers, not the blended total.

### Fast, statistically sound testing (recommended)

Win rate is high-variance — a true 50/50 mirror swings 30–70% over 10 games. To tell a
real improvement from noise you need a big sample. `tools/test_parallel.py` fans out
Docker workers (the engine is entropy-seeded per process, so workers are independent)
and reports a **95% confidence interval** plus a verdict:

```bash
python3 tools/test_parallel.py --a submission --b baseline -n 1000 -j 6
```

~1000 games runs in ~20s once the image is cached. A change is only "real" when the
CI clears 50%. Rule of thumb: ~200 games detects ~7%+ effects; ~1000 games detects ~3%.

## Submitting to Kaggle

See [SUBMITTING.md](SUBMITTING.md). In short: a Kaggle notebook packages
`main.py` + `deck.csv` + the `cg` engine into `submission.tar.gz`, then you click
**Submit Agent** on the competition page.
