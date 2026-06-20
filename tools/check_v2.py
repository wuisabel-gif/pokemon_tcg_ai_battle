import os, sys, importlib.util
SUB=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"submission")
sys.path.insert(0,SUB); os.chdir(SUB)
from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class, SelectContext, OptionType
spec=importlib.util.spec_from_file_location("am",os.path.join(SUB,"main.py"))
am=importlib.util.module_from_spec(spec); spec.loader.exec_module(am)
with open("deck.csv") as f: DECK=[int(x) for x in f.read().split("\n")[:60]]
main_dec=0; overrides=0; fired=0
for g in range(4):
    obs=battle_start(DECK,DECK)[0]
    for _ in range(400):
        if obs["current"]["result"]>=0: break
        o=to_observation_class(obs)
        if o.select and o.select.context==SelectContext.MAIN and o.select.maxCount==1 and o.current.turn>=2 and o.search_begin_input:
            # heuristic top vs search pick
            main_dec+=1
            # compute heuristic desc (call agent with _in_rollout to bypass search)
            am._in_rollout=True; heur=am.agent(obs); am._in_rollout=False
            pick=am.agent(obs)
            fired+=1
            if heur and pick and heur[0]!=pick[0]: overrides+=1
        obs.pop("search_begin_input",None)
        obs=battle_select(am.agent(obs))
    battle_finish()
print(f"MAIN decisions checked={main_dec}, search fired={fired}, search OVERRODE heuristic={overrides} ({100*overrides/max(1,fired):.0f}%)")
