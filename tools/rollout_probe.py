"""Validate using the heuristic agent as the rollout policy inside search.

The Search API returns observations as dataclasses; agent() wants a dict. This
probes whether dataclasses.asdict round-trips well enough to drive a full-turn
rollout with the real agent (the key capability v1's crude auto-resolve lacked).
"""
import os, sys, importlib.util, dataclasses

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission")
sys.path.insert(0, SUB); os.chdir(SUB)
from cg.game import battle_start, battle_select, battle_finish  # noqa
from cg.api import (to_observation_class, OptionType, search_begin, search_step, search_end)  # noqa

spec = importlib.util.spec_from_file_location("am", os.path.join(SUB, "main.py"))
am = importlib.util.module_from_spec(spec); spec.loader.exec_module(am)
with open("deck.csv") as f:
    DECK = [int(x) for x in f.read().split("\n")[:60]]
FILLER = 6


def predict_mine(obs):
    st = obs.current; me = st.players[st.yourIndex]
    counts = {}
    for cid in DECK: counts[cid] = counts.get(cid, 0) + 1
    def rm(c):
        if counts.get(c, 0) > 0: counts[c] -= 1
    def rmp(p):
        rm(p.id)
        for c in p.energyCards: rm(c.id)
        for c in p.tools: rm(c.id)
        for c in p.preEvolution: rm(c.id)
    for c in (me.hand or []): rm(c.id)
    for c in me.discard: rm(c.id)
    for p in me.active:
        if p: rmp(p)
    for p in me.bench: rmp(p)
    h = [c for cid, n in counts.items() for c in [cid] * n]
    pn = len(me.prize)
    return h[pn:], h[:pn]


obs = battle_start(DECK, DECK)[0]
for step in range(400):
    if obs["current"]["result"] >= 0:
        break
    o = to_observation_class(obs)
    if o.select and o.select.context == 0 and o.current.turn >= 2 and o.search_begin_input \
       and any(op.type == OptionType.ATTACK for op in o.select.option):
        mi = o.current.yourIndex
        opp = o.current.players[1 - mi]
        yd, yp = predict_mine(o)
        root = search_begin(o, your_deck=yd, your_prize=yp,
                            opponent_deck=[FILLER] * opp.deckCount or [677],
                            opponent_prize=[FILLER] * len(opp.prize),
                            opponent_hand=[FILLER] * opp.handCount, opponent_active=[])
        sid = root.searchId
        sim = root.observation
        prize_before = len(o.current.players[mi].prize)
        steps_driven = 0
        agent_calls_ok = 0
        for _ in range(40):
            s = sim.select; c = sim.current
            if s is None or (c and c.result >= 0):
                break
            if c and c.yourIndex != mi:
                break
            # convert dataclass obs -> dict and drive with the REAL agent
            sim_dict = dataclasses.asdict(sim)
            try:
                action = am.agent(sim_dict)
                agent_calls_ok += 1
            except Exception as e:
                print(f"AGENT FAILED on sim obs: {type(e).__name__}: {e}")
                action = list(range(min(s.maxCount, len(s.option))))
            ss = search_step(sid, action)
            sid = ss.searchId
            sim = ss.observation
            steps_driven += 1
        c = sim.current
        prizes = prize_before - len(c.players[mi].prize) if c else 0
        search_end()
        print(f"Rollout at turn {o.current.turn}: agent drove {agent_calls_ok}/{steps_driven} sim steps OK, "
              f"prizes taken in sim turn = {prizes}")
        print("PROBE OK — heuristic agent works as a rollout policy inside search."
              if agent_calls_ok == steps_driven else "PROBE: some agent calls failed on sim obs.")
        battle_finish()
        break
    obs.pop("search_begin_input", None)
    obs = battle_select(am.agent(obs))
