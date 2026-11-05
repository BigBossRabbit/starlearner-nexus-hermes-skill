#!/usr/bin/env python3
"""StarLearner-Nexus v2 — USAGE LEDGER (closes the loop: which skills earn their place).

Scans every Hermes profile's state.db for evidence that a generated skill was
actually loaded/mentioned in sessions, then writes data/usage_ledger.json and
prints a compact used/dead report.

With --prune: skills with ZERO usage evidence whose files are older than 90
days are MOVED (never deleted) to <live-skills>/.attic/ — fully reversible.

Usage:
    python3 usage_ledger.py [--prune] [--min-age-days 90]
"""
import glob
import json
import os
import shutil
import sqlite3
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_OUT = os.path.join(REPO, "data", "usage_ledger.json")
# The live skills tree + the profile state DBs (portable): the hermes home
# ($HERMES_HOME, default ~/.hermes), overridable with --live-skills /
# --state-dbs. STANDALONE-ONLY tool (plugin v1 never reads these).
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
LIVE_SKILLS = os.path.join(HERMES_HOME, "skills")
ATTIC = os.path.join(LIVE_SKILLS, ".attic")


def _state_dbs():
    return (glob.glob(os.path.join(HERMES_HOME, "profiles", "*",
                                    "state.db"))
            + [os.path.join(HERMES_HOME, "state.db")])


def candidate_skills():
    """Top-level installed skills that came from generated sources."""
    out = []
    for path in sorted(glob.glob(os.path.join(LIVE_SKILLS, "*", "SKILL.md"))):
        slug = os.path.basename(os.path.dirname(path))
        out.append((slug, path))
    return out


def usage_hits(slug, conn, text_cols, table):
    """True usage signal: successful skill_view loads only.

    Contamination found empirically (2026-10-25): the skills LIST rides along in
    system prompts, compaction summaries and failed-lookup dumps, so plain text
    matching counts every installed skill as 'used' (yuanbao: 258 fake hits).
    A real load produces a tool_name='skill_view' row whose result JSON contains
    "name": "<slug>" (double quotes); not-found errors use single quotes and are
    excluded. Verified: yuanbao=0, starlearner-nexus=36, hermes-agent=13.
    """
    try:
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE tool_name='skill_view' "
            f"AND content LIKE ?",
            (f'%"name": "{slug}"%',),
        )
        return cur.fetchone()[0] or 0
    except sqlite3.Error:
        return 0


def scan_db(db_path):
    """Return (conn, table, text_cols) for a profile state.db, or (None,).
    Prefers a table WITH an FTS5 shadow (<table>_fts) so counting is instant."""
    if not os.path.exists(db_path):
        return None,
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        # prefer a messages-like table that has an FTS5 shadow
        best = None
        for cand in ("messages", "events", "log"):
            if cand in tables:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({cand})")]
                text_cols = [
                    c for c, t in ((c, k) for c, k in zip(cols, [r[2] for r in conn.execute(f"PRAGMA table_info({cand})")]))
                    if "TEXT" in (t or "").upper() or "CHAR" in (t or "").upper()
                ]
                if text_cols:
                    best = (cand, text_cols)
                if f"{cand}_fts" in tables:
                    return conn, cand, text_cols
        if best:
            return (conn,) + best
        return None,
    except sqlite3.Error:
        return None,


def main():
    prune = "--prune" in sys.argv
    min_age = 90
    if "--min-age-days" in sys.argv:
        min_age = int(sys.argv[sys.argv.index("--min-age-days") + 1])
    now = time.time()
    report = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "profiles_scanned": [], "skills": []}
    conns = []
    for db in _state_dbs():
        opened = scan_db(db)
        if len(opened) > 1:
            conns.append((db,) + opened)
            report["profiles_scanned"].append(db)
    used, dead, pruned = [], [], []
    for slug, path in candidate_skills():
        hits = 0
        for _db, conn, _table, _cols in [(c[0], c[1], c[2], c[3]) for c in conns if len(c) > 1]:
            hits += usage_hits(slug, conn, _cols, _table)
        age_days = (now - os.path.getmtime(os.path.dirname(path))) / 86400
        entry = {"slug": slug, "usage_rows": hits, "age_days": round(age_days)}
        report["skills"].append(entry)
        if hits > 0:
            used.append(slug)
        else:
            dead.append(slug)
            if prune and age_days >= min_age:
                os.makedirs(ATTIC, exist_ok=True)
                dest = os.path.join(ATTIC, slug)
                if not os.path.exists(dest):
                    shutil.move(os.path.dirname(path), dest)
                    pruned.append(slug)
    report["summary"] = {
        "total": len(used) + len(dead),
        "used": len(used),
        "dead": len(dead),
        "pruned_to_attic": pruned,
    }
    os.makedirs(os.path.dirname(LEDGER_OUT), exist_ok=True)
    with open(LEDGER_OUT, "w") as fh:
        json.dump(report, fh, indent=1)
    for c in conns:
        if len(c) > 1:
            c[1].close()
    print(f"StarLearner usage: {report['summary']['total']} installed · "
          f"{len(used)} with usage evidence · {len(dead)} unused"
          + (f" · pruned {len(pruned)} to .attic" if prune else ""))
    if dead and not prune:
        print("  unused (no evidence yet): " + ", ".join(dead[:10])
              + (" …" if len(dead) > 10 else ""))
    if prune:
        print("  attic: " + (", ".join(pruned[:10]) + (" …" if len(pruned) > 10 else "") if pruned else "(nothing met the bar)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
