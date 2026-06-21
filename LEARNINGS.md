# What I learned building a Pokémon TCG battle agent

This is the honest writeup of a Kaggle run: what I tried, what worked, and the
thing that took eight failed experiments to finally understand.

## The setup

The competition asks you to submit an agent that plays Pokémon TCG. The organizers
hand you sample agents — rule-based Python, one per deck archetype, each scoring
around 600 on the leaderboard. I took the Mega Lucario ex sample, got it running,
and started from there.

The first real work wasn't the agent. It was the testing.

The game engine ships as a Linux binary, so it won't run on a Mac directly. I
wrapped it in Docker and wrote a self-play harness: two agents, many games, win
rate with a confidence interval. That last part matters more than it sounds.
Win rate in this game is wild — a mirror match of identical agents swings between
30% and 70% over ten games. Without a confidence interval you are reading noise
and calling it signal. With one, and a thousand games, you can actually tell a
real change from luck. Every conclusion below rests on that harness.

## Getting on the board

I submitted the working Lucario agent and it landed at **674**. Mid-pack — rank
~1,279 of 2,480. Reading its match history later told a clean story: it beats
opponents rated below ~650 and loses to those above ~700. That is exactly what a
674 rating means. Nothing broken, nothing unlucky. A fair, average agent.

Then I tried to climb. This is where it gets instructive.

## Eight experiments, all neutral

I changed things I was sure would help, measured each over a thousand games
against the frozen baseline, and watched them do nothing:

- Tuned the attack-target scoring. Neutral.
- Removed a penalty that discouraged attacking near the win. Neutral.
- Made that penalty conditional. Neutral.
- Pointed the engine's built-in lookahead at attack choice. Neutral.
- Pointed it at target selection. Neutral.
- Fixed a real deckbuilding flaw — four copies of the attacker, only three of the
  basic it evolves from. Neutral.
- Traded a card. Neutral.
- Traded a different card. Neutral.

Eight in a row. At that point I wrote it off: the sample must be near-optimal, the
well is dry, accept the median. That conclusion was wrong, and the replay data
proved it.

## The thing that changed everything

The competition publishes replays — every match, the moves both agents made. The
first move of any game is the agent returning its 60-card deck. So I mined a
sample of players, pulled their decks, and matched each to its leaderboard score.

The top of the board plays Mega Lucario ex. My deck. One player scoring **1,102**
runs the *identical* sixty cards — every count the same as the sample I started
from. Another, at 1,148, differs by a single card.

So the deck is not the problem. The deck is correct. The 674-to-1,100 gap is
entirely decision quality — the same cards, played far better. My eight neutral
experiments hadn't found a local optimum. They had just been too small to matter.
There was 400 points of room the whole time, sitting in the logic.

## The search agent that didn't work

If the gap is logic, give it a better brain. The engine exposes a forward
simulator, so I built an agent that looks ahead: at each turn it rolls the turn
out to its end, scores the resulting board, and plays the line that lands best. A
real lookahead agent, not a heuristic tweak.

It lost. 44% against the baseline — worse than the thing it was trying to beat.

The reason is worth keeping. A shallow search is only as good as the function that
scores the end position, and my scoring function was cruder than the sample's
hand-tuned judgment. When I let search override the heuristic, it traded good
nuanced play for greedy prize-grabbing. Restricting it to override only when it
could prove an extra prize pulled it back to even. Even, not ahead.

## What I actually learned

A well-tuned heuristic is hard to beat, and "hard to beat" has a specific shape:
small changes vanish into the noise, and a clever-looking upgrade can quietly make
things worse. The only way to know which is which is to measure, at scale, against
a fixed opponent. Intuition was wrong here more often than it was right. The
confidence interval was the only thing that kept me honest.

The gap to the top is real and it is closeable, but not with tweaks. It needs a
genuinely better evaluator — a value function learned from outcomes, or a search
that models the opponent's reply instead of ignoring it. That is a research
project, and naming it as one is its own kind of progress. Knowing the difference
between "I haven't tuned this enough" and "this needs a different method" saves you
from a hundred more neutral experiments.

The agent sits at 674. The deck is right, the toolchain is solid, and the path up
is mapped even though I didn't walk it.

## What's in here

- `submission/` — the working agent: `main.py`, `deck.csv`, and the engine.
- `tools/test_parallel.py` — self-play vs a baseline with a 95% confidence interval.
- `tools/submit.sh` — package and submit in one command.
- `tools/mine_meta.py` — pull decks and archetypes out of the replay data.
- `baseline/` — the frozen reference every change is measured against.
- The `search-agent` branch — the lookahead agent, kept for anyone who wants to
  give the value function the upgrade it needs.
