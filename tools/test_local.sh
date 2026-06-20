#!/usr/bin/env bash
# Run local battles for the agent inside a Linux x86-64 container,
# because the cg engine ships only as a Linux .so (won't load on macOS).
#
# Usage:  ./tools/test_local.sh [n_games]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
N="${1:-20}"

docker run --rm --platform linux/amd64 \
  -v "$REPO":/work -w /work \
  python:3.11-slim \
  python tools/run_match.py "$N"
