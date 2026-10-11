#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/opt/cursor/artifacts/choice-0.5.2.zip}"
REF="${CHOICE_RELEASE_GIT_REF:-HEAD}"
# Version tag is bumped in choice/__init__.py; default outfile name should match release.
cd "$ROOT"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "make_release_zip.sh must run inside a git checkout." >&2
  exit 1
fi
rm -f "$OUT"
git archive --format=zip -o "$OUT" "$REF"
sha256sum "$OUT"
ls -lh "$OUT" | awk '{print $5, $9}'
echo "$OUT"
