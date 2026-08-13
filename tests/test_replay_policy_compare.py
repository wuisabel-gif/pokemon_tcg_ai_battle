import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "replay_policy_compare", Path(__file__).parents[1] / "tools" / "replay_policy_compare.py")
rpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rpc)


def make_replay(team="Expert"):
    obs_deck = {"current": {"turn": 0, "yourIndex": 1}, "select": None}
    obs_main = {"current": {"turn": 1, "yourIndex": 1},
                "select": {"context": 0, "minCount": 1, "maxCount": 1,
                           "option": [{"type": 14}, {"type": 3}]}}
    obs_multi = {"current": {"turn": 2, "yourIndex": 1},
                 "select": {"context": 21, "minCount": 0, "maxCount": 2,
                            "option": [{"type": 9}, {"type": 9}, {"type": 12}]}}
    return {
        "info": {"TeamNames": ["Foe", team]},
        # The answer to cell t is stored in the same seat in cell t+1.
        "steps": [
            [{"observation": obs_deck}, {"observation": obs_deck}],
            [{"action": [1] * 60}, {"action": [2] * 60}],
            [{"observation": obs_main}, {"observation": obs_main}],
            [{"action": [0]}, {"action": [1]}],
            [{"observation": obs_multi}, {"observation": obs_multi}],
            [{"action": [0, 1]}, {"action": [1, 0]}],  # order differs
        ],
    }


def test_seat_alignment_and_deck_filtering():
    decisions = list(rpc.iter_seat_decisions(make_replay(), seat=1))
    assert len(decisions) == 3
    assert decisions[0]["is_deck_request"] and decisions[0]["expert_action"] == [2] * 60
    assert decisions[1]["context"] == 0 and decisions[1]["expert_action"] == [1]
    assert decisions[2]["context"] == 21 and decisions[2]["expert_action"] == [1, 0]


def test_inactive_repeated_cells_are_skipped():
    replay = make_replay()
    replay["steps"].insert(3, [{"status": "INACTIVE", "observation": replay["steps"][2][0]["observation"]},
                               {"status": "INACTIVE", "observation": replay["steps"][2][1]["observation"]}])
    assert all(d["step"] != 3 for d in rpc.iter_seat_decisions(replay, seat=1))


def test_team_index():
    assert rpc.team_index(make_replay(), "Expert") == 1
    assert rpc.team_index(make_replay(), None) == 1
    try:
        rpc.team_index(make_replay(), "Missing")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_canonical_overlap_and_legality():
    assert rpc.canonical([1, 0]) == (0, 1)
    assert rpc.action_overlap([1, 0], [0, 1]) == 1.0
    assert rpc.action_overlap([0], [1]) == 0.0
    sel = {"option": [{}, {}, {}], "minCount": 1, "maxCount": 2}
    assert rpc.legality_error([0, 2], sel) is None
    assert rpc.legality_error([0, 0], sel) == "duplicate_indices"
    assert rpc.legality_error([], sel) == "empty_or_noninteger"
    assert rpc.legality_error([5], sel) == "index_out_of_range"
    assert rpc.legality_error([0, 1, 2], sel) == "too_many(3>2)"


def test_summarize_groups_and_examples():
    records = [
        {"is_deck_request": False, "context_label": "MAIN", "turn_bucket": "t1-3",
         "step": 2, "turn": 1, "exception": None, "legality_error": None,
         "agree": True, "overlap": 1.0, "expert_fp": "14", "ours_fp": "14"},
        {"is_deck_request": False, "context_label": "MAIN", "turn_bucket": "t1-3",
         "step": 4, "turn": 2, "exception": "ValueError: boom", "legality_error": "exception",
         "agree": False, "overlap": 0.0, "expert_fp": "3", "ours_fp": "-"},
    ]
    rows = rpc.summarize(records)
    assert len(rows) == 1
    row = rows[0]
    assert row["decisions"] == 2 and row["agreements"] == 1 and row["differences"] == 1
    assert row["exceptions"] == 1 and row["agreement_rate"] == 0.5
    assert row["examples"][0]["expert"] == "3"


def test_render_markdown():
    result = {"episodes": 1, "decisions": 2, "agreements": 1, "exceptions": 1,
              "illegal": 1,
              "groups": rpc.summarize([
                  {"is_deck_request": False, "context_label": "MAIN",
                   "turn_bucket": "t1-3", "step": 4, "turn": 2,
                   "exception": None, "legality_error": None, "agree": False,
                   "overlap": 0.5, "expert_fp": "3", "ours_fp": "14"}])}
    text = rpc.render_markdown(result)
    assert "# Replay policy comparison" in text
    assert "MAIN" in text and "50.0%" in text
