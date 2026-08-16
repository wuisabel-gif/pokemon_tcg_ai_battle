# Repository development workflow

This repository separates the production Pokémon TCG agent from research, evaluation,
and submission preparation.

## Project boundaries

| Area | Purpose |
|---|---|
| `submission/` | Current production agent, deck list, and competition engine interface. |
| `baseline/` | Frozen local comparison agent. |
| `tools/` | Reusable replay diagnostics, local evaluation, comparison, and packaging utilities. |
| `notebooks/` | Interactive Kaggle analysis and monitoring workflows. |
| `reports/` | Human-readable experiment reports and compact evidence summaries. |
| `reports/data/` | Small, intentional JSON summaries used to reproduce report numbers. |
| `tests/` | Synthetic and regression tests for portable tools. |
| `docs/` | Project diagrams and competition-track documentation. |

Raw replays, downloaded competition projects, caches, large model artifacts, and
submission archives stay local and must not be staged accidentally.

## Candidate promotion

A gameplay change follows this sequence:

```text
candidate branch
  -> focused tests and compilation
  -> balanced local evaluation against frozen baseline
  -> per-seat and reliability review
  -> replay/competition evidence
  -> explicit approval
  -> Kaggle packaging and submission
```

The production `submission/` directory is not changed merely to explore an idea.
Experimental candidates should remain isolated in their branch until the hypothesis,
validation result, and limitations are documented.

## Evaluation requirements

A candidate report should include:

- The exact policy change and its hypothesis
- Games, seats, opponents, and seeds or worker configuration where available
- Overall and per-seat results
- Confidence intervals or another uncertainty estimate
- Crashes, illegal actions, and fallback/error counts
- Whether the result is conclusive, inconclusive, or negative

A public Kaggle score is not treated as a controlled A/B result. Matchmaking, opponent
strength, and episode timing can move the score without a code change. Replay analysis
must use the authoritative reward, actual `firstPlayer`, the correct submission ID, and
chronological observation/action alignment.

## Replay-analysis rules

When comparing policies or cohorts:

1. Match the selected player by submission ID, not only by team name.
2. Require an exact normalized deck match before using actions as same-deck labels.
3. Preserve selection context, target/source information, seat, and outcome.
4. Separate disagreements in wins from disagreements in losses.
5. Treat cross-deck action differences as descriptive, not as expert labels.
6. Keep raw replay files outside Git; commit only compact summaries and reproducible code.

## Submission discipline

Kaggle submission is a separate, explicit action. Before uploading:

1. Confirm the intended commit and candidate directory.
2. Validate the archive contains only the required agent files.
3. Run the available Linux/container smoke test.
4. Record the candidate description and archive hash.
5. Keep the prior known-good submission as a reference.

Merging analysis or documentation PRs does not create a Kaggle submission and does not
change the production agent by itself.
