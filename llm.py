"""llm.py — the ctx.llm enrichment layer (spec A.4).

A NEW layer bolted onto the deterministic rules engine (which has zero LLM
calls today): the map / categorize / assess stages optionally run through the
host-owned ``ctx.llm`` — the user's active provider and model, host-owned
credentials, zero keys in the plugin. The rules engine stays as the
always-available, bit-for-bit fallback (``enrich: rules`` or any LLM failure
or the ``llm_max_items`` cap ⇒ the current engine output, unchanged).

Trust-gate-safe by construction: ZERO override arguments are ever passed
(no ``provider=``/``model=``/``agent_id=``/``profile=`` — PluginLlmTrustError
is structurally impossible), and ``task=`` is only ever this plugin's own
registered auxiliary task (``starlearner_enricher``). Request-shaping args only
(``temperature``/``max_tokens``/``timeout``/``json_schema``/``purpose``).

Every failure mode maps to ONE behavior — the rules fallback, never a
failure, never a hang (A.4.3): provider errors / 5xx / timeout → caught per
batch (error CLASS only recorded); non-JSON or schema-invalid output →
``content_type == "text"`` / ``parsed is None``; ``ValueError`` from
``complete_structured`` (empty input / schema-validation failure) → caught,
batch dropped. No retries, no loops, one bounded call per batch. The
generate stage is NEVER LLM-enriched (Jinja2 renders LLM-produced VARIABLES;
the LLM never writes the SKILL.md structure).

Nothing in this module imports hermes or the engine; ``ctx`` is the captured
PluginContext (runtime.get_ctx()), and ``ctx.llm`` is reached lazily +
defensively (a missing/None llm surface = the no-LLM path = rules).
"""
from __future__ import annotations

import json
import re
import time

from . import runtime
from .skills_out import item_source_key

# The own registered auxiliary task (underscore key; hyphens are invalid).
TASK = runtime.AUX_TASK

# Batches (A.4.2): map ≤ 10 items, categorize/assess ≤ 20.
MAP_BATCH = 10
CAT_BATCH = 20
ASSESS_BATCH = 20

# One bounded complete_structured per batch (doc constraints).
TEMPERATURE = 0.0
MAX_TOKENS = 2000
TIMEOUT = 30

# A valid LLM map name: 3-8 kebab-case words, sane length (A.4.2). Anything
# else falls back to the rules identity for that item.
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){2,11}$")

MAP_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "description", "topics"],
                "properties": {
                    "id": {"type": ["string", "integer"]},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

CAT_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "category", "confidence"],
                "properties": {
                    "id": {"type": ["string", "integer"]},
                    "category": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}

ASSESS_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "integrate", "integrate_rationale",
                             "opportunity", "opportunity_rationale"],
                "properties": {
                    "id": {"type": ["string", "integer"]},
                    "integrate": {"type": "boolean"},
                    "integrate_rationale": {"type": "string"},
                    "opportunity": {"type": ["string", "null"]},
                    "opportunity_rationale": {"type": "string"},
                },
            },
        },
    },
}


class Stats:
    """The per-run LLM enrichment stats (the llm.* fields of the harvest
    result). Error KINDS only — never error message text."""

    def __init__(self):
        self.batches = 0
        self.items = 0
        self.errors = 0
        self.error_kinds: list = []
        self.started: float | None = None

    def error(self, kind: str) -> None:
        self.errors += 1
        if kind not in self.error_kinds:
            self.error_kinds.append(kind)

    def as_dict(self) -> dict:
        out: dict = {"batches": self.batches, "items": self.items,
                     "errors": self.errors}
        if self.error_kinds:
            out["error_kinds"] = sorted(self.error_kinds)
        if self.started is not None:
            out["seconds"] = round(time.time() - self.started, 1)
        return out


class Enricher:
    """The ctx.llm wrapper. ``llm=None`` (no llm surface / no items under the
    cap) means every batch is a clean no-op fallback — the rules engine."""

    def __init__(self, ctx=None, enabled=True):
        self._llm = None
        self.enabled = enabled
        if enabled:
            ctx = ctx if ctx is not None else runtime.get_ctx()
            # Never a hard ctx.llm touch: a missing surface (test stubs, a
            # hermes without it) — or even a *raising* one (a broken lazy
            # property) — is simply the no-LLM path (rules fallback).
            try:
                self._llm = getattr(ctx, "llm", None)
            except Exception:
                self._llm = None

    @property
    def available(self) -> bool:
        return self.enabled and self._llm is not None

    def _complete(self, *, instructions, batch_items, schema, schema_name,
                  purpose, stats) -> list | None:
        """One bounded complete_structured call over a batch. Returns the
        parsed items list, or None (a recorded error kind ⇒ rules fallback for
        the whole batch)."""
        if not self.available:
            stats.error("disabled")
            return None
        try:
            result = self._llm.complete_structured(  # type: ignore[union-attr]
                instructions=instructions,
                input=[{"type": "text",
                        "text": json.dumps(batch_items, ensure_ascii=False)}],
                json_schema=schema,
                schema_name=schema_name,
                purpose=purpose,
                task=TASK,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                timeout=TIMEOUT,
            )
        except Exception as exc:  # provider errors, timeouts, ValueError …
            # Error CLASS only (A.4.3) — never message text (may carry content).
            stats.error(type(exc).__name__)
            return None
        if result is None:
            stats.error("none")
            return None
        if getattr(result, "content_type", "text") != "json" or \
                getattr(result, "parsed", None) is None:
            stats.error("not_json")
            return None
        parsed = result.parsed
        items = parsed.get("items") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            stats.error("shape")
            return None
        return items


def _batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _cap(items, llm_max_items):
    """LLM-shy runs: items beyond the cap run rules (token-spend guard).
    ``llm_max_items <= 0`` disables LLM enrichment entirely (the setting's
    documented meaning)."""
    if llm_max_items is None or llm_max_items <= 0:
        # 0 (or any negative) disables LLM enrichment entirely (the
        # setting's documented meaning).
        return []
    return items[:llm_max_items]


# ── map (A.4.2) ──────────────────────────────────────────────────────────────

MAP_INSTRUCTIONS = (
    "For each starred repository, produce the skill identity this repo "
    "should carry (a curation pass): `name` = 3-8 word kebab-case slug a "
    "human would give the skill (lowercase words joined by single "
    "hyphens; not necessarily the repo name); `description` = 1-2 plain "
    "sentences of what it does/enables (from the repo's own description "
    "and topics; no hype); `topics` = 3-8 lower-case tags. Return each "
    "item's `id` unchanged."
)


def enrich_map(items, ctx=None, llm_max_items=50, enrich="llm"):
    """The map stage's LLM pass (B.4): per item (a starred repo mapped in
    by the fetcher) a curated {name, description, topics} identity — the
    curation pass over the repo object (the rules fallback = today's
    identity: the repo name verbatim + the raw description).

    Returns ``(overrides, stats)``: *overrides* is {item_key: {name,
    description, topics}} for the items the LLM (successfully) re-identified —
    missing/invalid items simply stay with the rules identity (the fallback is
    the caller leaving the item untouched).
    """
    stats = Stats()
    overrides = {}
    capped = _cap(items, llm_max_items if enrich == "llm" else 0)
    if not capped:
        # rules mode / nothing under the cap / disabled: zero stats (the
        # "disabled" error kind is recorded only when the LLM was actually
        # requested and is unavailable — see Enricher).
        return overrides, stats
    enricher = Enricher(ctx, enabled=(enrich == "llm"))
    if not enricher.available:
        stats.error("disabled")
        return overrides, stats
    stats.started = time.time()
    for batch in _batches(capped, MAP_BATCH):
        stats.batches += 1
        stats.items += len(batch)
        payload = [{"id": it.get("_bookmark_id") or it.get("id") or idx,
                    "name": it.get("name") or "",
                    "description": (it.get("description") or "")[:600],
                    "topics": it.get("topics") or []}
                   for idx, it in enumerate(batch)]
        parsed = enricher._complete(instructions=MAP_INSTRUCTIONS,
                                    batch_items=payload,
                                    schema=MAP_SCHEMA,
                                    schema_name="starlearner.map.v1",
                                    purpose="starlearner.map", stats=stats)
        if parsed is None:
            continue
        by_id = {}
        for row in parsed:
            if isinstance(row, dict) and row.get("id") is not None:
                by_id[str(row.get("id"))] = row
        for it in batch:
            payload_id = it.get("_bookmark_id") or it.get("id")
            row = by_id.get(str(payload_id))
            if not row:
                stats.error("missing_item")
                continue
            key = item_source_key(it)
            name = str(row.get("name") or "").strip().lower()
            description = str(row.get("description") or "").strip()
            topics = row.get("topics")
            if not _NAME_RE.match(name) or not description or \
                    not isinstance(topics, list) or not topics or \
                    any(not isinstance(t, str) or not t.strip()
                        for t in topics) or len(name) > 80:
                stats.error("invalid_item")
                continue
            overrides[key] = {
                "name": name,
                "description": description[:600],
                "topics": [t.strip().lower()[:40] for t in topics[:8]],
            }
    return overrides, stats


# ── categorize (A.4.2) ───────────────────────────────────────────────────────


def _category_keys():
    """The 12 domain keys as data (taxonomy-as-data, never in the prompt)."""
    from pathlib import Path
    cat_file = Path(__file__).resolve().parent / "references" / "categories.json"
    try:
        data = json.loads(cat_file.read_text(encoding="utf-8"))
        keys = [str(k) for k in data.keys()]
    except Exception:  # pragma: no cover — the file ships with the plugin
        keys = []
    return keys


def enrich_categorize(items, ctx=None, llm_max_items=50, enrich="llm"):
    """The categorize stage's LLM pass: per item {category, confidence}.

    Returns ``(verdicts, stats)``: *verdicts* is {item_key: {"category": str,
    "confidence": float}} for the LLM-classified items. THE FUSION LIVES IN
    THE CALLER (harvest.py) and is fixed + deterministic (A.4.2): a keyword
    hit always wins; the LLM classifies (a) items the keyword engine left
    ``uncategorized`` and (b) weak keyword scores; an LLM verdict that
    disagrees with a strong keyword verdict is recorded as ``llm_override``
    for the human (starlearner_review), never applied.
    """
    stats = Stats()
    verdicts = {}
    capped = _cap(items, llm_max_items if enrich == "llm" else 0)
    if not capped:
        return verdicts, stats
    keys = _category_keys()
    instructions = (
        "Classify each item into exactly one of these category keys: "
        + ", ".join(keys) + " (or 'uncategorized' when nothing fits). "
        "`confidence` is your 0-1 confidence. Return each item's `id` "
        "unchanged. Judge from the item's name, description and topics."
    )
    enricher = Enricher(ctx, enabled=(enrich == "llm"))
    if not enricher.available:
        stats.error("disabled")
        return verdicts, stats
    stats.started = time.time()
    for batch in _batches(capped, CAT_BATCH):
        stats.batches += 1
        stats.items += len(batch)
        payload = [{"id": it.get("_bookmark_id") or it.get("id") or idx,
                    "name": it.get("name") or "",
                    "description": (it.get("description") or "")[:400],
                    "topics": it.get("topics") or []}
                   for idx, it in enumerate(batch)]
        parsed = enricher._complete(instructions=instructions,
                                    batch_items=payload,
                                    schema=CAT_SCHEMA,
                                    schema_name="starlearner.categorize.v1",
                                    purpose="starlearner.categorize", stats=stats)
        if parsed is None:
            continue
        by_id = {}
        for row in parsed:
            if isinstance(row, dict) and row.get("id") is not None:
                by_id[str(row.get("id"))] = row
        for it in batch:
            payload_id = it.get("_bookmark_id") or it.get("id")
            row = by_id.get(str(payload_id))
            if not row:
                stats.error("missing_item")
                continue
            key = item_source_key(it)
            category = str(row.get("category") or "").strip()
            confidence = row.get("confidence")
            if category not in keys or not isinstance(confidence, (int, float)) \
                    or not 0.0 <= float(confidence) <= 1.0:
                stats.error("invalid_item")
                continue
            verdicts[key] = {"category": category,
                             "confidence": round(float(confidence), 2)}
    return verdicts, stats


# ── assess (A.4.2) ───────────────────────────────────────────────────────────

ASSESS_INSTRUCTIONS = (
    "Two-track assessment per item (a bookmark the user saved, mapped to a "
    "skill candidate). Track A — integrate: is this worth turning into a "
    "loadable skill for this user's own stack? (a reusable, tool-like, "
    "practice-able thing; not a one-off news item or a plain link). "
    "Track B — opportunity: is this a business-opportunity value? (a "
    "candidate to package for a client deliverable; give the domain key "
    "when true). Track B is judgement: be conservative and give a short "
    "rationale for either track. Return each item's `id` unchanged."
)


def enrich_assess(items, ctx=None, llm_max_items=50, enrich="llm"):
    """The assess stage's LLM pass: per item the two-track verdict.

    Returns ``(verdicts, stats)``: *verdicts* is {item_key: {"integrate":
    bool, "integrate_rationale": str, "opportunity": str|None,
    "opportunity_rationale": str}}. THE FUSION LIVES IN THE CALLER (A.4.2):
    keyword hits are the floor (union); LLM-derived Track-B hits land in
    starlearner_review with rationale and are NOT written to the ledger without
    review; an LLM Track-A true adds a *candidate* only.
    """
    stats = Stats()
    verdicts = {}
    capped = _cap(items, llm_max_items if enrich == "llm" else 0)
    if not capped:
        return verdicts, stats
    enricher = Enricher(ctx, enabled=(enrich == "llm"))
    if not enricher.available:
        stats.error("disabled")
        return verdicts, stats
    stats.started = time.time()
    for batch in _batches(capped, ASSESS_BATCH):
        stats.batches += 1
        stats.items += len(batch)
        payload = [{"id": it.get("_bookmark_id") or it.get("id") or idx,
                    "name": it.get("name") or "",
                    "description": (it.get("description") or "")[:400],
                    "topics": it.get("topics") or []}
                   for idx, it in enumerate(batch)]
        parsed = enricher._complete(instructions=ASSESS_INSTRUCTIONS,
                                    batch_items=payload,
                                    schema=ASSESS_SCHEMA,
                                    schema_name="starlearner.assess.v1",
                                    purpose="starlearner.assess", stats=stats)
        if parsed is None:
            continue
        by_id = {}
        for row in parsed:
            if isinstance(row, dict) and row.get("id") is not None:
                by_id[str(row.get("id"))] = row
        for it in batch:
            payload_id = it.get("_bookmark_id") or it.get("id")
            row = by_id.get(str(payload_id))
            if not row:
                stats.error("missing_item")
                continue
            key = item_source_key(it)
            integrate = row.get("integrate")
            opportunity = row.get("opportunity")
            if not isinstance(integrate, bool) or \
                    not isinstance(row.get("integrate_rationale") or "", str) or \
                    not isinstance(opportunity, (str, type(None))):
                stats.error("invalid_item")
                continue
            verdicts[key] = {
                "integrate": integrate,
                "integrate_rationale":
                    str(row.get("integrate_rationale") or "")[:300],
                "opportunity":
                    (str(opportunity).strip().lower() or None)
                    if opportunity else None,
                "opportunity_rationale":
                    str(row.get("opportunity_rationale") or "")[:300],
            }
    return verdicts, stats
