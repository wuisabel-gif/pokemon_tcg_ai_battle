#!/usr/bin/env python3
"""Portable diagnostics for Pokémon TCG replay and normalized episode data.

This module intentionally imports only the Python standard library.  In particular it
never imports ``submission`` or ``cg`` unless a caller explicitly supplies a callback
with ``--callback module:function``.

Replay convention: for Kaggle's player-cell arrays, an observation at step ``t`` is
paired with that player's action at step ``t+1``.  For normalized transition records,
explicit ``action_at_next``/``resulting_action`` fields take precedence.  Ambiguous
records are skipped rather than guessed.
"""
from __future__ import annotations
import argparse, csv, importlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable


def _as_list(value: Any) -> list:
    if value is None: return []
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: value = [x.strip() for x in value.split(",") if x.strip()]
    return value if isinstance(value, list) else [value]


def normalize_deck(deck: Any) -> tuple[str, ...]:
    """Return a canonical multiset representation (sorted card IDs/counts)."""
    cards = _as_list(deck)
    counts = Counter()
    for card in cards:
        if isinstance(card, dict):
            ident = card.get("id", card.get("card_id", card.get("name")))
            n = int(card.get("count", card.get("quantity", 1)) or 1)
            if ident is not None: counts[str(ident).strip()] += n
        elif card is not None and str(card).strip(): counts[str(card).strip()] += 1
    return tuple(f"{k}:{v}" for k, v in sorted(counts.items()))


def deck_similarity(a: Any, b: Any) -> float:
    """Multiset Jaccard similarity, with duplicate cards counted."""
    # normalize_deck is key:count; convert to card -> count.
    ma = {x.rsplit(":", 1)[0]: int(x.rsplit(":", 1)[1]) for x in normalize_deck(a)}
    mb = {x.rsplit(":", 1)[0]: int(x.rsplit(":", 1)[1]) for x in normalize_deck(b)}
    keys = set(ma) | set(mb)
    union = sum(max(ma.get(k, 0), mb.get(k, 0)) for k in keys)
    return sum(min(ma.get(k, 0), mb.get(k, 0)) for k in keys) / union if union else 1.0


def same_deck(deck: Any, target: Any, mode: str = "exact", threshold: float = 1.0) -> bool:
    if mode == "exact": return normalize_deck(deck) == normalize_deck(target)
    if mode in ("similarity", "jaccard"): return deck_similarity(deck, target) >= threshold
    raise ValueError("mode must be exact or similarity")


def _metadata(ep: dict) -> dict:
    meta = dict(ep.get("metadata", {})) if isinstance(ep.get("metadata"), dict) else {}
    for key in ("opponent", "opponent_id", "team", "archetype", "deck", "decklist", "seat", "winner", "result", "outcome"):
        if key in ep: meta.setdefault(key, ep[key])
    return meta


def _cells(ep: dict) -> list:
    if "observation" in ep or "obs" in ep:
        return [ep]
    steps = ep.get("steps", ep.get("trajectory", ep.get("records", ep.get("data", []))))
    return steps if isinstance(steps, list) else []


def iter_decisions(episode: dict) -> Iterable[dict]:
    """Yield normalized decision rows, without silently offsetting replay actions."""
    cells = _cells(episode); meta = _metadata(episode)
    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            if isinstance(cell, list):
                # Common Kaggle shape: [player-0 cell, player-1 cell].
                for seat, value in enumerate(cell):
                    if isinstance(value, dict):
                        following = cells[i + 1] if i + 1 < len(cells) and isinstance(cells[i + 1], list) else []
                        next_action = (following[seat].get("action")
                                        if seat < len(following) and isinstance(following[seat], dict)
                                        else None)
                        yield from _decision_cell(value, i, meta, seat, next_action)
            continue
        if "observation" in cell or "action" in cell:
            # Some exports store observation t and the resulting action in the
            # following transition.  Only use the immediate next cell; this
            # avoids silently pairing actions across gaps or player turns.
            following = cells[i + 1] if i + 1 < len(cells) and isinstance(cells[i + 1], dict) else {}
            yield from _decision_cell(cell, i, meta, cell.get("seat"), following.get("action"))
        else: # normalized rows often are already observation/action records
            yield from _decision_cell(cell, i, meta, cell.get("seat"))


def _decision_cell(cell: dict, step: int, meta: dict, seat: Any, next_action: Any = None) -> Iterable[dict]:
    obs = cell.get("observation", cell.get("obs"))
    action = cell.get("action_at_next", cell.get("resulting_action", next_action))
    if action is None:
        action = cell.get("action")
    if isinstance(obs, str):
        try: obs = json.loads(obs)
        except json.JSONDecodeError: pass
    if obs is None or action is None: return
    select = obs.get("select", {}) if isinstance(obs, dict) else {}
    row = dict(meta); row.update({"step": step, "seat": cell.get("seat", seat), "observation": obs, "action": action})
    # Optional recorded comparison candidate used by normalized expert/public
    # replay exports.  It is deliberately not inferred from submission code.
    for name in ("heuristic_action", "agent_action", "predicted_action", "expert_action", "public_action"):
        if name in cell: row[name] = cell[name]
    row["context"] = select.get("context", cell.get("context", row.get("context", "unknown")))
    row["legal_actions"] = select.get("option", select.get("options", cell.get("legal_actions", [])))
    yield row


def load_inputs(paths: Iterable[str]) -> list[dict]:
    episodes = []
    for name in paths:
        path = Path(name)
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8") as f: episodes.extend(dict(r) for r in csv.DictReader(f))
            continue
        data = json.loads(path.read_text(encoding="utf-8")); data = data if isinstance(data, list) else data.get("episodes", data.get("records", [data])) if isinstance(data, dict) else []
        episodes.extend(data)
    return episodes


def _actions(action: Any) -> tuple[str, ...]:
    return tuple(sorted(str(x) for x in _as_list(action)))


def analyze(episodes: Iterable[dict], target_deck: Any = None, deck_mode: str = "exact", threshold: float = 1.0, callback: Callable | None = None) -> dict:
    groups = defaultdict(lambda: {
        "decisions": 0, "wins": 0, "losses": 0,
        "comparisons": 0, "comparison_matches": 0,
        "win_comparisons": 0, "loss_comparisons": 0,
        "win_disagreements": 0, "loss_disagreements": 0,
        "action_overlap": 0.0,
    })
    episode_rows = []
    for number, ep in enumerate(episodes):
        if target_deck is not None and not same_deck(ep.get("deck", ep.get("decklist")), target_deck, deck_mode, threshold): continue
        meta = _metadata(ep); result = str(meta.get("result", meta.get("outcome", ""))).lower()
        win = result in ("win", "won", "1", "true"); loss = result in ("loss", "lost", "0", "false")
        decisions = list(iter_decisions(ep)); episode_rows.append({"episode": number, "result": result, "seat": meta.get("seat"), "opponent": meta.get("opponent", meta.get("opponent_id")), "archetype": meta.get("archetype"), "deck_similarity": deck_similarity(ep.get("deck", ep.get("decklist")), target_deck) if target_deck is not None else None})
        for row in decisions:
            key = tuple(str(row.get(k, "unknown")) for k in ("opponent", "team", "archetype", "seat", "context"))
            g = groups[key]; g["decisions"] += 1; g["wins"] += win; g["losses"] += loss
            comparison = None
            if callback:
                comparison = callback(row["observation"], row.get("legal_actions", []))
            else:
                comparison = next((row[k] for k in
                                   ("heuristic_action", "agent_action", "predicted_action")
                                   if k in row), None)
            if comparison is not None:
                observed = _actions(row["action"])
                predicted = _actions(comparison)
                same = observed == predicted
                overlap = (len(set(observed) & set(predicted)) /
                           len(set(observed) | set(predicted))
                           if observed or predicted else 1.0)
                g["comparisons"] += 1
                g["comparison_matches"] += same
                g["action_overlap"] += overlap
                if win:
                    g["win_comparisons"] += 1
                    g["win_disagreements"] += not same
                elif loss:
                    g["loss_comparisons"] += 1
                    g["loss_disagreements"] += not same
    rows = []
    for key, g in groups.items():
        row = dict(zip(("opponent", "team", "archetype", "seat", "context"), key)); row.update(g); n = g["decisions"]
        comparisons = g["comparisons"]
        row["comparison_rate"] = comparisons / n if n else 0
        row["match_rate"] = (g["comparison_matches"] / comparisons
                              if comparisons else None)
        row["mean_action_jaccard"] = (g["action_overlap"] / comparisons
                                       if comparisons else None)
        win_rate = (g["win_disagreements"] / g["win_comparisons"]
                    if g["win_comparisons"] else None)
        loss_rate = (g["loss_disagreements"] / g["loss_comparisons"]
                     if g["loss_comparisons"] else None)
        row["win_disagreement_rate"] = win_rate
        row["loss_disagreement_rate"] = loss_rate
        row["loss_disagreement_lift"] = (loss_rate - win_rate
                                          if loss_rate is not None and win_rate is not None
                                          else None)
        rows.append(row)
    rows.sort(key=lambda r: (r["loss_disagreement_lift"] is not None,
                             r["loss_disagreement_lift"] or float("-inf"),
                             r["comparisons"]), reverse=True)
    return {"groups": rows, "episodes": episode_rows, "matched_episodes": len(episode_rows), "decisions": sum(r["decisions"] for r in rows)}


def render(result: dict, fmt: str) -> str:
    if fmt == "json": return json.dumps(result, indent=2, sort_keys=True)
    rows = result["groups"]
    if fmt == "csv":
        fields = ["opponent", "team", "archetype", "seat", "context", "decisions", "wins", "losses", "comparisons", "comparison_rate", "match_rate", "mean_action_jaccard", "win_disagreement_rate", "loss_disagreement_rate", "loss_disagreement_lift"]
        out = []; import io; s = io.StringIO(); w = csv.DictWriter(s, fieldnames=fields); w.writeheader(); w.writerows({k:r.get(k,"") for k in fields} for r in rows); return s.getvalue()
    lines = ["# Replay diagnostics", "", f"Matched episodes: {result['matched_episodes']}  ", f"Decisions: {result['decisions']}", "", "| Opponent | Team | Archetype | Seat | Context | N | Comparisons | Match | Loss lift |", "|---|---|---|---:|---|---:|---:|---:|---:|"]
    def pct(value): return "—" if value is None else f"{value:.1%}"
    lines += [f"| {r['opponent']} | {r['team']} | {r['archetype']} | {r['seat']} | {r['context']} | {r['decisions']} | {r['comparisons']} ({r['comparison_rate']:.1%}) | {pct(r['match_rate'])} | {pct(r['loss_disagreement_lift'])} |" for r in rows]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("inputs", nargs="+"); p.add_argument("--deck"); p.add_argument("--deck-mode", choices=("exact", "similarity"), default="exact"); p.add_argument("--threshold", type=float, default=1.0); p.add_argument("--format", choices=("json", "csv", "markdown"), default="json"); p.add_argument("--output", "-o"); p.add_argument("--callback", help="module:function; called as callback(observation, legal_actions)")
    a = p.parse_args(argv); target = Path(a.deck).read_text().splitlines() if a.deck else None; cb = None
    if a.callback:
        mod, fn = a.callback.rsplit(":", 1); cb = getattr(importlib.import_module(mod), fn)
    text = render(analyze(load_inputs(a.inputs), target, a.deck_mode, a.threshold, cb), a.format)
    (Path(a.output).write_text(text) if a.output else sys.stdout.write(text))

if __name__ == "__main__": main()
