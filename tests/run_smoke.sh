#!/usr/bin/env bash
# run_smoke.sh
# Wrapper that installs required deps if missing, then runs the smoke test.
# Run from anywhere; it cd's to the repo root. Exit code mirrors the test.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> Ensuring dependencies (jinja2, PyYAML, requests)..."
python3 -m pip install --quiet \
    "jinja2>=3.0.0" \
    "PyYAML>=6.0" \
    "requests>=2.25.0" \
    || { echo "ERROR: dependency install failed" >&2; exit 1; }

echo "==> Running smoke test..."
python3 tests/smoke_test.py
