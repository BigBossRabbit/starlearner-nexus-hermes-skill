"""runtime.py — the plugin's shared runtime state. hermes-free.

Holds the PluginContext captured at register() time (the A.7.4-probe
mechanism: tool handlers call ctx.register_skill at handler time through the
captured context), the plugin identity constants, and the on_unload hook list.

Import rules (the whole plugin layer obeys them):
  * no hermes imports at module level (lazy, inside functions) — register()
    must run against the validate probe's bare recording stub too;
  * no engine imports at module level (the engine is imported through
    ``_engine`` lazily, at first tool call);
  * register() itself never touches ctx.llm / ctx.state / ctx.manifest (the
    recording stub raises AttributeError for that surface).
"""
from __future__ import annotations

import logging
import threading

# The manifest name (plugin id, settings key, skill namespace, plugin-data dir).
PLUGIN_NAME = "starlearner-nexus"

# The auxiliary LLM task key. MUST be alphanumeric + underscores — a hyphen
# would raise ValueError in register_auxiliary_task and fail the whole load.
AUX_TASK = "starlearner_enricher"

# The plugin-mode skill template (references/skill_templates/).
PLUGIN_TEMPLATE = "plugin_skill.md.j2"

# The bundled always-registered index skill (A.7.5).
INDEX_SKILL = "starlearner-index"

log = logging.getLogger("hermes_plugins.starlearner_nexus")

# ── the captured PluginContext (A.7.4) ───────────────────────────────────────
_CTX = None
_CTX_LOCK = threading.Lock()


def set_ctx(ctx) -> None:
    """Capture the PluginContext at register() time (handler-time
    register_skill runs through it)."""
    global _CTX
    with _CTX_LOCK:
        _CTX = ctx


def get_ctx():
    """The captured context, or None (a handler running without one reports a
    clean error instead of crashing)."""
    with _CTX_LOCK:
        return _CTX


def setting(key: str, default=None, args: dict | None = None):
    """Read one plugin setting: tool args > plugins.entries.starlearner-nexus.settings >
    *default* (the config_schema default — the caller passes it; never None so
    the probe stub's get_config and an unconfigured plugin behave the same).

    Never touches ctx.llm / ctx.state; returns the default whenever the
    context is missing (tests) or the key is unset.
    """
    if args is not None and args.get(key) is not None:
        return args.get(key)
    ctx = get_ctx()
    if ctx is None:
        return default
    try:
        value = ctx.get_config(key, default)
    except Exception:  # pragma: no cover — a settings read must never crash
        return default
    return default if value is None else value


# ── on_unload hooks (engine-module eviction etc.) ────────────────────────────
_ON_UNLOAD: list = []
_ON_UNLOAD_LOCK = threading.Lock()


def on_unload(callback) -> None:
    """Register a cleanup callback (runs at plugin unload; exceptions logged,
    never propagated)."""
    with _ON_UNLOAD_LOCK:
        _ON_UNLOAD.append(callback)


def run_unload() -> None:
    """Run every on_unload callback (reverse order), never raising."""
    with _ON_UNLOAD_LOCK:
        callbacks = list(reversed(_ON_UNLOAD))
        _ON_UNLOAD.clear()
    for callback in callbacks:
        try:
            callback()
        except Exception:  # pragma: no cover — cleanup must never raise
            log.warning("starlearner-nexus on_unload callback %r failed", callback, exc_info=True)
