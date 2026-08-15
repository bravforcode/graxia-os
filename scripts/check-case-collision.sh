#!/bin/sh
set -e -o pipefail
dupes=$(git ls-files | tr '[:upper:]' '[:lower:]' | sort | uniq -d)
if [ -n "$dupes" ]; then
  echo "ERROR: case-collision detected in tracked files:"; echo "$dupes"; exit 1
fi
echo "case-collision: OK"
