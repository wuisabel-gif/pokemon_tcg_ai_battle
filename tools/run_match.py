"""Local match runner for the PTCG AI Battle agent.

Runs N battles of our agent (submission/main.py) against a random opponent,
using the cg.game engine. Must run on Linux/x86-64 (the cg engine is a Linux
.so), so invoke it via tools/test_local.sh which wraps it in Docker.

Usage (inside container):  python tools/run_match.py [n_games]
"""
import os
import sys
import random
import importlib.util

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = os.path.join(REPO, "submission")

# The agent resolves "deck.csv" relative to CWD, and imports `cg` from CWD.
sys.path.insert(0, SUB)
os.chdir(SUB)

from cg.game import battle_start, battle_finish, battle_select  # noqa: E402

# Load submission/main.py as a module so we can call its agent() function.
spec = importlib.util.spec_from_file_location("agent_mod", os.path.join(SUB, "main.py"))
agent_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_mod)
agent_fn = agent_mod.agent


def random_agent(obs_dict: dict) -> list[int]:
    sel = obs_dict["select"]
    return random.sample(range(len(sel["option"])), sel["maxCount"])


def load_deck() -> list[int]:
    with open("deck.csv") as f:
        rows = f.read().split("\n")
    return [int(rows[i]) for i in range(60)]


def play_one(deck: list[int], our_index: int) -> int:
    """Play a single battle. Returns 1 if our agent wins, 0 otherwise."""
    obs, _ = battle_start(deck, deck)
    while obs["current"]["result"] < 0:
        turn_player = obs["current"]["yourIndex"]
        act = agent_fn(obs) if turn_player == our_index else random_agent(obs)
        obs.pop("search_begin_input", None)
        obs = battle_select(act)
    result = obs["current"]["result"]
    battle_finish()
    return 1 if result == our_index else 0


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    deck = load_deck()
    wins = 0
    for g in range(n):
        # Alternate which side our agent plays, to balance first-player advantage.
        our_index = g % 2
        wins += play_one(deck, our_index)
        print(f"  game {g + 1}/{n} done (running wins: {wins})", flush=True)
    print(f"\nMega Lucario agent vs Random: {wins}/{n} wins = {wins / n:.0%}")


if __name__ == "__main__":
    main()
