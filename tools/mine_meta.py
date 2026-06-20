"""Mine the competition metagame from episode replays.

Given a directory of downloaded episode JSONs and the leaderboard CSV, extracts
each player's 60-card deck (their first action), identifies the headliner Pokemon,
joins to leaderboard score, and reports the top archetypes + deck diffs vs our deck.

This analysis produced the session's key finding: top players run Mega Lucario ex
(same as us) and even the identical decklist scores ~1100 vs our 706 — so the gap
is decision LOGIC, not the deck.

Usage (host Python, no Docker needed):
    python3 tools/mine_meta.py /tmp/eps /tmp/lb/pokemon-tcg-ai-battle.zip

Download episodes first, e.g.:
    kaggle datasets files  kaggle/pokemon-tcg-ai-battle-episodes-<DATE>
    kaggle datasets download kaggle/pokemon-tcg-ai-battle-episodes-<DATE> -f <id>.json -p /tmp/eps
    kaggle competitions leaderboard -c pokemon-tcg-ai-battle --download -p /tmp/lb
"""
import sys, os, csv, json, glob, io, zipfile, collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eps_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/eps"
lb_zip = sys.argv[2] if len(sys.argv) > 2 else "/tmp/lb/pokemon-tcg-ai-battle.zip"

card = {}
with open(os.path.join(REPO, "EN_Card_Data.csv"), newline="") as f:
    for r in csv.DictReader(f):
        try:
            card[int(r["Card ID"])] = (r["Card Name"], r["Stage (Pokémon)/Type (Energy and Trainer)"], r["Rule"])
        except Exception:
            pass

z = zipfile.ZipFile(lb_zip)
lb = {r["TeamName"]: float(r["Score"])
      for r in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode()))}


def headliner(deck):
    c = []
    for cid in set(deck):
        if cid in card and "Pokémon" in card[cid][1]:
            name, stage, rule = card[cid]
            c.append(("Stage 2" in stage, "ex" in (rule or "").lower(), deck.count(cid), name))
    c.sort(reverse=True)
    return c[0][3] if c else "?"


players = {}
for fn in glob.glob(os.path.join(eps_dir, "*.json")):
    if os.path.basename(fn).startswith("_"):
        continue
    try:
        d = json.load(open(fn))
        for i in range(2):
            nm = d["info"]["Agents"][i]["Name"]
            deck = d["steps"][1][i]["action"]
            if isinstance(deck, list) and len(deck) == 60:
                players.setdefault(nm, deck)
    except Exception:
        continue

rows = sorted(((lb.get(nm, 0), nm, headliner(dk)) for nm, dk in players.items()), reverse=True)
print(f"distinct players sampled: {len(rows)}\n")
print(f"{'score':>6}  {'headliner':<22} player")
print("-" * 52)
for sc, nm, a in rows[:20]:
    print(f"{sc:6.0f}  {a:<22} {nm[:20]}")
print("\ntop-20 archetype frequency:")
for a, c in collections.Counter(a for _, _, a in rows[:20]).most_common():
    print(f"  {c:2}x  {a}")
