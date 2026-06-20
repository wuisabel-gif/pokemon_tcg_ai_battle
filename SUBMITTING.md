# Submitting your agent to Kaggle

This competition (`pokemon-tcg-ai-battle`) accepts a **direct tarball submission via
the Kaggle CLI** — no notebook required. The tarball must contain exactly these three
things at its root:

```
submission.tar.gz
├── main.py      # your agent  (submission/main.py)
├── deck.csv     # your deck   (submission/deck.csv)
└── cg/          # the game engine (submission/cg/, Linux .so)
```

## One command

```bash
./tools/submit.sh "short description of this version"
```

This builds a clean `submission.tar.gz` from `submission/` and submits it. Requires the
Kaggle access token at `~/.kaggle/access_token`.

## What it does under the hood

```bash
tar czf submission.tar.gz -C submission main.py deck.csv cg
~/Library/Python/3.12/bin/kaggle competitions submit \
    -c pokemon-tcg-ai-battle -f submission.tar.gz -m "your message"
```

## Checking status

```bash
~/Library/Python/3.12/bin/kaggle competitions submissions -c pokemon-tcg-ai-battle
```

A new submission shows `PENDING`, then gets a score once the matchmaking matches have
run (agent competitions score by playing your agent against others — this is not
instant). Watch the **Leaderboard** and **Submissions** tabs on the competition page.

## Limits

Check the competition **Rules** tab for the daily submission cap before burning
attempts — iterate locally with `./tools/test_parallel.py` first, and only submit a
version that beats `baseline` with the CI clearing 50%.
