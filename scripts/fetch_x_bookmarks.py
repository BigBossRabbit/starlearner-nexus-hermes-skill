#!/usr/bin/env python3
"""fetch_x_bookmarks.py — production fetcher for the user's X (Twitter) bookmarks.

Architecture (no paid X API):
  1. Copy the live Brave 'Default/Cookies' SQLite file into a fresh temp profile
     (READ-ONLY on the source; non-destructive). This carries the authenticated
     x.com session natively — X accepts it exactly as the real browser would.
  2. Launch headless Brave over CDP (port 9222) against that copied profile.
  3. Navigate to https://x.com/i/history, then repeatedly scroll to the bottom
     to trigger X's infinite load, collecting every <article> bookmark.
  4. Extract per tweet: id, full text, author screen_name, created_at, URLs.
  5. Write data/x_bookmarks.json (idempotent, deduped by id, atomic write).

Cookie VALUES are never printed, logged, or persisted. The source cookie DB is
opened read-only (a copy is made; the original is never touched).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import sqlite3
import hashlib
import tempfile
import urllib.request
from pathlib import Path

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("ERROR: 'websocket-client' is required. Run: pip3 install websocket-client")

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
BRAVE_DIR = "/Users/fromthejump/Library/Application Support/BraveSoftware/Brave-Browser"
DEFAULT_PROFILE = os.path.join(BRAVE_DIR, "Default")
COOKIE_DB = os.path.join(DEFAULT_PROFILE, "Cookies")
KEYCHAIN_SERVICES = ["Brave Safe Storage", "Chrome Safe Storage"]
BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
PORT = 9222
PROFILE = "/tmp/bravex_cdp_profile"
X_HISTORY_URL = "https://x.com/i/history"
MAX_SCROLLS = 60          # upper bound on infinite-load iterations
SCROLL_WAIT = 1.8         # seconds between scrolls (rate-limit politely)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "x_bookmarks.json"

# ----------------------------------------------------------------------------
# Cookie verification (names only — values never printed) + read-only DB access
# ----------------------------------------------------------------------------
def get_keychain_pass(service):
    r = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", service],
        capture_output=True, text=True, check=True)
    return r.stdout.rstrip("\n")


def aes_cbc_decrypt(ct, key, iv):
    """AES-128-CBC no-padding decrypt of ct (bytes) via openssl."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(ct)
        tmp = f.name
    try:
        r = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-nopad",
             "-K", key.hex(), "-iv", iv.hex(), "-in", tmp],
            capture_output=True)
        return r.stdout if r.returncode == 0 else None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def decrypt_value(encrypted_value, key):
    if not encrypted_value or encrypted_value[:3] not in (b"v10", b"v11"):
        return None
    raw = aes_cbc_decrypt(encrypted_value[3:], key, b" " * 16)
    if not raw:
        return None
    pad = raw[-1]
    if 1 <= pad <= 16 and pad <= len(raw):
        raw = raw[:-pad]
    return raw.decode("utf-8", "replace")


def resolve_key():
    """Return (service_name, pbkdf2_key) or raise. Tries Brave then Chrome."""
    last_err = None
    for service in KEYCHAIN_SERVICES:
        try:
            pw = get_keychain_pass(service).encode()
            key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, 16)
            print(f"[fetch_x_bookmarks] Keychain service: '{service}'")
            return service, key
        except subprocess.CalledProcessError as e:
            last_err = e
            continue
    raise RuntimeError(f"No usable Keychain service: {last_err}")


def read_x_cookies():
    """Decrypt all x.com/twitter.com cookies. Returns {name: value} in-memory only.

    Used by verify_x_bookmarks.py to prove the session is decryptable. Values
    are never printed or persisted.
    """
    _svc, key = resolve_key()
    if not os.path.exists(COOKIE_DB):
        raise RuntimeError(f"Cookie DB not found: {COOKIE_DB}")
    con = sqlite3.connect(f"file:{COOKIE_DB}?mode=ro", uri=True)
    cur = con.cursor()
    cookies = {}
    try:
        cur.execute(
            "SELECT host_key, name, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%x.com%' OR host_key LIKE '%twitter.com%'")
        for host, name, enc in cur.fetchall():
            if name in cookies:
                continue
            val = decrypt_value(enc, key)
            if val is not None:
                cookies[name] = val
    finally:
        con.close()
    for required in ("auth_token", "ct0", "_twitter_sess"):
        if required not in cookies:
            raise RuntimeError(
                f"Required cookie '{required}' missing — is the session logged in?")
    return cookies


# ----------------------------------------------------------------------------
# Headless Brave + CDP
# ----------------------------------------------------------------------------
def prepare_profile():
    """Build a fresh profile at PROFILE carrying the live session's Cookies.

    Copies only the Cookies SQLite file (non-destructive read of the source).
    """
    subprocess.run(["pkill", "-9", "-f", "bravex_cdp_profile"], capture_output=True)
    time.sleep(1)
    subprocess.run(["rm", "-rf", PROFILE])
    default_dir = os.path.join(PROFILE, "Default")
    os.makedirs(default_dir, exist_ok=True)
    if not os.path.exists(COOKIE_DB):
        raise RuntimeError(f"Source cookie DB not found: {COOKIE_DB}")
    shutil.copy2(COOKIE_DB, os.path.join(default_dir, "Cookies"))
    return PROFILE


def launch_brave():
    """Launch headless Brave on the prepared profile at PORT; return (proc, version)."""
    proc = subprocess.Popen(
        [BRAVE, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}",
         "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "--window-size=1280,2400", "--remote-allow-origins=*",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for CDP — try IPv6 then IPv4 (Brave may bind only one).
    for _ in range(60):
        for base in ("http://[::1]:%d" % PORT, "http://127.0.0.1:%d" % PORT):
            try:
                with urllib.request.urlopen(base + "/json/version", timeout=2) as r:
                    return proc, json.loads(r.read())
            except Exception:
                continue
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("CDP endpoint never came up on port %d" % PORT)


class CDP:
    """Minimal CDP client over a single websocket connection."""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=40)
        self.ws.settimeout(40)
        self.id = 0

    def send(self, method, params=None):
        self.id += 1
        mid = self.id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg
            if msg.get("method") in (
                "Network.requestWillBeSent", "Network.responseReceived",
                "Network.loadingFinished", "Network.requestWillBeSentExtraInfo",
                "Network.responseReceivedExtraInfo"):
                continue

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def js(page, expression):
    """Evaluate JS in the page and return the deserialized value."""
    res = page.send("Runtime.evaluate",
                    {"expression": expression, "returnByValue": True,
                     "awaitPromise": True})
    if res.get("result", {}).get("exceptionDetails"):
        raise RuntimeError("JS error: " +
                           json.dumps(res["result"]["exceptionDetails"])[:400])
    return res.get("result", {}).get("result", {}).get("value")


def new_page(browser):
    """Create a page target and return its CDP client."""
    tgt = browser.send("Target.createTarget", {"url": "about:blank"})["result"]["targetId"]
    page_ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://[::1]:%d/json" % PORT, timeout=3) as r:
            for t in json.loads(r.read()):
                if t.get("id") == tgt:
                    page_ws = t["webSocketDebuggerUrl"]
                    break
        if page_ws:
            break
        time.sleep(0.3)
    if not page_ws:
        raise RuntimeError("Could not resolve page websocket for new target")
    page = CDP(page_ws)
    page.send("Network.enable")
    page.send("Page.enable")
    return page


# ----------------------------------------------------------------------------
# Extraction
# ----------------------------------------------------------------------------
EXTRACT_JS = r"""
(() => {
  const out = [];
  document.querySelectorAll('article').forEach((art) => {
    const link = art.querySelector('a[href*="/status/"]');
    const idMatch = link && link.href.match(/\/status\/(\d+)/);
    if (!idMatch) return;
    const id = idMatch[1];
    let author = null;
    const authorLink = art.querySelector('a[href^="/"]');
    if (authorLink) {
      const m = authorLink.getAttribute('href').match(/^\/([^\/]+)$/);
      if (m) author = m[1];
    }
    const textEl = art.querySelector('[data-testid="tweetText"]');
    const text = textEl ? textEl.innerText : '';
    const timeEl = art.querySelector('time');
    const created_at = timeEl ? (timeEl.getAttribute('datetime') || null) : null;
    const urls = Array.from(art.querySelectorAll('a[href]'))
      .map(a => a.href)
      .filter(h => h.startsWith('http') && !h.includes('x.com') && !h.includes('twitter.com'));
    out.push({id, author, text, created_at, urls: [...new Set(urls)]});
  });
  return out;
})()
"""


def extract_articles(page):
    return js(page, EXTRACT_JS)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. Sanity-check session decryptable (names only) before launching.
    cookies = read_x_cookies()
    print(f"[fetch_x_bookmarks] Session verified: {len(cookies)} x.com cookies "
          f"decryptable (auth_token, ct0, _twitter_sess present)")

    # 2. Prepare profile (copy live Cookies) + launch headless Brave.
    prepare_profile()
    proc, version = launch_brave()
    try:
        browser = CDP(version["webSocketDebuggerUrl"])
        page = new_page(browser)

        # 3. Navigate to bookmarks.
        page.send("Page.navigate", {"url": X_HISTORY_URL})
        time.sleep(12)
        title = js(page, "document.title")
        href = js(page, "location.href")
        print(f"[fetch_x_bookmarks] Loaded: '{title}' @ {href}")
        if "onboarding" in (href or "") or "login" in (href or ""):
            raise RuntimeError("Redirected to login — copied session not accepted")

        # 4. Infinite scroll to load all bookmarks.
        prev = -1
        stable = 0
        for i in range(MAX_SCROLLS):
            js(page, "window.scrollTo(0, document.body.scrollHeight); true")
            time.sleep(SCROLL_WAIT)
            n = len(extract_articles(page))
            print(f"[fetch_x_bookmarks] scroll {i+1}: {n} bookmarks on page")
            if n == prev:
                stable += 1
                if stable >= 3:      # 3 consecutive no-gain scrolls -> exhausted
                    break
            else:
                stable = 0
            prev = n

        # 5. Final collect + dedupe by id.
        bookmarks = extract_articles(page)
        seen = {}
        for b in bookmarks:
            seen[b["id"]] = b
        result = sorted(seen.values(), key=lambda x: int(x["id"]), reverse=True)

        # 6. Atomic write (resumable/idempotent).
        tmp = OUTPUT_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        os.replace(tmp, OUTPUT_FILE)
        print(f"[fetch_x_bookmarks] Wrote {len(result)} unique bookmarks -> {OUTPUT_FILE}")
        browser.close()
        page.close()
    finally:
        proc.terminate()
        time.sleep(1)
        subprocess.run(["pkill", "-9", "-f", "bravex_cdp_profile"], capture_output=True)


if __name__ == "__main__":
    main()
