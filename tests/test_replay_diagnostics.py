import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("replay_diagnostics", Path(__file__).parents[1] / "tools" / "replay_diagnostics.py")
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)


def episode(deck, result="win", action=(1,), context="ATTACK"):
    return {"deck": deck, "result": result, "opponent": "foe", "team": "red", "archetype": "control", "seat": 0,
            "steps": [{"observation": {"select": {"context": context, "option": [1, 2]}}, "action": list(action)}]}


def test_deck_exact_and_multiset_jaccard():
    assert rd.normalize_deck(["a", "b", "a"]) == ("a:2", "b:1")
    assert rd.same_deck(["a", "a", "b"], {"a": 2, "b": 1}) is False  # dict is one card object, not a list
    assert rd.same_deck(["a", "a", "b"], ["b", "a", "a"])
    assert rd.deck_similarity(["a", "b"], ["a", "c"]) == 1 / 3
    assert rd.same_deck(["a", "b"], ["a", "c"], "similarity", 1 / 3)


def test_alignment_and_grouped_stats():
    first = {"observation": {"select": {"context": "PLAY", "option": [0]}}, "step": 0}
    second = {"action": [0], "step": 1}
    result = rd.analyze([{**episode(["a"], "loss"), "steps": [first, second]}, episode(["a"], "win", [2])])
    assert result["decisions"] == 2
    assert sum(row["wins"] + row["losses"] for row in result["groups"]) == 2
    assert {row["context"] for row in result["groups"]} == {"PLAY", "ATTACK"}


def test_callback_and_render_formats():
    data = episode(["a"], action=[1])
    data["steps"][0]["heuristic_action"] = [2]
    result = rd.analyze([data])
    assert result["groups"][0]["match_rate"] == 0
    result = rd.analyze([data], callback=lambda obs, legal: [1])
    assert result["groups"][0]["match_rate"] == 1
    assert "# Replay diagnostics" in rd.render(result, "markdown")
    assert "context" in rd.render(result, "csv")
