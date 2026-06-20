#!/usr/bin/env python3
"""Parallel local match runner.

Fans out many Docker workers (each running a slice of the games) to get a large,
statistically meaningful sample in a fraction of the wall-clock. The cg engine is
entropy-seeded per process, so independent workers produce independent games.

Runs natively on macOS; each worker is a linux/amd64 container.

Usage:
    python3 tools/test_parallel.py --a submission --b baseline -n 200 -j 6

Output: aggregated win rate with a 95% confidence interval, plus per-seat splits.
A change is only "real" if the CI clears 50% (vs baseline).
"""
import os
import re
import sys
import json
import math
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT_RE = re.compile(r"^RESULT (\{.*\})\s*$", re.MULTILINE)


def run_worker(a: str, b: str, n: int, idx: int) -> dict:
    cmd = [
        "docker", "run", "--rm", "--platform", "linux/amd64",
        "-v", f"{REPO}:/work", "-w", "/work",
        "python:3.11-slim",
        "python", "tools/run_match.py", "--a", a, "--b", b, "-n", str(n), "--json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    m = RESULT_RE.search(out.stdout)
    if not m:
        sys.stderr.write(f"[worker {idx}] no RESULT line.\nstdout:\n{out.stdout}\nstderr:\n{out.stderr}\n")
        return {"n": 0, "wins": 0, "seat_wins": [0, 0], "seat_games": [0, 0]}
    return json.loads(m.group(1))


def wilson_ci(wins: int, n: int, z: float = 1.96):
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (center - half, center + half)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="submission")
    ap.add_argument("--b", default="baseline")
    ap.add_argument("-n", type=int, default=200, help="total games")
    ap.add_argument("-j", type=int, default=6, help="parallel workers")
    args = ap.parse_args()

    per = max(1, args.n // args.j)
    slices = [per] * args.j
    slices[-1] += args.n - per * args.j  # remainder to last worker

    print(f"Running {sum(slices)} games of [{args.a}] vs [{args.b}] "
          f"across {args.j} workers ({per}/worker)...", flush=True)

    totals = {"n": 0, "wins": 0, "seat_wins": [0, 0], "seat_games": [0, 0]}
    with ThreadPoolExecutor(max_workers=args.j) as ex:
        futs = [ex.submit(run_worker, args.a, args.b, slices[i], i) for i in range(args.j)]
        done = 0
        for f in as_completed(futs):
            r = f.result()
            totals["n"] += r["n"]
            totals["wins"] += r["wins"]
            for s in (0, 1):
                totals["seat_wins"][s] += r["seat_wins"][s]
                totals["seat_games"][s] += r["seat_games"][s]
            done += 1
            print(f"  worker {done}/{args.j} done "
                  f"({totals['wins']}/{totals['n']} so far)", flush=True)

    n, wins = totals["n"], totals["wins"]
    rate = wins / n if n else 0.0
    lo, hi = wilson_ci(wins, n)
    print("\n" + "=" * 56)
    print(f"[{args.a}] vs [{args.b}]")
    print(f"  overall: {wins}/{n} = {rate:.1%}   95% CI [{lo:.1%}, {hi:.1%}]")
    for s in (0, 1):
        sg, sw = totals["seat_games"][s], totals["seat_wins"][s]
        if sg:
            slo, shi = wilson_ci(sw, sg)
            print(f"  as P{s}:   {sw}/{sg} = {sw / sg:.1%}   95% CI [{slo:.1%}, {shi:.1%}]")
    if args.b != "random":
        verdict = ("BETTER than baseline" if lo > 0.5
                   else "WORSE than baseline" if hi < 0.5
                   else "NOT distinguishable from baseline (CI spans 50%)")
        print(f"  verdict: {verdict}")
    print("=" * 56)


if __name__ == "__main__":
    main()
