#!/usr/bin/env python3
"""verify_x_bookmarks.py — smoke test for the X bookmarks pipeline.

Checks:
  1. Cookies are readable + decryptable from the Keychain/Brave DB (without
     printing their values).
  2. fetch_x_bookmarks.py runs and returns N > 0 bookmarks.
Prints a compact one-line summary.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
X_BOOKMARKS = DATA_DIR / "x_bookmarks.json"


def main():
    # Step 1: cookies decryptable (import the fetch module's reader)
    sys.path.insert(0, str(SCRIPT_DIR))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fetch_x_bookmarks", SCRIPT_DIR / "fetch_x_bookmarks.py")
    if spec is None or spec.loader is None:
        print("VERIFY FAIL | could not load fetch_x_bookmarks module")
        sys.exit(1)
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)

    cookie_err = ""
    try:
        cookies = fetch.read_x_cookies()
        ok_names = [k for k in ("auth_token", "ct0") if k in cookies]
        cookie_ok = len(ok_names) == 2
    except Exception as e:
        cookies, cookie_ok = {}, False
        cookie_err = str(e)

    if not cookie_ok:
        print(f"VERIFY FAIL | cookies: NOT decryptable ({cookie_err})")
        sys.exit(1)

    # Step 2: run the real fetcher
    r = subprocess.run([sys.executable, str(SCRIPT_DIR / "fetch_x_bookmarks.py")],
                       capture_output=True, text=True, timeout=420)
    print(r.stdout.strip())

    if not X_BOOKMARKS.exists():
        print("VERIFY FAIL | fetch produced no data file")
        sys.exit(1)
    with open(X_BOOKMARKS) as f:
        bookmarks = json.load(f)
    n = len(bookmarks)

    if n > 0:
        sample = next((b for b in bookmarks if b.get("text")), {})
        sample_txt = (sample.get("text") or "")[:60].replace("\n", " ")
        print(f"VERIFY PASS | bookmarks fetched: {n} | sample: @{sample.get('author')} "
              f"\"{sample_txt}\"")
    else:
        print("VERIFY FAIL | 0 bookmarks fetched")
        sys.exit(1)


if __name__ == "__main__":
    main()
