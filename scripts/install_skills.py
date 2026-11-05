#!/usr/bin/env python3
"""StarLearner-Nexus v2 — INSTALL GATE (the 'evolve, don't collect' fix).

Scans the repo's generated_skills/ for skill candidates and installs ONLY the
ones that pass the gate into the live Hermes skills dir. Gate rules:
  1. SKILL.md must exist with YAML frontmatter (name: or directory name).
  2. Target skill dir must not already exist (never overwrite a live skill).
  3. Name must not collide with any installed skill (kills the duplicate-name
     shadow class that made generated skills unloadable).
  4. Size sanity: no single file > 2 MB, total < 10 MB.
Every decision (installed / skipped / rejected + reason) lands in
data/install_ledger.json so the fleet can audit what it grew.

Usage:
    python3 install_skills.py [--dry-run] [--source <generated_skills_dir>]
"""
import json
import os
import re
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DEFAULT = os.path.join(REPO, "generated_skills")
LIVE_SKILLS = "/Users/fromthejump/.hermes/skills"
LEDGER = os.path.join(REPO, "data", "install_ledger.json")
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 10 * 1024 * 1024

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
NAME_RE = re.compile(r"^name:\s*['\"]?([\w.-]+)", re.MULTILINE)


def skill_identity(skill_md_path, dir_name):
    """Return the declared skill name or None if frontmatter is missing."""
    try:
        with open(skill_md_path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(4000)
    except OSError:
        return None
    m = FRONTMATTER.search(head)
    if not m:
        return None
    nm = NAME_RE.search(m.group(1))
    return nm.group(1) if nm else dir_name


def gate_candidate(src_dir):
    """Return (ok, name, reason)."""
    skill_md = os.path.join(src_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        return False, None, "no SKILL.md"
    name = skill_identity(skill_md, os.path.basename(src_dir))
    if not name:
        return False, None, "no frontmatter/name"
    if os.path.sep + "." in src_dir[len(SOURCE_DEFAULT):]:
        return False, name, "hidden path"
    total = 0
    for root, _dirs, files in os.walk(src_dir):
        for f in files:
            p = os.path.join(root, f)
            sz = os.path.isfile(p) and os.path.getsize(p) or 0
            total += sz
            if sz > MAX_FILE:
                return False, name, f"file too large: {f}"
    if total > MAX_TOTAL:
        return False, name, f"total too large: {total} bytes"
    return True, name, "ok"


def installed_names():
    """All skill names currently visible in the live skills tree (any tier)."""
    names = set()
    for root, dirs, files in os.walk(LIVE_SKILLS):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" in files:
            names.add(os.path.basename(root))
    return names


def main():
    # Default = REPORT ONLY. Nothing enters the live tree without --install
    # ("evolve, don't collect": bulk-installing 57 unproven skills would just
    # rebuild the collection disease).
    install = "--install" in sys.argv
    dry = not install
    source = SOURCE_DEFAULT
    if "--source" in sys.argv:
        source = sys.argv[sys.argv.index("--source") + 1]
    installed, skipped, rejected = [], [], []
    seen_names = set()
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" not in files:
            continue
        ok, name, reason = gate_candidate(root)
        if not ok:
            rejected.append({"path": root, "name": name, "reason": reason})
            continue
        leaf = os.path.basename(root)
        target = os.path.join(LIVE_SKILLS, leaf)
        if os.path.exists(target):
            skipped.append({"path": root, "name": name, "reason": "already installed"})
            continue
        if name in installed_names() or name in seen_names:
            skipped.append({"path": root, "name": name,
                            "reason": "name collision with installed skill"})
            continue
        seen_names.add(name)
        if dry:
            installed.append({"path": root, "name": name, "dry_run": True})
            continue
        shutil.copytree(root, target)
        installed.append({"path": root, "name": name, "dest": target})
    entry = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": dry,
        "installed": installed,
        "skipped": skipped,
        "rejected": rejected,
    }
    if not dry:
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        try:
            ledger = json.load(open(LEDGER))
        except Exception:
            ledger = []
        ledger.append(entry)
        ledger = ledger[-200:]
        with open(LEDGER, "w") as fh:
            json.dump(ledger, fh, indent=1)
    # compact one-line result for cron stdout
    print(f"StarLearner gate: {len(installed)} installed, {len(skipped)} skipped, "
          f"{len(rejected)} rejected{' (dry-run)' if dry else ''}")
    for r in rejected[:5]:
        print(f"  rejected: {r['name'] or r['path']}: {r['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
