#!/usr/bin/env python3
"""ledger.py — persistent "seen" ledger for incremental processing.

Tracks every item the pipeline has already taken into account so each run
only counts and assesses NEW items. This is the cross-run deduplication
boundary: fetch the full set, diff against the ledger, process only the new
ones, then record them.

Identity keys:
  - StarLearner (GitHub stars):  repo "id" (int) and "full_name" (owner/repo)
  - ReapX (X bookmarks):         tweet "_bookmark_id" (stable string)

The ledger is written ONLY after a successful run so a mid-run failure never
marks items as seen.

Usage (CLI):
  python3 ledger.py diff  <input.json> <ledger.json> <new_output.json>
  python3 ledger.py update <ledger.json> <new_output.json> [--source NAME]
  python3 ledger.py report <ledger.json>
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def item_key(item: dict) -> str:
    """Return a stable, unique key for an item.

    Prefers the strongest identity available: GitHub id, then full_name,
    then _bookmark_id, then name. Falls back to a hash of the item so we
    never silently collapse distinct items.
    """
    if item.get("id") is not None:
        return f"id:{item['id']}"
    if item.get("full_name"):
        return f"repo:{item['full_name']}"
    if item.get("_bookmark_id"):
        return f"tweet:{item['_bookmark_id']}"
    if item.get("name"):
        return f"name:{item['name']}"
    # Last resort: stable hash of the serialised item.
    import hashlib
    blob = json.dumps(item, sort_keys=True, default=str).encode("utf-8")
    return "hash:" + hashlib.sha256(blob).hexdigest()[:16]


def load_ledger(path: Path) -> dict:
    """Load the ledger; return an empty ledger if absent or corrupt."""
    if not path.exists():
        return {"version": 1, "source": "", "updated_at": "", "items": {}}
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict) or "items" not in data:
            return {"version": 1, "source": "", "updated_at": "", "items": {}}
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "source": "", "updated_at": "", "items": {}}


def diff_new(items: list, ledger: dict) -> list:
    """Return only items whose key is not already in the ledger."""
    seen = set(ledger.get("items", {}).keys())
    new = []
    for item in items:
        key = item_key(item)
        if key not in seen:
            new.append(item)
    return new


def update_ledger(ledger: dict, new_items: list, source: str = "") -> dict:
    """Record new items into the ledger (idempotent by key)."""
    items = ledger.setdefault("items", {})
    for item in new_items:
        key = item_key(item)
        if key not in items:
            items[key] = {
                "first_seen": _now_iso(),
                "integrated": False,
                "opportunity": None,
            }
    ledger["version"] = 1
    if source:
        ledger["source"] = source
    ledger["updated_at"] = _now_iso()
    return ledger


def save_ledger(ledger: dict, path: Path) -> None:
    """Atomically write the ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(ledger, f, indent=2)
    tmp.replace(path)


def report(ledger: dict) -> dict:
    """Return summary counts for the ledger."""
    items = ledger.get("items", {})
    integrated = sum(1 for v in items.values() if v.get("integrated"))
    opportunities = sum(1 for v in items.values() if v.get("opportunity"))
    return {
        "total_seen": len(items),
        "integrated": integrated,
        "opportunities": opportunities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seen-ledger for incremental processing")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help="Write only NEW items to new_output.json")
    p_diff.add_argument("input")
    p_diff.add_argument("ledger")
    p_diff.add_argument("new_output")

    p_upd = sub.add_parser("update", help="Record new items into the ledger")
    p_upd.add_argument("ledger")
    p_upd.add_argument("new_output")
    p_upd.add_argument("--source", default="")

    p_rep = sub.add_parser("report", help="Print ledger summary")
    p_rep.add_argument("ledger")

    args = parser.parse_args()

    if args.cmd == "diff":
        with open(args.input) as f:
            items = json.load(f)
        ledger = load_ledger(Path(args.ledger))
        new = diff_new(items, ledger)
        out = Path(args.new_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(new, f, indent=2)
        print(f"[ledger] {len(items)} total, {len(new)} NEW (not yet seen)")
        return 0

    if args.cmd == "update":
        ledger = load_ledger(Path(args.ledger))
        with open(args.new_output) as f:
            new = json.load(f)
        ledger = update_ledger(ledger, new, source=args.source)
        save_ledger(ledger, Path(args.ledger))
        r = report(ledger)
        print(f"[ledger] recorded {len(new)} new; total seen now {r['total_seen']}")
        return 0

    if args.cmd == "report":
        ledger = load_ledger(Path(args.ledger))
        r = report(ledger)
        print(json.dumps(r, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
