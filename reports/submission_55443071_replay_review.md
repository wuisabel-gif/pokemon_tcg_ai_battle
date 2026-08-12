# Submission 55443071 replay review

## Current snapshot

The latest replay-analysis workflow was run against submission `55443071`.

| Metric | Result |
|---|---:|
| Current public score | **652.6** |
| Completed episodes | **42** |
| Wins | **16** |
| Losses | **26** |
| Overall win rate | **38.1%** |
| Actual first-player games | 12 / 31 wins (**38.7%**) |
| Actual second-player games | 4 / 11 wins (**36.4%**) |
| Parsed decisions | **5,433** |
| Replay download/parse failures | **0** |
| Replay-recorded errors | **0** |

The earlier 714.7 value was a temporary score observed while evaluation was still developing. The current public score is 652.6, so the historical peak should not be treated as the stable result.

## Important analysis correction

The first analysis used the agent array index as if it were the game’s first/second seat. That was incorrect. The updated notebook now reads `current.firstPlayer` and reports actual play order. It also uses the replay `rewards` field as the authoritative win/loss label.

The apparent seat gap is therefore much smaller than first reported:

- First player: 12/31 wins (38.7%)
- Second player: 4/11 wins (36.4%)

The sample is still imbalanced and too small for strong causal conclusions.

## What the episodes suggest

### 1. No confirmed play-order weakness yet

After correcting play-order detection, the data does not support a large first-player/second-player policy defect. The original 50% versus 22.2% comparison was an artifact of confusing player index with play order.

### 2. Optional selections are not clearly the cause

Across the replay decisions, optional selections (`minCount < maxCount`) occurred at similar rates:

- Seat index 0 wins: approximately 8.9%
- Seat index 0 losses: approximately 7.1%
- Seat index 1 wins: approximately 11.9%
- Seat index 1 losses: approximately 9.0%

This does not support a universal “always select fewer than `maxCount`” change. Optional-selection behavior should remain a context-specific experiment.

### 3. No replay-level crash pattern is visible

All 42 replays downloaded and parsed successfully, and no replay-recorded error field was present. This does not prove that the crash-safe fallback never activated, because the current wrapper does not export fallback telemetry into the replay. Local instrumentation is still needed.

### 4. Game length is not yet explanatory

Wins averaged about 10 turns and losses about 11.5 turns. The difference is not enough to identify a reliable strategy cause. The sample includes many short games and should not be used to infer a general game-length rule.

## Decision

Do **not** make a broad strategy rewrite or submit another agent version based only on this sample. The corrected evidence does not identify a specific policy defect.

Recommended next experiment:

1. Instrument fallback activations locally.
2. Decode opponent opening decks and group results by archetype.
3. Compare the first three actual turns for wins versus losses: active selection, benching, search/draw order, energy attachment, evolution, switching, and attack readiness.
4. Select one repeated concrete mistake and test one narrow policy change against a frozen opponent pool.
5. Require zero fallback activations and a meaningful confidence interval before submission.

The replay-analysis notebook produced normalized data under `data/episode_analysis/` locally. The raw replay data remains local/generated and is not committed to the repository.
