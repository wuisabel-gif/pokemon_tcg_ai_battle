#!/usr/bin/env bash
# Run local battles inside a Linux x86-64 container, because the cg engine ships
# only as a Linux .so (won't load on macOS). All arguments are forwarded to
# tools/run_match.py.
#
# Examples:
#   ./tools/test_local.sh                          # submission vs random, 20 games
#   ./tools/test_local.sh -n 40                     # submission vs random, 40 games
#   ./tools/test_local.sh --a submission --b baseline -n 40
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

docker run --rm --platform linux/amd64 \
  -v "$REPO":/work -w /work \
  python:3.11-slim \
  python tools/run_match.py "$@"
