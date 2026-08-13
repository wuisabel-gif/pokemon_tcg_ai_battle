#!/usr/bin/env python3
"""Replay an episode against the production policy and report disagreements.

Kaggle replays store one cell per step and one record per player in each cell.
An observation in cell ``t`` is answered by that seat's ``action`` in cell
``t + 1``. During a wait, the observation can be repeated in an INACTIVE
record; those records are skipped by the alignment logic.
The production agent is stateful (a global turn plan), so observations must
be fed chronologically for a single seat — never scored independently.

The pure-Python helpers (alignment, comparison, grouping, rendering) import
cleanly on any platform.  Running the policy itself requires the Linux game
engine, so use ``tools/compare_replays.sh`` which wraps this script in the
same Docker image as ``tools/test_local.sh``.

Usage (inside Docker):
    python tools/replay_policy_compare.py \
        --replays data/replays_latest --team "Isabella Wu" \
        --agent submission --format markdown -o disagreements.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Context labels are parsed from submission/cg/api.py at runtime so they stay
# correct when the enum changes; no game-engine import is required.
_FALLBACK_CONTEXT_NAMES = {
    0: "MAIN",
    1: "SETUP_ACTIVE_POKEMON",
    2: "SETUP_BENCH_POKEMON",
    3: "SWITCH",
    4: "TO_ACTIVE",
    5: "TO_BENCH",
    7: "TO_HAND",
    8: "DISCARD",
    21: "ATTACH_FROM",
    22: "ATTACH_TO",
    30: "DISCARD_ENERGY",
    38: "DRAW_COUNT",
    41: "IS_FIRST",
    42: "MULLIGAN",
    43: "ACTIVATE",
}


def load_context_names() -> dict:
    """Parse SelectContext members from cg/api.py source (no engine import)."""
    import re
    api_path = Path(REPO) / "submission" / "cg" / "api.py"
    names = dict(_FALLBACK_CONTEXT_NAMES)
    try:
        text = api_path.read_text(encoding="utf-8-sig")
    except OSError:
        return names
    m = re.search(r"class SelectContext\(IntEnum\):(.*?)\nclass ", text, re.S)
    if not m:
        return names
    for name, value in re.findall(r"^\s+([A-Z_]+)\s*=\s*(\d+)", m.group(1), re.M):
        names[int(value)] = name
    return names


CONTEXT_NAMES = load_context_names()


# --------------------------------------------------------------------------
# Pure helpers (no game-engine imports; unit-testable on macOS)
# --------------------------------------------------------------------------

def team_index(replay: dict, team: str | None) -> int:
    """Resolve the expert's seat from replay info."""
    names = (replay.get("info") or {}).get("TeamNames") or []
    if team is not None:
        if team not in names:
            raise ValueError(f"team {team!r} not in replay TeamNames {names!r}")
        return names.index(team)
    if len(names) == 2:
        return 1  # default: second listed team (our submissions in cached data)
    return 0


def iter_seat_decisions(replay: dict, seat: int) -> Iterable[dict]:
    """Yield chronological decision records for one seat.

    Each record pairs an observation in cell ``t`` with the same seat's
    answering action in cell ``t + 1``. The deck-request observation
    (``select`` is None) is yielded with ``is_deck_request`` so the caller can
    feed it to the policy (resetting its state) without comparing actions.
    """
    steps = replay.get("steps") or []
    for t, cell in enumerate(steps):
        if not isinstance(cell, list) or seat >= len(cell):
            continue
        record = cell[seat]
        if not isinstance(record, dict):
            continue
        if record.get("status") not in (None, "ACTIVE"):
            continue
        obs = record.get("observation")
        if not isinstance(obs, dict) or not obs:
            continue
        select = obs.get("select")
        if select is None:
            next_action = None
            if t + 1 < len(steps) and isinstance(steps[t + 1], list) and seat < len(steps[t + 1]):
                next_record = steps[t + 1][seat]
                if isinstance(next_record, dict):
                    next_action = next_record.get("action")
            yield {"step": t, "obs": obs, "expert_action": next_action,
                   "is_deck_request": True, "context": None, "select": None}
        elif isinstance(select, dict) and select.get("option"):
            next_action = None
            if t + 1 < len(steps) and isinstance(steps[t + 1], list) and seat < len(steps[t + 1]):
                next_record = steps[t + 1][seat]
                if isinstance(next_record, dict):
                    next_action = next_record.get("action")
            yield {"step": t, "obs": obs, "expert_action": next_action,
                   "is_deck_request": False, "skip": None,
                   "context": select.get("context"), "select": select}


def canonical(action: Any) -> tuple[int, ...]:
    """Order-normalized action fingerprint (multi-select order is irrelevant)."""
    if action is None:
        return ()
    values = action if isinstance(action, list) else [action]
    out = []
    for v in values:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            return ()
    return tuple(sorted(out))


def action_overlap(a: Any, b: Any) -> float:
    """Multiset Jaccard overlap between two actions; 1.0 when both empty."""
    ca, cb = canonical(a), canonical(b)
    if not ca and not cb:
        return 1.0
    aa, bb = Counter(ca), Counter(cb)
    keys = set(aa) | set(bb)
    union = sum(max(aa[k], bb[k]) for k in keys)
    inter = sum(min(aa[k], bb[k]) for k in keys)
    return inter / union if union else 1.0


def legality_error(action: Any, select: dict) -> str | None:
    """Validate a candidate action against the offered select constraints."""
    vals = canonical(action)
    if not vals:
        return "empty_or_noninteger"
    options = select.get("option") or []
    lo = select.get("minCount", 0) or 0
    hi = select.get("maxCount", 0) or 0
    if len(set(vals)) != len(vals):
        return "duplicate_indices"
    if len(vals) < lo:
        return f"too_few({len(vals)}<{lo})"
    if len(vals) > hi:
        return f"too_many({len(vals)}>{hi})"
    if any(v < 0 or v >= len(options) for v in vals):
        return "index_out_of_range"
    return None


def option_fingerprint(select: dict, indices: Any) -> str:
    """Human-readable summary of chosen options, e.g. '14+3' option types."""
    options = select.get("option") or []
    parts = []
    for i in canonical(indices):
        if 0 <= i < len(options) and isinstance(options[i], dict):
            parts.append(str(options[i].get("type", "?")))
        else:
            parts.append("?")
    return "+".join(parts) if parts else "-"


def context_label(context: Any) -> str:
    try:
        return CONTEXT_NAMES.get(int(context), f"CTX_{context}")
    except (TypeError, ValueError):
        return str(context)


def summarize(records: list[dict]) -> dict:
    """Group comparison records by context and turn bucket."""
    groups = defaultdict(lambda: {
        "decisions": 0, "agreements": 0, "differences": 0,
        "illegal": 0, "exceptions": 0, "overlap_sum": 0.0,
        "examples": [],
    })
    for r in records:
        if r.get("is_deck_request"):
            continue
        key = (r["context_label"], r["turn_bucket"])
        g = groups[key]
        g["decisions"] += 1
        g["exceptions"] += int(bool(r.get("exception")))
        g["illegal"] += int(bool(r.get("legality_error")))
        ov = r.get("overlap", 0.0)
        g["overlap_sum"] += ov
        if r.get("agree"):
            g["agreements"] += 1
        else:
            g["differences"] += 1
            if len(g["examples"]) < 3:
                g["examples"].append({
                    "step": r["step"], "turn": r.get("turn"),
                    "expert": r.get("expert_fp"), "ours": r.get("ours_fp"),
                })
    rows = []
    for (ctx, bucket), g in groups.items():
        n = g["decisions"]
        rows.append({
            "context": ctx, "turn_bucket": bucket,
            "decisions": n, "agreements": g["agreements"],
            "differences": g["differences"],
            "agreement_rate": g["agreements"] / n if n else 0.0,
            "mean_overlap": g["overlap_sum"] / n if n else 0.0,
            "illegal": g["illegal"], "exceptions": g["exceptions"],
            "examples": g["examples"],
        })
    rows.sort(key=lambda r: r["differences"], reverse=True)
    return rows


def render_markdown(result: dict) -> str:
    lines = [
        "# Replay policy comparison", "",
        f"- Episodes: {result['episodes']}",
        f"- Decisions compared: {result['decisions']}",
    ]
    if result["decisions"]:
        lines.append(
            f"- Agreements: {result['agreements']} "
            f"({result['agreements'] / result['decisions']:.1%})")
    lines += [
        f"- Exceptions (would be hidden fallbacks): {result['exceptions']}",
        f"- Illegal candidate actions: {result['illegal']}", "",
        "| Context | Turns | Decisions | Agreement | Mean overlap | Exceptions | Illegal |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in result["groups"]:
        lines.append(
            f"| {r['context']} | {r['turn_bucket']} | {r['decisions']} | "
            f"{r['agreement_rate']:.1%} | {r['mean_overlap']:.1%} | "
            f"{r['exceptions']} | {r['illegal']} |"
        )
    top = [r for r in result["groups"] if r["differences"]][:5]
    if top:
        lines += ["", "## Top disagreement examples", ""]
        for r in top:
            lines.append(f"### {r['context']} ({r['turn_bucket']})")
            for ex in r["examples"]:
                lines.append(
                    f"- step {ex['step']} turn {ex['turn']}: "
                    f"expert `{ex['expert']}` vs ours `{ex['ours']}`"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def load_replays(paths: Iterable[str]) -> list[tuple[str, dict]]:
    out = []
    for name in paths:
        p = Path(name)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        for f in files:
            try:
                out.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
            except Exception as exc:  # noqa: BLE001 - report and skip bad files
                print(f"warning: skipping {f}: {exc}", file=sys.stderr)
    return out


# --------------------------------------------------------------------------
# Policy execution (requires the Linux game engine; run via Docker wrapper)
# --------------------------------------------------------------------------

def load_policy(agent_dir_name: str):
    """Load an agent module fresh; call once per episode for clean globals."""
    agent_dir = os.path.join(REPO, agent_dir_name)
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    prev = os.getcwd()
    os.chdir(agent_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            f"policy_{agent_dir_name}", os.path.join(agent_dir, "main.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(prev)
    impl = getattr(mod, "_agent_impl", None) or mod.agent
    return impl


def compare_episode(replay: dict, seat: int, agent_dir: str) -> list[dict]:
    """Feed one seat's observations to the policy in order; compare choices."""
    impl = load_policy(agent_dir)  # fresh module = fresh global plan
    records = []
    skipped = Counter()
    for d in iter_seat_decisions(replay, seat):
        obs = dict(d["obs"])
        obs.pop("search_begin_input", None)  # match tools/run_match.py behavior
        if d["is_deck_request"]:
            try:
                impl(obs)  # returns the deck; resets agent state
            except Exception:  # noqa: BLE001
                pass
            continue
        if d.get("skip"):
            skipped[d["skip"].split(":", 1)[0]] += 1
            continue
        select = d["select"]
        turn = (obs.get("current") or {}).get("turn")
        try:
            ours = impl(obs)
            exc = None
        except Exception as e:  # noqa: BLE001 - count what the wrapper would hide
            ours, exc = None, f"{type(e).__name__}: {e}"
        legal = legality_error(ours, select) if exc is None else "exception"
        agree = (exc is None and legal is None
                 and canonical(ours) == canonical(d["expert_action"]))
        records.append({
            "step": d["step"], "turn": turn,
            "turn_bucket": ("t0" if turn == 0
                            else "t1-3" if isinstance(turn, int) and turn <= 3
                            else "t4+"),
            "context_label": context_label(d["context"]),
            "exception": exc, "legality_error": legal,
            "agree": agree,
            "overlap": action_overlap(ours, d["expert_action"]),
            "expert_fp": option_fingerprint(select, d["expert_action"]),
            "ours_fp": option_fingerprint(select, ours),
        })
    return records, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--replays", nargs="+", required=True,
                    help="Replay JSON files or directories")
    ap.add_argument("--team", default=None,
                    help="Team name of the expert seat (default: second TeamNames entry)")
    ap.add_argument("--agent", default="submission", help="Agent directory to compare")
    ap.add_argument("--format", choices=("json", "markdown"), default="markdown")
    ap.add_argument("--output", "-o", default=None)
    args = ap.parse_args(argv)

    all_records, episodes, total_skipped = [], 0, Counter()
    for name, replay in load_replays(args.replays):
        try:
            seat = team_index(replay, args.team)
        except ValueError as exc:
            print(f"warning: {name}: {exc}", file=sys.stderr)
            continue
        records, skipped = compare_episode(replay, seat, args.agent)
        all_records.extend(records)
        total_skipped.update(skipped)
        episodes += 1

    groups = summarize(all_records)
    result = {
        "episodes": episodes,
        "decisions": sum(g["decisions"] for g in groups),
        "agreements": sum(g["agreements"] for g in groups),
        "exceptions": sum(g["exceptions"] for g in groups),
        "illegal": sum(g["illegal"] for g in groups),
        "skipped": dict(total_skipped),
        "groups": groups,
    }
    text = (json.dumps(result, indent=2) if args.format == "json"
            else render_markdown(result))
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
