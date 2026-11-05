#!/usr/bin/env python3
"""test_grep_gate.py — the forbidden-strings gate (a BUILD STEP, not a
final sweep: mission rule 3 — zero client/personal/company names in the
shipped tree).

Scans every file the catalog would pin (``git ls-files`` when the tree is
a repo — i.e. the exact shipped set — else a walk excluding the
gitignored runtime dirs), everything EXCEPT ``tests/`` (the gate's own
fixtures + the test harness legitimately reference the host machine's
hermes checkout path — a build-time fact, never shipped data), for:

  * personal paths (/Users/<name>, the home shorthand);
  * personal names + handles + company names (the de-hardcode list);
  * machine-local absolute paths;
  * secrets/key material (report-as-fail: the trees have none — keep it
    that way);
  * R17 junk that must never be tracked (pyc/__pycache__/.DS_Store/._*,
    the runtime data dirs data/ logs/ generated_skills/, .last_sync*).

The patterns are case-insensitive where a name can appear in prose.
Known false-positive classes are avoided by construction (e.g. the
'okin' substring inside 'booking'/'forward-looking' is NOT matched —
only the whole-word/company forms are).
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (pattern, why) — the de-hardcode list, per the mission + skill doctrine.
FORBIDDEN = [
    (r"fromthejump", "personal username/home path"),
    (r"/Users/fromthejump", "personal absolute path"),
    (r"/Users/[a-z]+/", "machine-local absolute path"),
    (r"Nikolai", "personal name"),
    (r"Tjongarero", "personal name"),
    (r"OKIN_17", "personal handle"),
    (r"okin ent", "company name"),
    (r"okinent", "company name"),
    (r"smart polar", "company name"),
    (r"BitcoinFrndly", "personal handle"),
]

# Secret/key material (the trees have none; the gate keeps it that way).
SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "OpenAI-style API key material"),
    (r"ghp_[A-Za-z0-9]{20,}", "GitHub PAT material"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained PAT material"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"(?i)(api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9/+_-]{24,}['\"]",
     "a hardcoded credential assignment"),
]

# R17: never tracked.
NEVER_TRACKED = [
    r"__pycache__", r"\.pyc$", r"\.pyo$", r"\.DS_Store", r"^\._",
    r"\.pyi$", r"\.dylib$", r"\.a$", r"\.bin$",
]
# The gitignored runtime dirs (untracked local state; a clean clone of the
# pinned commit must contain none of them).
RUNTIME_DIRS = ("data", "logs", "generated_skills")


def _shipped_files():
    """The exact set the catalog would pin: git ls-files when in a repo."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True,
            timeout=30, check=True)
        files = [Path(REPO_ROOT / f) for f in
                 out.stdout.decode("utf-8").split("\0") if f]
        if files:
            return files, True
    except Exception:
        pass
    # not a repo (a raw export): walk, skipping the runtime + cache dirs
    skip = {".git", "__pycache__", ".pytest_cache", ".mypy_cache",
            ".venv", "node_modules"} | set(RUNTIME_DIRS)
    files = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(part in skip for part in rel.parts):
            continue
        files.append(path)
    return files, False


def _scan(files, patterns):
    hits = []
    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, why in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                line = text.count("\n", 0, m.start()) + 1
                hits.append((rel, line, m.group(0), why))
    return hits


class GrepGateTests(unittest.TestCase):

    def test_tree_is_a_git_repo(self):
        """The pinned set must be the TRACKED files (R16/R17 evidence)."""
        _, is_repo = _shipped_files()
        self.assertTrue(is_repo, "the tree must be a git repo so the "
                                 "gate scans the exact pinned set")

    def test_no_forbidden_strings_in_the_shipped_tree(self):
        files, is_repo = _shipped_files()
        self.assertTrue(files)
        scanned = [f for f in files
                   if f.relative_to(REPO_ROOT).parts[0] != "tests"]
        hits = _scan(scanned, FORBIDDEN)
        self.assertEqual(hits, [], "forbidden strings in the shipped "
                                   "tree: %r" % (hits[:10],))

    def test_no_secrets_in_the_shipped_tree(self):
        files, _ = _shipped_files()
        # the whole tree, tests included (a secret is a secret anywhere)
        hits = _scan(files, SECRET_PATTERNS)
        self.assertEqual(hits, [], "secret-looking material: %r"
                         % (hits[:10],))

    def test_r17_never_tracked(self):
        files, is_repo = _shipped_files()
        if not is_repo:
            self.skipTest("not a repo")
        for rel in (f.relative_to(REPO_ROOT).as_posix() for f in files):
            for pattern in NEVER_TRACKED:
                self.assertIsNone(
                    re.search(pattern, rel.split("/")[-1]),
                    "R17 junk tracked: %r (pattern %r)" % (rel, pattern))

    def test_runtime_data_dirs_not_tracked(self):
        """The pinned commit must ship NONE of the runtime dirs (the
        clean-clone half of the R17/R11-hygiene check)."""
        files, is_repo = _shipped_files()
        if not is_repo:
            self.skipTest("not a repo")
        for f in files:
            parts = f.relative_to(REPO_ROOT).parts
            self.assertNotIn(parts[0], RUNTIME_DIRS,
                             "runtime data tracked: %r" % f)
            self.assertFalse(
                f.name.startswith(".last_sync"),
                "the cron gate file is runtime state: %r" % f)

    def test_the_gate_itself_holds_the_forbidden_strings(self):
        """The gate's own fixtures legitimately hold them (the scan covers
        everything but tests/) — proves the scanner actually matches."""
        hits = _scan([Path(__file__)],
                     [(r"fromthejump", "selftest")])
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
