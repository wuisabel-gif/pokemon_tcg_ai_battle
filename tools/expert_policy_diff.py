#!/usr/bin/env python3
"""Compare expert and target policies in same-deck replay trajectories.

This is deliberately stdlib-only and does not import the game engine.  Kaggle's
``steps`` are commonly cells containing one record per player; an observation in
cell *t* is paired with that player's action in cell *t+1*.  The initial 60-card
deck response is a protocol action, not a policy decision, and is ignored.
"""
from __future__ import annotations
import argparse, csv, io, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def as_list(value: Any) -> list:
    if value is None: return []
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: value = [x.strip() for x in value.split(",") if x.strip()]
    return value if isinstance(value, list) else [value]


def card_token(card: Any) -> str:
    if isinstance(card, dict):
        return str(card.get("id", card.get("card_id", card.get("name", card)))).strip()
    return str(card).strip()


def deck_counts(deck: Any) -> Counter:
    out = Counter()
    for card in as_list(deck):
        if isinstance(card, dict) and ("count" in card or "quantity" in card):
            out[card_token(card)] += int(card.get("count", card.get("quantity", 1)) or 1)
        elif card is not None and card_token(card): out[card_token(card)] += 1
    return out


def normalize_deck(deck: Any) -> tuple[str, ...]:
    return tuple(f"{k}:{v}" for k, v in sorted(deck_counts(deck).items()))


def deck_similarity(a: Any, b: Any) -> float:
    aa, bb = deck_counts(a), deck_counts(b); keys = set(aa) | set(bb)
    union = sum(max(aa[k], bb[k]) for k in keys)
    return sum(min(aa[k], bb[k]) for k in keys) / union if union else 1.0


def same_deck(a: Any, target: Any, threshold: float = 1.0) -> bool:
    return normalize_deck(a) == normalize_deck(target) if threshold >= 1 else deck_similarity(a, target) >= threshold


def _meta(ep: dict) -> dict:
    m = dict(ep.get("metadata", {})) if isinstance(ep.get("metadata"), dict) else {}
    for k in ("deck", "decklist", "opponent", "opponent_id", "archetype", "team", "seat", "result", "outcome", "rank", "expert", "is_expert"):
        if k in ep: m.setdefault(k, ep[k])
    return m


def _deck_from_cell(cell: Any) -> Any:
    if not isinstance(cell, dict): return None
    obs = cell.get("observation", cell.get("obs", {}))
    if not isinstance(obs, dict) or not isinstance(obs.get("current"), dict):
        visual = cell.get("visualize", [])
        if isinstance(visual, list) and visual and isinstance(visual[0], dict):
            obs = visual[0]
    cur = obs.get("current") if isinstance(obs, dict) else None
    if isinstance(cur, dict):
        players = cur.get("players", [])
        seat = cell.get("seat", cur.get("yourIndex"))
        if isinstance(seat, int) and seat < len(players): return players[seat].get("deck")
    return None


def extract_deck(ep: dict, seat: int | None = None) -> Any:
    metadata = ep.get("metadata") if isinstance(ep.get("metadata"), dict) else {}
    for key in ("deck", "decklist", "cards"):
        if key in ep: return ep[key]
        if key in metadata: return metadata[key]
    metadata = ep.get("metadata")
    if isinstance(metadata, dict):
        for key in ("deck", "decklist", "cards"):
            if key in metadata: return metadata[key]
    cells = ep.get("steps", ep.get("trajectory", []))
    for cell in cells if isinstance(cells, list) else []:
        candidates = cell if isinstance(cell, list) else [cell]
        for c in candidates:
            if isinstance(c, dict) and (seat is None or c.get("seat", seat) == seat):
                deck = _deck_from_cell(c)
                if deck: return deck
    return []


def _is_expert(ep: dict, meta: dict) -> bool:
    for k in ("expert", "is_expert", "expert_submission"):
        if meta.get(k) is True or str(meta.get(k, "")).lower() in ("expert", "true", "yes"):
            return True
    return str(meta.get("submission_type", meta.get("role", ""))).lower() == "expert"


def select_experts(episodes: Iterable[dict]) -> list[dict]:
    """Prefer explicit expert metadata; otherwise retain best (lowest) rank."""
    eps = list(episodes); flagged = [e for e in eps if _is_expert(e, _meta(e))]
    if flagged: return flagged
    ranked = [(float(_meta(e)["rank"]), e) for e in eps if _meta(e).get("rank") is not None]
    if ranked:
        best = min(r for r, _ in ranked)
        return [e for r, e in ranked if r == best]
    return eps


def _obs(cell: dict) -> dict:
    o = cell.get("observation", cell.get("obs", {})); return o if isinstance(o, dict) else {}


def _decision(cell: dict, step: int, seat: int, next_action: Any, meta: dict, next_cell: dict | None = None) -> dict | None:
    obs = _obs(cell); select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    action = next_action
    context = select.get("context", cell.get("context", "unknown"))
    if action is None: return None
    values = as_list(action)
    if context in ("IsFirst", "FIRST", "Deck", "DECK") or len(values) >= 60: return None
    cur = obs.get("current", {}) if isinstance(obs.get("current"), dict) else {}
    turn = cur.get("turn", obs.get("turn", "unknown")); phase = cur.get("phase", obs.get("phase", "unknown"))
    row = dict(meta); row.update(step=step, seat=seat, context=context, turn=turn, phase=phase, observation=obs)
    next_cell = next_cell or {}
    row["expert_action"] = cell.get("expert_action", next_cell.get("expert_action", cell.get("action", action)))
    row["target_action"] = cell.get("target_action", next_cell.get("target_action", next_cell.get("predicted_action", next_cell.get("agent_action"))))
    return row


def iter_decisions(ep: dict) -> Iterable[dict]:
    cells = ep.get("steps", ep.get("trajectory", ep.get("records", []))); meta = _meta(ep)
    if not isinstance(cells, list): return
    for i, cell in enumerate(cells):
        if isinstance(cell, list):
            following = cells[i + 1] if i + 1 < len(cells) and isinstance(cells[i + 1], list) else []
            for seat, item in enumerate(cell):
                if isinstance(item, dict) and seat < len(following) and isinstance(following[seat], dict):
                    row = _decision(item, i, seat, following[seat].get("action"), meta, following[seat])
                    if row: yield row
        elif isinstance(cell, dict):
            following = cells[i + 1] if i + 1 < len(cells) and isinstance(cells[i + 1], dict) else {}
            row = _decision(cell, i, int(cell.get("seat", meta.get("seat", 0))), following.get("action", cell.get("action")), meta, following)
            if row: yield row


def action_fingerprint(action: Any) -> tuple[str, ...]:
    return tuple(sorted(card_token(x) for x in as_list(action)))


def action_overlap(a: Any, b: Any) -> float:
    aa, bb = Counter(action_fingerprint(a)), Counter(action_fingerprint(b)); keys = set(aa) | set(bb)
    union = sum(max(aa[k], bb[k]) for k in keys)
    return sum(min(aa[k], bb[k]) for k in keys) / union if union else 1.0


def _outcome(meta: dict) -> tuple[int, int]:
    value = str(meta.get("result", meta.get("outcome", ""))).lower()
    if not value and isinstance(meta.get("rewards"), list):
        value = str(meta["rewards"][int(meta.get("seat", 0) or 0)] if meta["rewards"] else "")
    return (int(value in ("win", "won", "1", "true")), int(value in ("loss", "lost", "-1", "false", "0")))


def analyze(episodes: Iterable[dict], target_deck: Any, threshold: float = 1.0) -> dict:
    selected = select_experts(episodes); groups = defaultdict(lambda: {"decisions": 0, "wins": 0, "losses": 0, "agreements": 0, "differences": 0, "overlap_sum": 0.0})
    for ep in selected:
        meta = _meta(ep); seat = meta.get("seat"); deck = extract_deck(ep, seat if isinstance(seat, int) else None)
        if target_deck is not None and not same_deck(deck, target_deck, threshold): continue
        win, loss = _outcome(meta)
        for row in iter_decisions(ep):
            target = row.get("target_action")
            if target is None: continue
            expert_fp, target_fp = action_fingerprint(row["expert_action"]), action_fingerprint(target)
            key = tuple(str(row.get(k, "unknown")) for k in ("context", "phase", "turn", "opponent", "archetype")); g = groups[key]
            same = expert_fp == target_fp; g["decisions"] += 1; g["wins"] += win; g["losses"] += loss; g["agreements"] += int(same); g["differences"] += int(not same); g["overlap_sum"] += action_overlap(row["expert_action"], target)
    rows = []
    for key, g in groups.items():
        r = dict(zip(("context", "phase", "turn", "opponent", "archetype"), key)); r.update(g); n = g["decisions"]
        r["agreement_rate"] = g["agreements"] / n if n else 0.0; r["difference_rate"] = g["differences"] / n if n else 0.0; r["mean_action_overlap"] = g["overlap_sum"] / n if n else 0.0; del r["overlap_sum"]; rows.append(r)
    return {"matched_episodes": len(selected), "decisions": sum(r["decisions"] for r in rows), "groups": rows}


def load_inputs(names: Iterable[str]) -> list[dict]:
    out = []
    for name in names:
        p = Path(name); paths = sorted(p.glob("*.json")) if p.is_dir() else [p]
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8")); out.extend(data if isinstance(data, list) else data.get("episodes", data.get("records", [data])) if isinstance(data, dict) else [])
    return [x for x in out if isinstance(x, dict)]


def render(result: dict, fmt: str) -> str:
    if fmt == "json": return json.dumps(result, indent=2, sort_keys=True)
    fields = ["context", "phase", "turn", "opponent", "archetype", "decisions", "wins", "losses", "agreements", "differences", "agreement_rate", "difference_rate", "mean_action_overlap"]
    if fmt == "csv":
        s = io.StringIO(); w = csv.DictWriter(s, fieldnames=fields); w.writeheader(); w.writerows({k:r.get(k, "") for k in fields} for r in result["groups"]); return s.getvalue()
    lines = ["# Expert policy differences", "", f"Matched episodes: {result['matched_episodes']} | Decisions: {result['decisions']}", "", "| Context | Phase | Turn | Opponent | Archetype | N | Wins | Losses | Agree | Differ | Overlap |", "|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['context']} | {r['phase']} | {r['turn']} | {r['opponent']} | {r['archetype']} | {r['decisions']} | {r['wins']} | {r['losses']} | {r['agreement_rate']:.1%} | {r['difference_rate']:.1%} | {r['mean_action_overlap']:.1%} |" for r in result["groups"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--replays", nargs="+", required=True); p.add_argument("--deck", required=True); p.add_argument("--format", choices=("json", "csv", "markdown"), default="json"); p.add_argument("--output", "-o"); p.add_argument("--threshold", type=float, default=1.0); a = p.parse_args(argv)
    target = [x.strip() for x in Path(a.deck).read_text(encoding="utf-8").splitlines() if x.strip()]; text = render(analyze(load_inputs(a.replays), target, a.threshold), a.format)
    if a.output: Path(a.output).write_text(text, encoding="utf-8")
    else: sys.stdout.write(text)

if __name__ == "__main__": main()
