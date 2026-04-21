#!/usr/bin/env bash
# Rebuild the file-based Universal Skills Hub.
# Daily use does not require this script.

set -euo pipefail

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "Universal Skills Hub Reindex"
echo "========================================"
echo ""

python3 scripts/consolidate_all_skills.py
echo ""
python3 scripts/verify_skills_hub.py

echo ""
echo "Universal Skills Hub is ready. No background process is required."
