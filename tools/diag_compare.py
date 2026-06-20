"""Diagnostic: how often does the sample agent's pick match strong same-deck play?

Replays each strong Lucario player's decisions in order, runs the sample agent on
the identical observation, and tallies exact-match agreement by decision context.

CAVEAT (important): exact-move agreement turned out to be NOISE, not signal. The
sample agreed ~13% with ~1100 players AND ~13% with a ~700 peer — flat across skill.
Many decisions have equivalent options (ties, orderings, which-of-two-identical), so
"different" does not mean "worse". Do NOT use this to pinpoint mistakes. The infra
(replaying real observations through the agent) is still reusable for outcome-based
analysis (e.g. scoring the chosen move via the Search API).

Run in Docker with episodes mounted at /eps.
"""
import os, sys, json, importlib.util, collections

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission")
sys.path.insert(0, SUB); os.chdir(SUB)
from cg.api import SelectContext  # noqa

CTX = {int(c): c.name for c in SelectContext}

spec = importlib.util.spec_from_file_location("am", os.path.join(SUB, "main.py"))
am = importlib.util.module_from_spec(spec); spec.loader.exec_module(am)

strong = json.load(open(os.environ.get("LIST", "/eps/_strong.json")))
by_ctx = collections.defaultdict(lambda: [0, 0])   # context -> [agree, total]
examples = collections.defaultdict(list)

for fname, idx, score, name in strong:
    d = json.load(open(f"/eps/{fname}"))
    for step in d["steps"]:
        cell = step[idx]
        act = cell.get("action")
        ob = cell.get("observation")
        if not (isinstance(act, list) and isinstance(ob, dict) and ob.get("select")):
            continue
        if len(act) == 60:   # deck submission
            continue
        try:
            mine = am.agent(ob)
        except Exception:
            continue
        ctx = ob["select"].get("context")
        agree = set(mine) == set(act)
        by_ctx[ctx][1] += 1
        if agree:
            by_ctx[ctx][0] += 1
        elif len(examples[ctx]) < 3:
            examples[ctx].append((act, mine, ob["select"].get("maxCount")))

rows = sorted(by_ctx.items(), key=lambda kv: (kv[1][1] - kv[1][0]), reverse=True)
tot_a = sum(a for a, _ in by_ctx.values()); tot_n = sum(n for _, n in by_ctx.values())
print(f"Compared {tot_n} strong decisions across {len(strong)} games.")
print(f"Overall agreement: {tot_a}/{tot_n} = {tot_a/tot_n:.0%}\n")
print(f"{'context':<26}{'agree%':>7}{'disagrees':>11}")
print("-" * 46)
for ctx, (a, n) in rows:
    print(f"{CTX.get(ctx, ctx):<26}{a/n*100:6.0f}%{n-a:>11}  (n={n})")
print("\n=== sample disagreements in the top-2 contexts ===")
for ctx, _ in rows[:2]:
    print(f"\n[{CTX.get(ctx, ctx)}] strong_pick vs sample_pick (maxCount):")
    for act, mine, mc in examples[ctx]:
        print(f"   strong={act}  sample={mine}  (max {mc})")
