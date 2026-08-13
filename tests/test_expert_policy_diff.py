import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("expert_policy_diff", Path(__file__).parents[1] / "tools" / "expert_policy_diff.py")
epd = importlib.util.module_from_spec(spec); spec.loader.exec_module(epd)


def replay(deck, expert=True, result="win"):
    # Cell t contains observations for both players; t+1 contains their actions.
    obs = {"select": {"context": "PLAY", "option": [["a"], ["b"]]}, "current": {"turn": 2, "phase": "main"}}
    return {"metadata": {"deck": deck, "expert": expert, "result": result,
                           "opponent": "foe", "archetype": "control", "seat": 0},
            "steps": [[{"observation": obs}, {"observation": {"select": {"context": "IsFirst"}}}],
                      [{"action": ["a", "b"], "expert_action": ["a", "b"], "target_action": ["b", "a"]},
                       {"action": ["x"]}]]}


def test_multiset_exact_and_jaccard():
    assert epd.normalize_deck(["a", "a", "b"]) == ("a:2", "b:1")
    assert epd.same_deck(["a", "a", "b"], ["b", "a", "a"])
    assert epd.deck_similarity(["a", "b"], ["a", "c"]) == 1 / 3
    assert epd.same_deck(["a", "b"], ["a", "c"], 1 / 3)


def test_next_cell_alignment_filters_deck_action_and_groups():
    result = epd.analyze([replay(["a"] * 60)], ["a"] * 60)
    assert result["decisions"] == 1
    row = result["groups"][0]
    assert row["context"] == "PLAY"
    assert row["wins"] == 1 and row["losses"] == 0
    assert row["agreement_rate"] == 1  # sorted fingerprints, order is not a difference
    assert row["mean_action_overlap"] == 1


def test_difference_and_renderers(tmp_path):
    ep = replay(["a"] * 59 + ["b"], result="loss")
    ep["steps"][1][0]["target_action"] = ["c"]
    result = epd.analyze([ep], ["a"] * 60, threshold=.9)
    row = result["groups"][0]
    assert row["differences"] == 1 and row["losses"] == 1
    assert "agreement_rate" in epd.render(result, "csv")
    assert "# Expert policy differences" in epd.render(result, "markdown")
    p = tmp_path / "r.json"; p.write_text(json.dumps(ep))
    assert len(epd.load_inputs([str(p)])) == 1


def test_expert_metadata_selection():
    ordinary = replay(["a"] * 60, expert=False)
    expert = replay(["a"] * 60, expert=True)
    assert len(epd.select_experts([ordinary, expert])) == 1
    assert epd.select_experts([ordinary])[0] is ordinary
