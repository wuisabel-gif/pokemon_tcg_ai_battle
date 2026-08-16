# Daily Competition Report — 2026-08-15

## Executive summary

The current focus is the Simulation competition (`pokemon-tcg-ai-battle`). The active production submission remains `55443071`; no new agent has been submitted.

A fresh leaderboard scan and live replay refresh were completed today:

| Metric | Today’s observation |
|---|---:|
| Leaderboard rows scanned | 4,000 |
| Our team rank | approximately **2,988** |
| Our observed score | **639.5** |
| Live episodes listed for `55443071` | **82** |
| Replays downloaded successfully | **82** |
| Replay result | **35 wins / 47 losses** |
| Parsed decisions | **5,662** |
| Replay errors | **0** |

The score has moved down from earlier observations while the policy remained unchanged. This is rating/matchmaking movement, not evidence of a code regression.

## Upper, middle, and lower leaderboard study

The leaderboard API was paginated so the study did not rely on the first page only. The current snapshot included representative ranks:

| Band | Representative ranks | Observed scores |
|---|---|---:|
| Upper | 1, 5, 10 | 1,266.7; 1,212.4; 1,175.8 |
| Middle | 500, 1,000, 1,500, 2,000 | 871.2; 793.7; 734.5; 700.3 |
| Lower / our region | 2,800; **2,988 ours**; 2,990 | 651.3; **639.5**; 639.4 |

Exploratory replay sampling across these bands showed that most upper- and lower-ranked agents use different decks from Mega Lucario ex. Their raw action choices therefore cannot be used as direct expert labels for our agent.

The useful comparison requirement is strict:

- Exact normalized 60-card deck match
- Correct selected-player seat
- Correct replay observation/action alignment
- Outcome and play-order labels
- Enough wins and losses from the same deck

The initial exploratory band sample was too small for a reliable same-deck policy comparison, and replay downloads encountered API rate limiting. The conclusion is not that higher-ranked policies have nothing to teach us; it is that cross-deck action imitation would be invalid.

## Live success and failure analysis

The current live sample for `55443071` contains 82 episodes:

- **35 wins / 47 losses**
- **5,662 parsed decisions**
- **Zero replay download/parse failures**
- **Zero replay-recorded agent errors**

After using the replay’s actual `firstPlayer` field:

| Play order | Wins | Games | Win rate |
|---|---:|---:|---:|
| First player | 21 | 54 | **38.9%** |
| Second player | 14 | 28 | **50.0%** |

The earlier apparent first/second-player gap was partly caused by confusing player-array index with actual play order. The updated live sample does not establish a first-player policy defect.

### Tempo observations

The first-action timing remains a useful hypothesis source:

| Event | Wins | Losses |
|---|---:|---:|
| First attack, average turn | 3.11 | 3.89 |
| First energy attachment, average turn | 1.46 | 1.64 |
| First evolution, average turn | 3.69 | 3.66 |

Wins reach their first attack about 0.78 turns earlier on average. The energy gap is smaller, and evolution timing is effectively equal. These observations are not causal proof because opening hands, matchup, and opponent pressure are not controlled.

### Optional selections

Optional selections (`minCount < maxCount`) were observed at similar rates:

| Outcome | Optional | Fixed | Optional rate |
|---|---:|---:|---:|
| Wins | 364 | 2,062 | **15.0%** |
| Losses | 469 | 2,767 | **14.5%** |

This does not support a universal rule to always select fewer or always select `maxCount`.

## Candidate evaluation

### Immediate-win attack candidate

The exact attack-ID mapping was corrected for the Mega Lucario deck:

- Makuhita: 976/977
- Hariyama: 978
- Solrock: 980
- Riolu: 981
- Mega Lucario ex: 982/983

The candidate was tested locally:

- First 10,000 games: 51.4%, CI 50.4–52.4%
- Second 10,000 games: 49.6%, CI 48.6–50.6%
- Combined 20,000 games: **50.49%, CI 49.80–51.18%**

It is not statistically distinguishable from baseline and remains unmerged/unsubmitted.

### Stale tactical-plan candidate

The plan-reset candidate produced:

- 1,000 games: 51.1%
- 95% CI: 48.0–54.2%

This is also inconclusive and remains unmerged/unsubmitted.

## Current interpretation

The most credible strategy signal is tempo: losses take longer to reach their first attack. However, the live sample does not identify which specific early decision causes the delay. The next analysis should compare opening hands and first three actual turns, not aggregate action counts.

The next candidate should be based on one repeated, deck-valid mistake involving:

- Active Pokémon selection
- First energy target
- Search/supporter order
- Bench development
- Evolution timing
- Energy preservation after Mega Brave

## Actions for the remaining competition period

1. Keep `55443071` as the safe Kaggle reference.
2. Do not interpret score drift as a code regression.
3. Do not submit an unchanged agent merely to create another noisy rating sample.
4. Preserve the live 82-replay refresh and continue using cached episode IDs with backoff.
5. Use loss-focused semantic diagnostics to identify a repeated exact-deck mistake.
6. Test one narrow candidate against the unchanged agent with balanced seats and a frozen opponent pool.
7. Submit only if the candidate shows repeatable improvement and no reliability regression.

## Strategy-track status

The Strategy competition report is complete at approximately 1,052 words in:

```text
docs/strategy_report.md
```

It is separate from the Simulation agent and does not change the active Kaggle submission.

## Final decision for today

No new Simulation agent should be submitted based on the current evidence. The safe production version remains `55443071`. The next score-improving action should be driven by a validated exact-deck loss pattern and the live 82-game replay sample, not leaderboard score movement or cross-deck imitation.
