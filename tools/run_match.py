"""Local match runner for the PTCG AI Battle agent.

Plays N battles between two agents and reports agent A's win rate. Each agent is
loaded as an isolated module (its own globals + its own deck), so you can pit a
modified agent against the fixed baseline and measure whether a change actually
helped. The special name "random" uses a random-move opponent.

Must run on Linux/x86-64 (the cg engine is a Linux .so), so invoke it via
tools/test_local.sh which wraps it in Docker.

Usage (inside container):
    python tools/run_match.py [--a DIR] [--b DIR|random] [-n N]

Examples:
    python tools/run_match.py --a submission --b random   -n 20
    python tools/run_match.py --a submission --b baseline  -n 40
"""
import os
import sys
import random
import argparse
import importlib.util

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The cg engine is shared; make it importable for every agent module.
sys.path.insert(0, os.path.join(REPO, "submission"))
from cg.game import battle_start, battle_finish, battle_select  # noqa: E402


def load_agent(name: str):
    """Load an agent by directory name. Returns (callable, deck_list).

    Each agent's main.py reads "deck.csv" relative to CWD at import time, so we
    chdir into its directory while importing to capture the right deck, then
    restore CWD. Module globals stay isolated per agent.
    """
    if name == "random":
        def random_agent(obs_dict):
            sel = obs_dict["select"]
            return random.sample(range(len(sel["option"])), sel["maxCount"])
        # Random opponent still needs a legal deck; reuse the baseline deck.
        deck = read_deck(os.path.join(REPO, "submission", "deck.csv"))
        return random_agent, deck

    agent_dir = os.path.join(REPO, name)
    deck = read_deck(os.path.join(agent_dir, "deck.csv"))
    prev_cwd = os.getcwd()
    os.chdir(agent_dir)
    try:
        spec = importlib.util.spec_from_file_location(f"agent_{name}", os.path.join(agent_dir, "main.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(prev_cwd)
    return mod.agent, deck


def read_deck(path: str) -> list[int]:
    with open(path) as f:
        rows = f.read().split("\n")
    return [int(rows[i]) for i in range(60)]


def play_one(agent_a, deck_a, agent_b, deck_b, a_index: int) -> int:
    """Play one battle with agent A seated at a_index. Returns 1 if A wins."""
    deck0, deck1 = (deck_a, deck_b) if a_index == 0 else (deck_b, deck_a)
    obs, _ = battle_start(deck0, deck1)
    while obs["current"]["result"] < 0:
        turn_player = obs["current"]["yourIndex"]
        act = agent_a(obs) if turn_player == a_index else agent_b(obs)
        obs.pop("search_begin_input", None)
        obs = battle_select(act)
    result = obs["current"]["result"]
    battle_finish()
    return 1 if result == a_index else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="submission", help="agent A directory (the one under test)")
    ap.add_argument("--b", default="random", help="agent B directory, or 'random'")
    ap.add_argument("-n", type=int, default=20, help="number of games")
    args = ap.parse_args()

    agent_a, deck_a = load_agent(args.a)
    agent_b, deck_b = load_agent(args.b)

    wins = 0
    seat_wins = [0, 0]   # A's wins when seated at index 0 / 1
    seat_games = [0, 0]
    for g in range(args.n):
        a_index = g % 2  # alternate sides to cancel first-player advantage
        w = play_one(agent_a, deck_a, agent_b, deck_b, a_index)
        wins += w
        seat_wins[a_index] += w
        seat_games[a_index] += 1
        print(f"  game {g + 1}/{args.n} (A wins so far: {wins})", flush=True)

    rate = wins / args.n
    print(f"\n[{args.a}] vs [{args.b}]: {wins}/{args.n} = {rate:.1%} win rate for A")
    for seat in (0, 1):
        if seat_games[seat]:
            print(f"    as player {seat}: {seat_wins[seat]}/{seat_games[seat]} = "
                  f"{seat_wins[seat] / seat_games[seat]:.1%}")


if __name__ == "__main__":
    main()
