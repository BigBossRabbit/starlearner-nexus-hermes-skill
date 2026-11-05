"""_engine.py — the lazy, namespace-safe engine adapter (B.2.1 seam).

The one rule that shapes this module (B.2.1 principle 1): **the engine
keeps its standalone shape** (one tree, two install shapes). The
standalone runs the engine as ``python3 scripts/<x>.py``
(``fetch_starred_repos.sh`` → ``data/starred_repos.json``; the argv-pure
categorize/assess/ledger/generate stages); the plugin therefore imports
the engine under its own package namespace
(``hermes_plugins.starlearner_nexus.scripts.*``), which gives:

  * zero top-level ``sys.modules`` pollution for the shared engine — two
    plugins in one hermes never fight over ``generate_skills``
    (ReapX's and StarLearner's differ in 8 lines);
  * the loader's own ``_evict_modules("hermes_plugins.<name>.*")`` evicts
    the engine on plugin reload/doctor-exit (fresh code after an update);
  * NO fetch chain here at all (B.2.2): the standalone fetcher is a shell
    script (gh/PAT curl — R11-clean by removal), and the plugin's fetch
    is ``github_fetch.py`` (in-process, secret_scope) — so this adapter
    has no ``load_fetch``, no browser/CDP imports, no websocket
    dependency anywhere in the plugin.

R09 discipline — the path-restore: the engine scripts carry their own
standalone-era ``sys.path.insert(0, <repo root>)`` idiom
(categorize/generate: "add the skill directory to path for imports" — a
no-op for the imports they actually do). Under the plugin it would leave
THE PLUGIN ROOT at ``sys.path[0]``, and every plugin root carries a
top-level ``tools.py``/``scripts`` package — shadowing hermes core's own
top-level ``tools``/``scripts`` packages for every later LAZY core import
(core imports ``tools.*`` lazily all over: approval contexts, mcp
costs, …). Everything the engine needs from the path it imports at import
time, so the path is restored to exactly what it was after every load.

Nothing hermes is imported here. ``load()`` is idempotent; every engine
failure is converted into a clean RuntimeError (R12).
"""
from __future__ import annotations

import sys

# The shared engine, imported under the plugin's own namespace.
# (Populated by load(); module attributes are set there so that a failed
# engine import surfaces as a clean RuntimeError, not an import error at
# plugin-register time — nothing here runs before the first tool call.)
ledger = None
categorize_repos = None
assess_repos = None
generate_skills = None

_LOADED = False


def load() -> None:
    """Import the shared engine (ledger / categorize / assess / generate —
    none of it needs a browser, a network or anything beyond jinja2).
    Idempotent; raises RuntimeError (never a bare ImportError) when the
    engine cannot load. See the module docstring for the path-restore."""
    global _LOADED, ledger, categorize_repos, assess_repos, generate_skills
    if _LOADED:
        return
    saved_path = list(sys.path)
    try:
        # Package-relative: hermes_plugins.starlearner_nexus.scripts.<name>
        # — the plugin's own copy of the engine, evictable by the plugin
        # loader, invisible to any other plugin's same-named engine
        # modules (ReapX's generate_skills differs in 8 lines).
        from . import scripts  # noqa: F401
        from .scripts import (ledger, categorize_repos, assess_repos,  # type: ignore # noqa: F401
                              generate_skills)  # type: ignore # noqa: F401
    except ImportError as exc:
        raise RuntimeError(f"engine import failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"engine load failed: {type(exc).__name__}: "
                           f"{exc}") from exc
    finally:
        # the engine scripts' own sys.path.insert(0, <repo root>) idiom
        # restored away — never shadow hermes core's top-level packages
        # (the R09 no-shadow law; see the module docstring).
        sys.path[:] = saved_path
    _LOADED = True
