#!/usr/bin/env python3
# verify_installation.py
# Verifies the StarLearner-Nexus installation: required imports, executable
# scripts, and reference documentation. Prints PASS/FAIL per check.
# Exit code 0 if all checks pass, 1 otherwise.

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILL_DIR = SCRIPT_DIR.parent


def check(label, ok, detail=""):
    """Print a PASS/FAIL line for a check and return whether it passed."""
    status = "PASS" if ok else "FAIL"
    suffix = f"  [{detail}]" if detail and not ok else ""
    print(f"{status}: {label}{suffix}")
    return ok


def main():
    results = []

    # 1. Required Python modules importable
    try:
        import jinja2  # noqa: F401
        results.append(check("import jinja2", True))
    except ImportError as e:
        results.append(check("import jinja2", False, str(e)))

    try:
        import yaml  # noqa: F401
        results.append(check("import yaml", True))
    except ImportError as e:
        results.append(check("import yaml", False, str(e)))

    try:
        import requests  # noqa: F401
        results.append(check("import requests", True))
    except ImportError as e:
        results.append(check("import requests", False, str(e)))

    # 2. Scripts exist and are executable
    script_names = [
        "categorize_repos.py",
        "generate_skills.py",
        "fetch_starred_repos.sh",
        "daily_sync.sh",
    ]
    for name in script_names:
        script = SCRIPT_DIR / name
        exists = script.exists()
        executable = exists and os.access(script, os.X_OK)
        ok = exists and executable
        detail = "" if ok else (f"missing: {name}" if not exists else f"not executable: {name}")
        results.append(check(f"script executable: {name}", ok, detail))

    # 3. references/github_api.md exists
    api_ref = SKILL_DIR / "references" / "github_api.md"
    results.append(check(
        "references/github_api.md exists",
        api_ref.exists(),
        "missing: references/github_api.md",
    ))

    all_pass = all(results)
    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
