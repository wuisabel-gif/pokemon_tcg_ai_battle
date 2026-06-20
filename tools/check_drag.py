"""Count how often the drag/snipe (Boss's Orders) search path actually fires."""
import os, sys, importlib.util
SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission")
sys.path.insert(0, SUB); os.chdir(SUB)
from cg.game import battle_start, battle_select, battle_finish  # noqa
from cg.api import to_observation_class, OptionType, SelectContext  # noqa
spec = importlib.util.spec_from_file_location("am", os.path.join(SUB, "main.py"))
am = importlib.util.module_from_spec(spec); spec.loader.exec_module(am)
with open("deck.csv") as f:
    DECK = [int(x) for x in f.read().split("\n")[:60]]
drag_ctx = drag_fired = multi = 0
for g in range(30):
    obs = battle_start(DECK, DECK)[0]
    for _ in range(400):
        if obs["current"]["result"] >= 0:
            break
        o = to_observation_class(obs)
        if o.select and o.select.context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
            mi = o.current.yourIndex
            opp_opts = [i for i, op in enumerate(o.select.option)
                        if op.type == OptionType.CARD and op.playerIndex != mi]
            if opp_opts:
                drag_ctx += 1
                if am.search_drag_target_values(o, mi):
                    drag_fired += 1
                if len(opp_opts) > 1:
                    multi += 1
        obs.pop("search_begin_input", None)
        obs = battle_select(am.agent(obs))
    battle_finish()
print(f"over 30 games: snipe contexts={drag_ctx}, search fired={drag_fired}, with 2+ targets={multi}")
