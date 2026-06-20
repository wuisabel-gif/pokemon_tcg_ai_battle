#!/usr/bin/env bash
# Package submission/ into submission.tar.gz and submit it to the competition.
#
# Usage:  ./tools/submit.sh "your submission message"
#
# Requires the Kaggle access token at ~/.kaggle/access_token (see kaggle-cli-auth).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
KAGGLE="$HOME/Library/Python/3.12/bin/kaggle"
COMP="pokemon-tcg-ai-battle"
MSG="${1:-Mega Lucario ex agent}"

cd "$REPO"
# Build a clean tarball matching the official layout (main.py, deck.csv, cg/ at root).
rm -f submission.tar.gz
rm -rf submission/cg/__pycache__
tar czf submission.tar.gz -C submission main.py deck.csv cg

echo "Tarball contents:"
tar tzf submission.tar.gz
echo
echo "Submitting to $COMP ..."
"$KAGGLE" competitions submit -c "$COMP" -f submission.tar.gz -m "$MSG"
echo
echo "Recent submissions:"
"$KAGGLE" competitions submissions -c "$COMP" | head -5
