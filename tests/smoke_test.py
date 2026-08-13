#!/usr/bin/env python3
# smoke_test.py
# Self-contained smoke test for the StarLearner-Nexus skill generator.
# Builds an inline fixture, runs generate_skill() in-process, and asserts:
#   (a) output SKILL.md frontmatter starts with '---' at byte 0
#   (b) no literal '{{' or '}}' placeholders remain in output
#   (c) repo_html_url resolves (no empty 'Original repository:' source)
#   (d) author is the repo owner (not 'GitHub Community')
#   (e) related_skills is empty []
#   (f) categorize_repo() does NOT mis-classify an 'email' repo as ai-ml
# Prints PASS/FAIL per assertion and exits 0 only if all pass.
#
# Uses only the stdlib plus the repo's own scripts (imported via sys.path).

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the repo's own modules (must succeed; deps are jinja2/yaml/requests,
# all present in the environment per verify_installation.py).
import generate_skills  # noqa: E402
import categorize_repos  # noqa: E402


def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    suffix = f"  [{detail}]" if detail and not ok else ""
    print(f"{status}: {label}{suffix}")
    return ok


def extract_frontmatter_field(text, field):
    """Pull `field: <value>` out of the YAML frontmatter (stdlib-only)."""
    m = re.search(
        rf"(?m)^{re.escape(field)}:\s*(.*)$",
        text,
    )
    if not m:
        return None
    return m.group(1).strip()


def main():
    results = []

    # --- Inline fixture: a small categorized repo set ---------------------
    # owner.login is set so assertion (d) can check author resolution.
    fixture_repo = {
        "name": "doomnet",
        "description": "A resilient mesh networking toolkit for planetary-scale coordination",
        "html_url": "https://github.com/DrDoom/doomnet",
        "url": "https://api.github.com/repos/DrDoom/doomnet",
        "owner": {"login": "DrDoom"},
        "language": "Python",
        "stargazers_count": 42,
        "forks_count": 7,
        "topics": ["networking", "mesh", "python"],
        "license": {"name": "MIT"},
        "size": 5000,
        "watchers_count": 20,
        "homepage": "https://doomnet.example",
    }
    category_key = "development-tools"

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        skill_file, status = generate_skills.generate_skill(
            fixture_repo, category_key, out_dir
        )
        rendered = skill_file.read_text()

        # (a) frontmatter starts with '---' at byte 0
        ok = rendered.startswith("---")
        results.append(check(
            "output starts with '---' at byte 0",
            ok,
            f"first 3 bytes: {rendered[:3]!r}",
        ))

        # (b) no literal '{{' or '}}' placeholders remain
        ok = ("{{" not in rendered) and ("}}" not in rendered)
        results.append(check(
            "no '{{' or '}}' placeholders remain",
            ok,
            "unrendered Jinja placeholder found",
        ))

        # (c) repo_html_url resolves: the real repo URL appears in output and
        #     there is no empty 'Original repository:'/'from:' source.
        ok = (
            fixture_repo["html_url"] in rendered
            and "Original repository: \n" not in rendered
            and "from: \n" not in rendered
        )
        results.append(check(
            "repo_html_url resolves (no empty source)",
            ok,
            f"expected URL {fixture_repo['html_url']} in output",
        ))

        # (d) author is the repo owner, not 'GitHub Community'
        author = extract_frontmatter_field(rendered, "author")
        ok = author == f'"{fixture_repo["owner"]["login"]}"' and "GitHub Community" not in rendered
        results.append(check(
            "author is repo owner (DrDoom), not 'GitHub Community'",
            ok,
            f"author field: {author!r}",
        ))

        # (e) related_skills is empty []
        related = extract_frontmatter_field(rendered, "related_skills")
        try:
            parsed = json.loads(related)
            ok = parsed == []
        except (TypeError, json.JSONDecodeError):
            parsed = None
            ok = False
        results.append(check(
            "related_skills is empty []",
            ok,
            f"related_skills: {related!r}",
        ))

        # (f) categorize_repo() does NOT mis-classify an email repo as ai-ml
        email_repo = {
            "name": "email-client",
            "description": "a simple imap email client",
            "topics": ["email", "smtp", "imap", "mail"],
        }
        categories = categorize_repos.load_categories()
        cat = categorize_repos.categorize_repo(email_repo, categories)
        ok = cat != "ai-ml"
        results.append(check(
            "email repo NOT mis-classified as ai-ml",
            ok,
            f"got category: {cat!r}",
        ))

    all_pass = all(results)
    print(f"\n{'ALL SMOKE TESTS PASSED' if all_pass else 'SOME SMOKE TESTS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
