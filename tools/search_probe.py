"""Feasibility probe for the Search API.

Plays a few turns with the baseline agent, then at the first real attack decision
uses search_begin/search_step to simulate the candidate attack and prints the
opponent's active HP before vs after — proving we can read true attack outcomes
locally. Run inside the Linux container (see bottom for the one-liner).
"""
import os
import sys
import importlib.util

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission")
sys.path.insert(0, SUB)
os.chdir(SUB)

from cg.game import battle_start, battle_finish, battle_select  # noqa: E402
from cg.api import (  # noqa: E402
    to_observation_class, OptionType, AreaType, CardType, all_card_data,
    search_begin, search_step, search_end,
)

card_table = {c.cardId: c for c in all_card_data()}

# Load the baseline agent to drive both sides until an attack is available.
spec = importlib.util.spec_from_file_location("agent_mod", os.path.join(SUB, "main.py"))
agent_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_mod)
agent_fn = agent_mod.agent

with open("deck.csv") as f:
    DECK = [int(x) for x in f.read().split("\n")[:60]]

# Card IDs we'll use as harmless fillers for the OPPONENT's unknown zones.
FILLER_ENERGY = 6   # Basic Fighting Energy
FILLER_BASIC = 677  # Riolu (a Basic Pokémon), in case a basic is required


def predict_my_hidden(obs):
    """Predict my own deck+prize: full deck minus everything I can see."""
    st = obs.current
    me = st.players[st.yourIndex]
    counts = {}
    for cid in DECK:
        counts[cid] = counts.get(cid, 0) + 1

    def remove(cid):
        if counts.get(cid, 0) > 0:
            counts[cid] -= 1

    def remove_pokemon(p):
        remove(p.id)
        for c in p.energyCards: remove(c.id)
        for c in p.tools: remove(c.id)
        for c in p.preEvolution: remove(c.id)

    for c in (me.hand or []): remove(c.id)
    for c in me.discard: remove(c.id)
    for p in me.active:
        if p: remove_pokemon(p)
    for p in me.bench: remove_pokemon(p)

    hidden = []
    for cid, n in counts.items():
        hidden += [cid] * n
    prize_n = len(me.prize)
    return hidden[prize_n:], hidden[:prize_n]  # your_deck, your_prize


def fillers(n):
    return [FILLER_ENERGY] * n


def main():
    obs_dict, _ = battle_start(DECK, DECK)
    step = 0
    while obs_dict["current"]["result"] < 0 and step < 400:
        step += 1
        obs = to_observation_class(obs_dict)
        sel = obs.select
        # Look for the first MAIN decision that offers an ATTACK.
        attack_opt = None
        if sel and sel.context == 0:  # MAIN
            for idx, o in enumerate(sel.option):
                if o.type == OptionType.ATTACK:
                    attack_opt = idx
                    break

        if attack_opt is not None and obs.search_begin_input:
            st = obs.current
            opp = st.players[1 - st.yourIndex]
            print(f"--- Found attack decision at turn {st.turn}, step {step} ---")
            opp_active = opp.active[0]
            print(f"Opponent active: id={opp_active.id} "
                  f"({card_table[opp_active.id].name}) HP={opp_active.hp}/{opp_active.maxHp}")
            your_deck, your_prize = predict_my_hidden(obs)
            try:
                root = search_begin(
                    obs,
                    your_deck=your_deck,
                    your_prize=your_prize,
                    opponent_deck=fillers(opp.deckCount) or [FILLER_BASIC],
                    opponent_prize=fillers(len(opp.prize)),
                    opponent_hand=fillers(opp.handCount),
                    opponent_active=[],  # active is face-up
                )
                print(f"search_begin OK (searchId={root.searchId})")
                sid = root.searchId
                cur = root.observation
                my_index = st.yourIndex
                # Step through the attack to resolution with a trivial auto-policy:
                # prefer the ATTACK option, else just take the first legal picks.
                for _ in range(30):
                    s = cur.select
                    if s is None or (cur.current and cur.current.result >= 0):
                        break
                    pick = None
                    for idx, o in enumerate(s.option):
                        if o.type == OptionType.ATTACK:
                            pick = [idx]
                            break
                    if pick is None:
                        pick = list(range(min(s.maxCount, len(s.option))))
                        if len(pick) < s.minCount:
                            pick = list(range(s.minCount))
                    cur = search_step(sid, pick).observation
                    # Stop once it's the opponent's turn (our attack resolved).
                    if cur.current and cur.current.yourIndex != my_index:
                        break
                nst = cur.current
                nopp = nst.players[1 - my_index] if nst else None
                if nopp and nopp.active and nopp.active[0]:
                    na = nopp.active[0]
                    print(f"AFTER resolving attack: opp active id={na.id} "
                          f"HP={na.hp}/{na.maxHp}  (damage dealt = {opp_active.hp - na.hp})")
                else:
                    print("AFTER resolving attack: opponent active KO'd or replaced")
                print(f"battle result in sim: {nst.result if nst else 'n/a'}")
                search_end()
                print("\nPROBE SUCCESS: search simulated a full attack and read the outcome.")
                battle_finish()
                return
            except Exception as e:
                print(f"search FAILED: {type(e).__name__}: {e}")
                battle_finish()
                return

        # Otherwise, let the baseline agent act and advance the battle.
        act = agent_fn(obs_dict)
        obs_dict = battle_select(act)

    print("No attack decision reached in probe window.")
    battle_finish()


if __name__ == "__main__":
    main()
