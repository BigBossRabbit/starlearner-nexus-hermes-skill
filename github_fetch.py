"""github_fetch.py — the in-process GitHub fetcher (spec B.6.2/B.6.3).

THE WHOLE CREDENTIAL SURFACE OF THE PLUGIN (B.6.2, verbatim design):

  * the token is a ``requires_env`` secret (``STARLEARNER_GITHUB_TOKEN``)
    — prompted (hidden) at ``hermes plugins install``, saved by the HOST
    to the active profile's ``.env``, read back per call through
    ``agent.secret_scope.get_secret`` (the R11 multiplexing-safe read —
    honours the ACTIVE profile; never a bare ``os.environ`` read, never a
    ``.env`` file, never another tool's login);
  * it is never in the plugin tree, its logs, its errors (the 401/403
    messages carry the class + the fix, never the value), its tool
    results, or its stored data;
  * narrowest scope we can name (read-only, public repos — a classic
    ``public_repo`` token or a fine-grained read-only public-repos token);
  * it leaves the machine only to ``api.github.com``, over one
    ``requests`` HTTPS call shape, one endpoint
    (``GET /user/starred``), paginated (``per_page=100`` +
    ``Link: rel="next"``), bounded (``timeout=30`` per page, the
    ``max_pages`` hard cap) — R12: a clean error, never a hang;
  * no shell, no ``gh``, no ``curl``, no ``jq``, no subprocess (B.1.3:
    the standalone's gh-CLI path is dropped in the plugin — shelling out
    to ``gh`` would ride another tool's stored login).

The gh-CLI path and the curl loop (``fetch_starred_repos.sh``) stay
standalone-only (B.2.1 principle 6 / B.10 gap B-1). ``requests`` is a
declared ``python_dependency`` (R10) — imported lazily inside
``fetch_starred`` so the module itself imports hermes-free + dep-free at
plugin-register time; ``_secret()`` (the secret_scope indirection) is the
one thing the tests monkeypatch.
"""
from __future__ import annotations

from . import runtime

# The declared requires_env name (plugin.yaml). Namespaced so it can't
# collide with a shared GITHUB_TOKEN (B.6.3).
TOKEN_ENV = "STARLEARNER_GITHUB_TOKEN"

API_URL = "https://api.github.com/user/starred"
API_VERSION = "2022-11-28"
PER_PAGE = 100
TIMEOUT = 30


class AuthError(RuntimeError):
    """A mapped fetch failure (kind + fix, R12 — never the token)."""

    def __init__(self, kind: str, detail: str = "", extra: dict | None = None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail
        self.extra = extra or {}


def _secret(name: str):
    """The secret_scope indirection (R11): ``agent.secret_scope.get_secret``
    — public, honours the active profile. Imported lazily (a hermes
    without it / the test stubs / a plugin-register-time import never
    touch it). Returns None when the secret is unset/unavailable."""
    try:
        from agent.secret_scope import get_secret
        return get_secret(name)
    except Exception:
        return None


def _token() -> str | None:
    try:
        tok = (_secret(TOKEN_ENV) or "").strip()
    except Exception:
        return None
    return tok or None               # None ⇒ clean 401-style error JSON


def has_token() -> bool:
    try:
        return bool((_secret(TOKEN_ENV) or "").strip())
    except Exception:
        return False


# the last call's max_pages verdict (a WARNING flag in the sync result,
# never a failure — B.3.1); set by fetch_starred, read by the driver.
last_max_pages_exhausted = False


def fetch_starred(max_pages=30, timeout=TIMEOUT) -> list:
    """``GET /user/starred`` (the repos the authenticated user starred),
    paginated, bounded. Raises AuthError (kind + fix, never the token).

    R12-clean: 401 (bad/expired token) / 403 (rate limit) / 5xx / the
    timeout / the max_pages cap are all clean errors; nothing waits for
    a person (a missing token = the one-command fix error, the
    install-prompt path).
    """
    tok = _token()
    if not tok:
        raise AuthError(
            "token_not_set",
            "STARLEARNER_GITHUB_TOKEN is not set. `hermes plugins "
            "install` prompts for it (hidden input), or set it in the "
            "active profile's .env.",
            {"fix": "hermes plugins install (the token prompt), or the "
                    "profile's .env; a read-only public-repos token is "
                    "all it needs"})
    import requests  # declared python_dependency (lazy: register-time free)

    headers = {"Authorization": f"Bearer {tok}",   # built per call, in memory
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": API_VERSION}
    repos, page = [], 1
    while page <= max_pages:
        try:
            r = requests.get(API_URL, params={"per_page": PER_PAGE,
                                              "page": page},
                             headers=headers, timeout=timeout)  # R12: bounded
        except requests.exceptions.Timeout as exc:
            raise AuthError("fetch_timeout",
                            f"api.github.com did not answer in {timeout}s "
                            f"(page {page}).") from exc
        except requests.exceptions.RequestException as exc:
            raise AuthError("fetch_error",
                            f"{type(exc).__name__} calling api.github.com "
                            f"(page {page}).") from exc
        if r.status_code == 401:
            raise AuthError(
                "github_401",
                "GitHub rejected the token (expired/revoked, or not the "
                "read-only public-repos scope).",
                {"fix": "create a fresh token (classic public_repo, or a "
                        "fine-grained read-only public-repos token) and "
                        "set it as STARLEARNER_GITHUB_TOKEN"})
        if r.status_code == 403:
            if "rate limit" in (r.text or "").lower():
                reset = (r.headers or {}).get("X-RateLimit--Reset") or \
                        (r.headers or {}).get("X-RateLimit-Reset")
                raise AuthError(
                    "github_403_rate",
                    "GitHub rate limit hit (the shared check window).",
                    {"fix": "retry after the rate-limit window resets"
                            + (f" (X-RateLimit-Reset={reset})" if reset
                               else "")})
            raise AuthError("github_403",
                            "GitHub refused the call (403).")
        if r.status_code >= 500:
            raise AuthError("github_5xx",
                            f"GitHub server error ({r.status_code}, page "
                            f"{page}).")
        if r.status_code != 200:
            raise AuthError("fetch_error",
                            f"GitHub returned {r.status_code} (page "
                            f"{page}).")
        try:
            body = r.json()
        except Exception as exc:
            raise AuthError("fetch_error",
                            "GitHub's answer was not JSON "
                            "(page %d)." % page) from exc
        if not isinstance(body, list):
            raise AuthError("fetch_error",
                            "GitHub's answer was not a stars array "
                            "(page %d)." % page)
        if not body:
            break
        repos.extend(body)
        if "next" not in (r.links or {}):
            break                             # Link: rel="next" (github_api.md)
        page += 1
    global last_max_pages_exhausted
    last_max_pages_exhausted = page > max_pages
    if last_max_pages_exhausted:
        # a warning flag, never a failure (the sync result carries it):
        runtime.log.warning("starlearner-nexus: star fetch hit "
                            "max_pages=%d (the sync result flags "
                            "max_pages_exhausted)", max_pages)
    return repos
