"""Verify the agent's search_attack_values actually runs (returns non-empty)."""
import os, sys, importlib.util, time

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission")
sys.path.insert(0, SUB); os.chdir(SUB)
from cg.game import battle_start, battle_select, battle_finish  # noqa
from cg.api import to_observation_class, OptionType  # noqa

spec = importlib.util.spec_from_file_location("am", os.path.join(SUB, "main.py"))
am = importlib.util.module_from_spec(spec); spec.loader.exec_module(am)

with open("deck.csv") as f:
    DECK = [int(x) for x in f.read().split("\n")[:60]]

print("_SEARCH_AVAILABLE =", am._SEARCH_AVAILABLE)
obs = battle_start(DECK, DECK)[0]
checks = 0
for step in range(400):
    if obs["current"]["result"] >= 0:
        break
    o = to_observation_class(obs)
    if o.select and any(op.type == OptionType.ATTACK for op in o.select.option):
        t = time.time()
        vals = am.search_attack_values(o)
        dt = (time.time() - t) * 1000
        atk_opts = [i for i, op in enumerate(o.select.option) if op.type == OptionType.ATTACK]
        print(f"turn {o.current.turn}: attack options at idx {atk_opts} -> "
              f"search returned {vals}  ({dt:.1f} ms)")
        checks += 1
        if checks >= 5:
            break
    obs.pop("search_begin_input", None)
    obs = battle_select(am.agent(obs))
battle_finish()
print(f"\nChecked {checks} attack decisions. "
      + ("SEARCH WORKING (non-empty)." if checks else "no attack decisions hit."))
