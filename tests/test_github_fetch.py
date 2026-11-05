#!/usr/bin/env python3
"""test_github_fetch.py — the auth surface (spec B.6.2/B.6.3), the one
credential path in the plugin.

THE R11 LAW, tested:

  * the token comes ONLY from ``agent.secret_scope.get_secret`` (the
    ``_secret`` indirection — the module code never touches
    ``os.environ``, never a file);
  * no gh, no curl, no jq, no subprocess (in-process ``requests`` only);
  * one endpoint (``api.github.com/user/starred``), one call shape,
    paginated (``per_page=100`` + ``Link: rel="next"``), bounded
    (``timeout=30``, the ``max_pages`` hard cap);
  * EVERY failure = a clean ``AuthError`` with a kind + a fix —
    **and NEVER the token**: the 401/403 messages carry the class + the
    fix (B.6.2: "401 messages carry the class + the fix, not the
    value");
  * R12: token_not_set / github_401 / github_403_rate / github_5xx /
    fetch_timeout / non-JSON / non-list — all clean errors, nothing
    hangs, nothing prompts;
  * ``requests`` is imported LAZILY (inside ``fetch_starred`` — the
    token check runs first: a missing token never even imports the
    network stack).

The transport is faked by injecting a ``FakeRequests`` module into
``sys.modules["requests"]`` (fetch_starred's in-function
``import requests`` resolves it); ``github_fetch._secret`` is the one
monkeypatch point (the secret_scope indirection).
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PLUGIN_PKG = "starlearner_under_test"


def _load_plugin(pkg=PLUGIN_PKG):
    if pkg in sys.modules:
        return sys.modules[pkg]
    spec = importlib.util.spec_from_file_location(
        pkg, REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)])
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(REPO_ROOT)]
    sys.modules[pkg] = module
    spec.loader.exec_module(module)
    return module


# a fixture repo (the starred shape)
def _repo(i=1, name="sample-gpt", stars=42):
    return {"id": 9000000000 + i, "name": name,
            "full_name": "sample-org/%s" % name,
            "description": "a test repo", "topics": ["t"],
            "html_url": "https://github.com/sample-org/%s" % name,
            "stargazers_count": stars, "owner": {"login": "sample-org"}}


class FakeResponse:
    def __init__(self, status=200, body=None, links=None, headers=None,
                 text=None):
        self.status_code = status
        self._body = body
        self.links = links or {}
        self.headers = headers or {}
        self.text = text if text is not None else (
            "" if body is None else "body")

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeRequests:
    """A module stand-in: real requests.exceptions, scripted .get()."""

    def __init__(self, responses=None):
        import requests as real_requests
        self.exceptions = real_requests.exceptions
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params,
                           "headers": dict(headers or {}),
                           "timeout": timeout})
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return FakeResponse(status=200, body=[])


# a short fixture token (kept under the secret-scan pattern's
# 24-char threshold — it is test data, never a real credential):
TOKEN = "gh-a-test-token"


@unittest.skipUnless(
    __import__("importlib.util", fromlist=["util"]).find_spec("requests"),
    "the FakeRequests stand-in carries the real requests.exceptions")
class GithubFetchTests(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        # the REAL requests, pre-imported: (a) its exceptions class for
        # the stand-in, (b) the teardown reference (a fake left in
        # sys.modules would half-import the real one on the next test —
        # stale submodules, no .exceptions — the classic teardown trap).
        if "requests" not in sys.modules:
            __import__("requests")
        self.plugin = _load_plugin()
        from starlearner_under_test import github_fetch as gf
        self.gf = gf
        self._real_secret = gf._secret
        self._real_requests = sys.modules.get("requests")
        self._real_token_env = gf.TOKEN_ENV

    def tearDown(self):
        self.gf._secret = self._real_secret
        if self._real_requests is not None:
            sys.modules["requests"] = self._real_requests
        else:
            sys.modules.pop("requests", None)
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def _secret_token(self):
        self.gf._secret = lambda name: TOKEN if name == self.gf.TOKEN_ENV \
            else None

    def _secret_none(self):
        self.gf._secret = lambda name: None

    def _transport(self, responses=None):
        fake = FakeRequests(responses=responses)
        sys.modules["requests"] = fake
        return fake

    # ── the happy path ──────────────────────────────────────────────────
    def test_one_page_fetch(self):
        self._secret_token()
        fake = self._transport([
            FakeResponse(body=[_repo(1), _repo(2)])])
        repos = self.gf.fetch_starred(max_pages=5)
        self.assertEqual(repos, [_repo(1), _repo(2)])
        self.assertEqual(len(fake.calls), 1)
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://api.github.com/user/starred")
        self.assertEqual(call["params"], {"per_page": 100, "page": 1})
        self.assertEqual(call["timeout"], 30)
        # the headers: the auth (in memory, per call) + the API version:
        self.assertEqual(call["headers"]["Authorization"],
                         "Bearer " + TOKEN)
        self.assertEqual(call["headers"]["X-GitHub-Api-Version"],
                         "2022-11-28")
        self.assertFalse(self.gf.last_max_pages_exhausted)

    def test_pagination_follows_link_next(self):
        self._secret_token()
        page1 = FakeResponse(
            body=[_repo(i, "repo-%d" % i) for i in range(100)],
            links={"next": {"url": "https://api.github.com/user/"
                                   "starred?page=2"}})
        page2 = FakeResponse(body=[_repo(1, "last")])
        fake = self._transport([page1, page2])
        repos = self.gf.fetch_starred(max_pages=5)
        self.assertEqual(len(repos), 101)
        self.assertEqual(fake.calls[-1]["params"]["page"], 2)
        self.assertFalse(self.gf.last_max_pages_exhausted)

    def test_empty_page_stops(self):
        self._secret_token()
        self._transport([FakeResponse(body=[])])
        repos = self.gf.fetch_starred(max_pages=5)
        self.assertEqual(repos, [])

    def test_max_pages_cap_is_a_warning_flag_never_a_failure(self):
        self._secret_token()
        page1 = FakeResponse(
            body=[_repo(i, "r%d" % i) for i in range(100)],
            links={"next": {"url": "...?page=2"}})
        fake = self._transport([page1])  # would need page 2
        repos = self.gf.fetch_starred(max_pages=1)
        self.assertEqual(len(repos), 100)
        self.assertTrue(self.gf.last_max_pages_exhausted)  # the flag

    # ── the error model (B.3.1) — clean kinds, never the token ─────────
    def test_token_not_set_is_the_clean_install_prompt_error(self):
        self._secret_none()
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "token_not_set")
        self.assertIn("hermes plugins install", str(cm.exception))
        self.assertIn("fix", cm.exception.extra)

    def test_401_is_clean_and_never_the_token(self):
        self._secret_token()
        self._transport([FakeResponse(
            status=401, text="Bad credentials")])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "github_401")
        # THE B.6.2 LAW: the 401 error never carries the token:
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception.extra))
        self.assertIn("read-only", str(cm.exception))

    def test_403_rate_limit_carries_the_reset_hint(self):
        self._secret_token()
        self._transport([FakeResponse(
            status=403, text="API rate limit exceeded",
            headers={"X-RateLimit-Reset": "1750000000"})])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "github_403_rate")
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("X-RateLimit-Reset=1750000000",
                      str(cm.exception.extra))

    def test_403_other_is_clean(self):
        self._secret_token()
        self._transport([FakeResponse(status=403, text="forbidden")])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "github_403")

    def test_5xx_is_clean(self):
        self._secret_token()
        self._transport([FakeResponse(status=502, text="bad gateway")])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "github_5xx")

    def test_timeout_is_clean_and_bounded(self):
        self._secret_token()
        import requests as real_requests
        self._transport([real_requests.exceptions.Timeout("timed out")])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "fetch_timeout")
        self.assertIn("30s", str(cm.exception))

    def test_connection_error_is_clean(self):
        self._secret_token()
        import requests as real_requests
        self._transport([
            real_requests.exceptions.RequestException("boom")])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "fetch_error")

    def test_non_json_answer_is_clean(self):
        self._secret_token()
        self._transport([FakeResponse(status=200, body=ValueError())])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "fetch_error")

    def test_non_list_answer_is_clean(self):
        self._secret_token()
        self._transport([FakeResponse(status=200, body={"a": 1})])
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "fetch_error")

    def test_has_token(self):
        self._secret_none()
        self.assertFalse(self.gf.has_token())
        self._secret_token()
        self.assertTrue(self.gf.has_token())

    # ── the R11 law, static (the code, never the docstrings) ───────────
    def test_the_r11_law_static(self):
        src = (REPO_ROOT / "github_fetch.py").read_text(encoding="utf-8")
        code = src.split('"""', 2)[2] if src.count('"""') >= 2 else src
        # the token ONLY via the secret_scope indirection:
        self.assertNotIn("os.environ", code)
        self.assertIn("from agent.secret_scope import get_secret", src)
        # no shell, no gh, no curl:
        self.assertNotIn("subprocess", code)
        self.assertNotIn("gh ", code)
        self.assertNotIn("curl", code)
        # one endpoint:
        self.assertEqual(code.count("https://api.github.com/"), 1)
        # requests imported lazily (inside the function, AFTER the token
        # check):
        self.assertGreater(code.index("import requests"),
                           code.index('if not tok:'))

    def test_a_broken_secret_scope_is_the_no_token_path(self):
        """a hermes without agent.secret_scope / any import failure =
        token_not_set (never a crash — R12)."""
        def broken(name):
            raise RuntimeError("secret scope exploded")
        self.gf._secret = broken
        self.assertFalse(self.gf.has_token())
        with self.assertRaises(self.gf.AuthError) as cm:
            self.gf.fetch_starred()
        self.assertEqual(cm.exception.kind, "token_not_set")


if __name__ == "__main__":
    unittest.main(verbosity=2)
