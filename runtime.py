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


def setting(key: str, default=None):
    """Read one setting from the plugin config ONLY —
    ``plugins.entries.starlearner-nexus.settings.<key>``.

    Tool args never reach here (the review point): a prompt-injected call can
    pass any JSON it likes without being able to flip the user's enrichment
    engine, lift the LLM spend cap, or force skill registration. Per-call args
    are handled separately: ``setting_int`` / ``capped_arg`` below.

    Never touches ctx.llm / ctx.state; returns the default whenever the
    context is missing (tests) or the key is unset.
    """
    ctx = get_ctx()
    if ctx is None:
        return default
    try:
        value = ctx.get_config(key, default)
    except Exception:  # pragma: no cover — a settings read must never crash
        return default
    return default if value is None else value


def setting_int(key: str, default: int) -> int:
    """An integer setting, coerced; a non-numeric/absent value is the default.

    0 is a MEANINGFUL value for the two cap settings (``llm_max_items=0``
    disables enrichment, ``generate_limit=0`` is assess-only), so it is kept —
    never collapsed into the default.
    """
    value = setting(key, default)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def capped_arg(args: dict | None, key: str, ceiling: int) -> int:
    """A per-call cap that can only TIGHTEN the configured ceiling.

    ``min(declared arg, setting)`` — the arg is per-call data, the setting is
    the user's spend guard. A missing/garbage arg is the ceiling; 0 is kept
    (assess-only / zero LLM items); the result is never negative.
    """
    if not args or args.get(key) is None:
        return ceiling
    try:
        value = int(args[key])
    except (TypeError, ValueError):
        return ceiling
    return max(0, min(value, ceiling))


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
