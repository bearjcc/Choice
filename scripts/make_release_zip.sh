#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/opt/cursor/artifacts/choice-0.4.1.zip}"
# Version tag is bumped in choice/__init__.py; default outfile name should match release.
rm -f "$OUT"
cd "$ROOT"
zip -q -r "$OUT" . \
  -x '*/.git/*' \
  -x '.git/*' \
  -x 'uploads/*' \
  -x '*/__pycache__/*' \
  -x '*.pyc' \
  -x '.ruff_cache/*' \
  -x '*/.ruff_cache/*' \
  -x '.pytest_cache/*' \
  -x '*/.pytest_cache/*' \
  -x 'build/*' \
  -x '*/build/*' \
  -x '*.egg-info/*' \
  -x '*/*.egg-info/*' \
  -x '.choice-smoke-state/*' \
  -x 'examples/*/.choice/*' \
  -x 'examples/**/.choice/**'
sha256sum "$OUT"
echo "$OUT"
