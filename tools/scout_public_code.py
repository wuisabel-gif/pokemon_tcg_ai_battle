"""Scout public Kaggle notebooks related to the competition.

This is a research/code-discovery tool, not an automatic production-code importer.
Kaggle does not expose a reliable Gold-medal flag through the public API, so the
manifest prioritizes leaderboard rank/score and notebook votes as transparent
proxies. Downloaded notebooks are written under the gitignored ``kaggle_code/``.

Usage:
    python3 tools/scout_public_code.py --top-players 20 --top-kernels 30
    python3 tools/scout_public_code.py --no-download
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

COMPETITION = "pokemon-tcg-ai-battle"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "kaggle_code" / "public_scout"


def field(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value not in (None, ""):
            return value
    return default


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def leaderboard(api: Any, limit: int) -> list[dict[str, Any]]:
    entries = list(api.competition_leaderboard_view(COMPETITION) or [])
    rows = []
    for position, entry in enumerate(entries, 1):
        score = number(field(entry, "score", "public_score"))
        if score is None:
            continue
        rows.append({
            "rank": int(field(entry, "rank", "team_rank", default=position)),
            "team_name": str(field(entry, "team_name", "teamName", "name", default="")),
            "score": score,
            "team_id": field(entry, "team_id", "teamId", "_team_id"),
        })
    return sorted(rows, key=lambda row: row["rank"])[:limit]


def kernel_row(kernel: Any, source: str) -> dict[str, Any]:
    votes = int(field(kernel, "total_votes", "vote_count", "_total_votes", default=0) or 0)
    last_run = field(kernel, "last_run_time", "_last_run_time")
    ref = str(field(kernel, "ref", "_ref", default=""))
    return {
        "ref": ref,
        "title": str(field(kernel, "title", "_title", default="")),
        "author": str(field(kernel, "author", "_author", default="")),
        "votes": votes,
        "last_run_time": str(last_run) if last_run else None,
        "source": source,
        "public_url": "https://www.kaggle.com/code/" + ref,
    }


def score_kernel(row: dict[str, Any], players: list[dict[str, Any]]) -> tuple[float, ...]:
    """Rank transparent signals; Gold itself is not available in this API."""
    author = normalize(row["author"])
    title = normalize(row["title"])
    matched = max((1000 - p["rank"] for p in players
                   if normalize(p["team_name"]) in {author, title}
                   or author in normalize(p["team_name"])), default=0)
    return (matched, row["votes"], 0 if row["source"] == "leaderboard_search" else -1)


def analyze_download(directory: Path) -> dict[str, Any]:
    """Extract lightweight signals without executing public competitor code."""
    text_parts = []
    for notebook in directory.rglob("*.ipynb"):
        try:
            document = json.loads(notebook.read_text())
            for cell in document.get("cells", []):
                if cell.get("cell_type") == "code":
                    text_parts.append("".join(cell.get("source", [])))
        except (OSError, json.JSONDecodeError):
            continue
    text = "\n".join(text_parts)
    lowered = text.lower()
    return {
        "notebooks": len(list(directory.rglob("*.ipynb"))),
        "code_lines": len(text.splitlines()),
        "has_mcts": bool(re.search(r"\bmcts\b|monte.?carlo|search_begin|puct", lowered)),
        "has_reinforcement_learning": bool(re.search(r"reinforcement|self.?play|policy.?value|actor.?critic", lowered)),
        "has_submission_agent": bool(re.search(r"def\s+agent\s*\(", text)),
        "has_search_api": "search_step" in lowered or "search_begin" in lowered,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-players", type=int, default=20)
    parser.add_argument("--top-kernels", type=int, default=30)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()

    token = Path.home() / ".kaggle" / "access_token"
    if token.exists():
        os.environ.setdefault("KAGGLE_API_TOKEN", token.read_text().strip())
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    players = leaderboard(api, args.top_players)
    if not players:
        raise RuntimeError("No scored leaderboard rows were returned")

    found: dict[str, dict[str, Any]] = {}
    for player in players:
        query = player["team_name"].strip()
        if query:
            try:
                for kernel in api.kernels_list(competition=COMPETITION, search=query, page_size=100) or []:
                    row = kernel_row(kernel, "leaderboard_search")
                    if row["ref"]:
                        found[row["ref"]] = row
            except Exception as exc:
                player["search_error"] = str(exc)
    try:
        for kernel in api.kernels_list(competition=COMPETITION, page_size=100, sort_by="voteCount") or []:
            row = kernel_row(kernel, "competition_votes")
            if row["ref"]:
                found[row["ref"]] = row
    except Exception as exc:
        print("Competition notebook listing failed:", exc)

    ranked = sorted(found.values(), key=lambda row: score_kernel(row, players), reverse=True)[:args.top_kernels]
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "competition": COMPETITION,
        "players": players,
        "gold_status": "not exposed by Kaggle API; rank, score, and votes are used as proxies",
        "kernels": ranked,
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if not args.no_download:
        code_dir = args.out / "notebooks"
        code_dir.mkdir(exist_ok=True)
        for index, row in enumerate(ranked, 1):
            target = code_dir / f"{index:02d}_{row['ref'].replace('/', '__')}"
            try:
                api.kernels_pull(row["ref"], path=str(target), metadata=True, quiet=True)
                row["downloaded_to"] = str(target.relative_to(ROOT))
                row["code_signals"] = analyze_download(target)
            except Exception as exc:
                row["download_error"] = str(exc)
            time.sleep(0.2)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"Leaderboard players: {len(players)}")
    print(f"Public notebooks selected: {len(ranked)}")
    for row in ranked[:10]:
        print(f"  {row['votes']:4d} votes  {row['author'][:24]:24s}  {row['public_url']}")
    print("Manifest:", manifest_path)


if __name__ == "__main__":
    main()
