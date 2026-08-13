#!/usr/bin/env bash
# Run replay-vs-policy comparison inside the Linux x86-64 container, because
# loading the agent imports the cg engine (.so won't load on macOS).
# Replay directories must live inside the repo to be visible in the container.
#
# Example:
#   cp /tmp/sub55443071/*.json data/replays_latest/
#   ./tools/compare_replays.sh --replays data/replays_latest \
#       --team "Isabella Wu" --agent submission --format markdown
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

docker run --rm --platform linux/amd64 \
  -v "$REPO":/work -w /work \
  python:3.11-slim \
  python tools/replay_policy_compare.py "$@"
