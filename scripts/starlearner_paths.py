#!/usr/bin/env python3
"""starlearner_paths.py — the data-dir seam (the one-tree, two-install-shapes
contract; B.2.1 principle 2 / B.2.2).

Everything the plugin-mode engine stages write (starred_repos.json,
new_repos.json, categorized_repos.json, opportunities.json, ledger.json)
lives under :func:`resolve_data_dir`, resolved in this order:

  1. an explicit argument (what the plugin layer passes — the host-owned
     ``plugin_data_dir("starlearner-nexus")``: outside the install tree,
     survives ``hermes plugins update``/``remove``, follows the active
     profile);
  2. the ``STARLEARNER_DATA_DIR`` environment variable (a standalone
     debugging affordance; never required);
  3. the standalone default ``<repo>/data`` — the pre-plugin behaviour,
     bit-for-bit unchanged.

The standalone scripts are argv-pure (categorize_repos / assess_repos take
<input> <output> paths; ledger.py takes paths; generate_skills takes
<input> <output>) — the fetcher writes ``data/starred_repos.json`` relative
to the script. This module is the data-root convention the plugin layer and
the tests share; it is the ONLY place a plugin-mode data root is resolved.
It must never import another engine script.
"""
from __future__ import annotations

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# The standalone default (repo-relative, exactly as before the seam).
DEFAULT_DATA_DIR = SCRIPT_DIR.parent / "data"

# The data-dir flag (mirrors the reapx seam's --data-dir convention).
DATA_DIR_FLAG = "--data-dir"


def resolve_data_dir(data_dir=None) -> Path:
    """Resolve the engine's data root: explicit arg >
    ``STARLEARNER_DATA_DIR`` env > ``<repo>/data`` (the standalone
    default)."""
    if data_dir:
        return Path(data_dir).expanduser()
    env = os.environ.get("STARLEARNER_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return DEFAULT_DATA_DIR


def data_file(name, data_dir=None) -> Path:
    """``resolve_data_dir(data_dir) / name`` — the one way the plugin layer
    names a data file (callers must not build their own data paths)."""
    return resolve_data_dir(data_dir) / name


if __name__ == "__main__":  # tiny self-test (no engine imports)
    import sys

    here = resolve_data_dir()
    ok = here == DEFAULT_DATA_DIR
    print(f"default data dir : {here} {'OK' if ok else 'MISMATCH'}")
    os.environ["STARLEARNER_DATA_DIR"] = "/tmp/starlearner-env-probe"
    ok = str(resolve_data_dir()) == "/tmp/starlearner-env-probe"
    print(f"env override    : {resolve_data_dir()} {'OK' if ok else 'MISMATCH'}")
    ok = str(resolve_data_dir("/tmp/starlearner-explicit")) == \
        "/tmp/starlearner-explicit"
    print(f"explicit arg    : {resolve_data_dir('/tmp/starlearner-explicit')} "
          f"{'OK' if ok else 'MISMATCH'}")
    del os.environ["STARLEARNER_DATA_DIR"]
    sys.exit(0 if ok else 1)
