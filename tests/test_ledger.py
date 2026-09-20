#!/usr/bin/env python3
"""test_ledger.py — tests for the incremental seen-ledger.

Covers the three behaviours that matter:
  (a) cold start: an empty ledger reports every item as NEW
  (b) idempotency: after recording, a re-diff reports 0 NEW
  (c) partial: recording only some items leaves the rest NEW
  (d) identity: GitHub id/full_name and _bookmark_id keys are stable

Runs in-process against the repo's own scripts/ledger.py. Exits 0 only if all
assertions pass.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import ledger  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def make_repos():
    """A small fixture with mixed identity shapes."""
    return [
        {"id": 1, "full_name": "owner/alpha", "name": "alpha",
         "description": "an ai agent cli tool", "stargazers_count": 500},
        {"id": 2, "full_name": "owner/beta", "name": "beta",
         "description": "bitcoin lightning wallet", "stargazers_count": 2000},
        {"_bookmark_id": "tweet-abc", "name": "bookmark-one",
         "description": "a logistics thread", "stargazers_count": 0},
    ]


def main():
    print("ledger tests")
    repos = make_repos()

    # (a) cold start: empty ledger -> all NEW
    empty = ledger.load_ledger(Path("/nonexistent/ledger.json"))
    new = ledger.diff_new(repos, empty)
    check("cold start: all items NEW", len(new) == len(repos))

    # (b) idempotency: record all, re-diff -> 0 NEW
    updated = ledger.update_ledger(empty, repos, source="test")
    new2 = ledger.diff_new(repos, updated)
    check("idempotency: re-diff is 0 NEW", len(new2) == 0)

    # (c) partial: record only the first repo, rest stay NEW
    empty2 = ledger.load_ledger(Path("/nonexistent/ledger2.json"))
    updated2 = ledger.update_ledger(empty2, repos[:1], source="test")
    new3 = ledger.diff_new(repos, updated2)
    check("partial: 2 of 3 remain NEW", len(new3) == 2)

    # (d) identity stability: same item keyed identically across calls
    k1 = ledger.item_key(repos[0])
    k2 = ledger.item_key({"id": 1, "full_name": "owner/alpha", "name": "alpha"})
    check("identity: id key stable", k1 == k2 and k1 == "id:1")

    k3 = ledger.item_key(repos[2])
    k4 = ledger.item_key({"_bookmark_id": "tweet-abc", "name": "bookmark-one"})
    check("identity: _bookmark_id key stable", k3 == k4 and k3 == "tweet:tweet-abc")

    # (e) save/load round-trip preserves items
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ledger.json"
        ledger.save_ledger(updated, p)
        reloaded = ledger.load_ledger(p)
        check("save/load round-trip", len(reloaded["items"]) == len(repos))

    print(f"\n{'-'*40}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
