"""skills_out.py — the generated-skills subsystem (spec A.7).

Where generated skills live and how they become the agent's:

  * **Write root** — ``plugin_data_dir("starlearner-nexus") / "generated_skills"``: the
    host-owned, profile-scoped store (NEVER the install tree — the dev
    guide's store-durable-state rule; survives ``hermes plugins update`` /
    ``remove``, follows the active profile).
  * **Registry** — ``plugin_db("starlearner-nexus")`` (SQLite, WAL): the authoritative
    index of generated skills (A.7.2.1 — the registry, not a walk of the data
    dir, is what ``register_all`` iterates). Plus the per-item ``review``
    store (the human-in-the-loop surface: LLM-derived Track-B hits and
    llm-overrides land here, never silently in the ledger).
  * **Registration** — ``ctx.register_skill(skill_name, skill_md, description)``
    at (a) ``register()`` time (``register_all`` — the guaranteed
    next-session form, A.7.4 layer 1, PROVEN by the mission-C probe) and
    (b) harvest-handler time (``write_and_register`` — the A.7.4 layer 2,
    PROBE WORLD A: handler-time registration is accepted AND the skill is
    live in the same session — ``skill_view("starlearner-nexus:<name>")`` resolves it
    through the real agent path, the bundle banner lists live siblings, and
    the skill is offered into the skills index on the next prompt build).
    Registered skills are namespaced ``starlearner-nexus:<skill_name>`` (the plugin's
    manifest name), read-only, never copied into ``~/.hermes/skills/``.

**Multi-run collision law (our own namespace, our own law — A.7.2):**

  1. The registry is the index; orphaned/drifted files on disk are reported,
     never registered.
  2. Same source_key → same skill_name → idempotent (content-unchanged skip
     in the generator; ``last_seen`` bumps).
  3. Same skill_name, different source_key (two bookmarks slug to the same
     name): the second gets a deterministic suffix —
     ``skill_name + "-" + sha256(source_key)[:6]`` — resolved BEFORE the
     generate stage runs (the name is the generator's input), so files,
     frontmatter and registry always agree. Never overwrite, never drop.
  4. Cross-plugin collisions: the host's rule (native-over-native =
     last-wins; a clash involving a portable plugin is refused) —
     catalog-name uniqueness + rule 3 make this a log-line defense.
  5. Never collides with built-ins/user skills: namespacing.

``register_generated_skills: false`` still writes files + registry rows
(reviewable via starlearner_review) but never calls ``ctx.register_skill``.

Nothing here imports hermes at module level (``plugin_data_dir`` /
``plugin_db`` are imported lazily inside the functions). SQLite rows hold
plain assessment data only — no bookmark text (the text stays in the
engine's data files under plugin-data; review rows carry the text head for
the starlearner_review surface).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import runtime

PLUGIN = runtime.PLUGIN_NAME

# ── plugin-data + plugin_db (lazy, public hermes surfaces) ──────────────────


def data_dir() -> Path:
    """``<hermes home>/plugin-data/starlearner-nexus/`` (created on first use)."""
    from plugins.plugin_storage import plugin_data_dir
    return plugin_data_dir(PLUGIN)


def gen_root() -> Path:
    """``<plugin-data>/generated_skills`` (the write root)."""
    root = data_dir() / "generated_skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _db():
    """``plugin_db("starlearner-nexus")`` — the registry + review store."""
    from plugins.plugin_storage import plugin_db
    return plugin_db(PLUGIN)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _init_db(db) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS skills (
            skill_name       TEXT PRIMARY KEY,
            source_key       TEXT UNIQUE,
            category         TEXT,
            first_seen       TEXT,
            last_seen        TEXT,
            rel_path         TEXT,
            frontmatter_name TEXT,
            registered       INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS review (
            source_key            TEXT PRIMARY KEY,
            ts                    TEXT,
            item_id               TEXT,
            author                TEXT,
            text_head             TEXT,
            category              TEXT,
            integrate             INTEGER,
            integrate_reason      TEXT,
            opportunity           TEXT,
            opportunity_rationale TEXT,
            engine                TEXT,
            llm_override          INTEGER DEFAULT 0,
            llm_integrate        INTEGER DEFAULT 0,
            skill_name            TEXT,
            generated            INTEGER DEFAULT 0
        );
        """
    )
    db.commit()


# ── naming + the collision law (A.7.2) ───────────────────────────────────────

# A valid skill name for ctx.register_skill: [a-zA-Z0-9_-]+ (no ':').
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def safe_skill_name(name: str) -> str:
    """Slugify a (rules or LLM) map name into a register-safe skill name
    (mirrors the engine's generate_skill_name rules)."""
    import re as _re
    skill = _re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    if skill and not skill[0].isalpha():
        skill = "skill-" + skill
    return (skill or "unknown-skill")[:96]


def item_source_key(item: dict) -> str:
    """The ledger's identity key (tweet:<id> for mapped bookmarks)."""
    if item.get("_bookmark_id"):
        return f"tweet:{item['_bookmark_id']}"
    if item.get("id") is not None:
        return f"id:{item['id']}"
    if item.get("name"):
        return f"name:{item['name']}"
    blob = json.dumps(item, sort_keys=True, default=str).encode("utf-8")
    return "hash:" + hashlib.sha256(blob).hexdigest()[:16]


def resolve_collisions(items, db) -> dict:
    """Apply the collision law (A.7.2.2-3 (B.7: source_key = id:<GitHub id>)) over the NEW items, BEFORE the
    generate stage runs (the resolved name is the generator's input).

    Returns ``renames`` = {item_key: {"from": name, "to": skill_name}} — the
    caller rewrites the items' ``name`` with the resolved value. Names are
    always normalized through :func:`safe_skill_name` (what the generator's
    own generate_skill_name would produce); a *recorded* rename is a real
    collision suffix (rule 3).
    """
    renames: dict = {}
    taken: dict = {}  # skill_name -> source_key (this run + the registry)
    for row in db.execute("SELECT skill_name, source_key FROM skills"):
        taken[row[0]] = row[1]
    for item in items:
        key = item_source_key(item)
        base = safe_skill_name(item.get("name"))
        item["name"] = base
        # Same source_key → same name → idempotent (rule 2).
        owner = taken.get(base)
        if owner is None or owner == key:
            taken[base] = key
            continue
        # Same name, different source_key → deterministic suffix (rule 3).
        suffixed = f"{base}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:6]}"
        renames[key] = {"from": base, "to": suffixed}
        item["name"] = suffixed
        taken[suffixed] = key
    return renames


def _frontmatter_description(skill_md: Path) -> str:
    """The frontmatter description line of a generated SKILL.md (the
    description register_skill/prompt rows/skills_list show). None-safe."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return ""
    d = re.search(r"^description:\s*\"?(.+?)\"?\s*$", m.group(1), re.MULTILINE)
    return (d.group(1) if d else "")[:400]


# ── register_all: the register()-time startup scan (A.7.2.1, A.7.4.1) ────────


def register_all(ctx) -> int:
    """The startup scan: register every registry row (the authoritative
    index) whose SKILL.md exists on disk. Orphaned files on disk are
    reported, never registered. THE GUARANTEED FORM (probe run 1 P5 + run 2:
    a fresh process re-registers everything generated before it)."""
    db = _db()
    _init_db(db)
    root = gen_root()
    registered = 0
    orphans = []
    rows = list(db.execute(
        "SELECT skill_name, source_key, rel_path, registered FROM skills "
        "ORDER BY first_seen, skill_name"))
    for skill_name, source_key, rel_path, want_registered in rows:
        skill_md = root / rel_path
        if not skill_md.is_file():
            orphans.append(rel_path)
            continue
        if not want_registered:
            continue
        try:
            ctx.register_skill(skill_name, skill_md,
                               _frontmatter_description(skill_md))
            registered += 1
        except Exception as exc:  # never fail the load on one skill
            runtime.log.warning("starlearner-nexus: startup register_skill(%r) -> %r",
                                skill_name, exc)
    if orphans:
        runtime.log.warning("starlearner-nexus: %d orphaned generated skill file(s) on "
                            "disk (not in the registry, not registered): %s",
                            len(orphans), ", ".join(orphans[:5]))
    db.close()
    return registered


# ── write_and_register: the harvest-time path (A.7.4.2 = probe WORLD A) ──────


def write_and_register(ctx, items, categories, assess_data, llm_map, llm_cat,
                       llm_assess, gen_stats, register_skills=True) -> dict:
    """Record + register this run's generated skills.

    * items: the NEW items (post map-enrichment, post collision-resolution,
      post categorize) — the review rows + the registry keys.
    * categories: {item_key: final category} (the fusion's verdict).
    * gen_stats: the engine generate_skills stats (+ per-item files via the
      category dirs).
    * llm_map/llm_cat/llm_assess: the enrichment layers' per-item data (for
      the review rows' engine/llm_override fields).

    Returns ``{"generated": n, "unchanged": n, "per_category": {...},
    "registered": [qualified names], "review_rows": n, "errors": [...]}``.
    """
    db = _db()
    _init_db(db)
    root = gen_root()
    now = _now()
    out = {"generated": (gen_stats or {}).get("skills_generated", 0),
           "unchanged": (gen_stats or {}).get("skills_unchanged", 0),
           "per_category": (gen_stats or {}).get("categories", {}),
           "registered": [], "review_rows": 0, "errors": []}

    for item in items:
        key = item_source_key(item)
        category = (categories or {}).get(key) or "uncategorized"
        skill_name = safe_skill_name(item.get("name"))
        rel_path = None
        # The generated file (this run or a previous one — idempotent).
        for candidate in (skill_name, str(item.get("name") or "")):
            if not candidate:
                continue
            p = Path(category) / safe_skill_name(candidate)
            if (root / p / "SKILL.md").is_file():
                rel_path = p.as_posix()
                break
        if rel_path is None:
            p = Path(category) / skill_name
            if (root / p / "SKILL.md").is_file():
                rel_path = p.as_posix()
        generated = rel_path is not None

        # ── the review row (the human-in-the-loop surface) ────────────────
        a_map = (assess_data or {}).get("_by_key", {}).get(key, {})
        llm_a = (llm_assess or {}).get(key, {})
        llm_c = (llm_cat or {}).get(key, {})
        rules_integrated = bool(a_map.get("integrated"))
        rules_opportunity = a_map.get("opportunity")
        llm_integrate = bool(llm_a.get("integrate"))
        llm_opportunity = llm_a.get("opportunity")
        llm_override = 0
        engine = "rules"
        integrate = rules_integrated
        integrate_reason = a_map.get("integrate_rationale") or (
            "integration keyword/star-rank heuristic" if rules_integrated
            else "")
        opportunity = rules_opportunity
        opportunity_rationale = a_map.get("opportunity_rationale") or ""
        if llm_a:
            engine = "llm"
            # Fusion (A.4.2): keyword hits are the FLOOR (union) for Track A
            # (an LLM-true adds a candidate); LLM Track-B hits are
            # review-only — NEVER written to the ledger without review.
            if llm_integrate and not rules_integrated:
                integrate = llm_integrate
                integrate_reason = llm_a.get("integrate_rationale") or ""
                llm_override = 1
            elif not llm_integrate and rules_integrated:
                llm_override = 1
            if llm_opportunity and not rules_opportunity:
                llm_override = 1
        if llm_c:
            # The categorize fusion markers (A.4.2) — the review-visibility
            # law: EVERY LLM-vs-rules divergence is review-visible, from
            # whichever stage it came. An APPLIED verdict (the LLM
            # classified a keyword-orphaned item) marks engine=llm; a
            # confident DISAGREEMENT (never applied) ORs llm_override.
            if llm_c.get("_applied"):
                engine = "llm"
            if llm_c.get("_llm_override"):
                llm_override = 1
        try:
            # 15 INSERT values + 7 UPDATE values (ON CONFLICT upsert).
            # LLM-derived Track-B stays review-only (opportunity column
            # carries the RULES verdict; the LLM's lands in the row's
            # llm_override/llm_integrate flags + engine marker for
            # starlearner_review) — never silently in the ledger.
            db.execute(
                "INSERT INTO review (source_key, ts, item_id, author, "
                "text_head, category, integrate, integrate_reason, "
                "opportunity, opportunity_rationale, engine, llm_override, "
                "llm_integrate, skill_name, generated) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(source_key) DO UPDATE SET ts=excluded.ts, "
                "category=excluded.category, "
                "integrate=excluded.integrate, "
                "integrate_reason=excluded.integrate_reason, "
                "opportunity=excluded.opportunity, "
                "opportunity_rationale=excluded.opportunity_rationale, "
                "engine=excluded.engine, llm_override=excluded.llm_override, "
                "llm_integrate=excluded.llm_integrate, "
                "skill_name=excluded.skill_name, "
                "generated=excluded.generated",
                (key, now,
                 str(item.get("_bookmark_id") or item.get("id") or ""),
                 str(item.get("author")
                      or (item.get("owner") or {}).get("login") or ""),
                 (item.get("description") or "")[:160], category,
                 1 if integrate else 0, integrate_reason,
                 rules_opportunity if rules_opportunity else None,
                 opportunity_rationale,
                 engine, llm_override, 1 if llm_integrate else 0,
                 skill_name if generated else None, 1 if generated else 0))
            out["review_rows"] += 1
        except Exception as exc:  # a review row must never fail the run
            out["errors"].append(f"review[{key}]: {type(exc).__name__}")
            db.rollback()

        # ── the registry + handler-time registration (probe WORLD A) ──────
        if not generated or rel_path is None:
            continue
        registered = 1 if register_skills else 0
        try:
            db.execute(
                "INSERT INTO skills (skill_name, source_key, category, "
                "first_seen, last_seen, rel_path, frontmatter_name, "
                "registered) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(skill_name) DO UPDATE SET last_seen=?, "
                "registered=?, rel_path=?, category=?",
                (skill_name, key, category, now, now, rel_path,
                 skill_name, registered,
                 now, registered, rel_path, category))
        except Exception as exc:
            out["errors"].append(f"registry[{key}]: {type(exc).__name__}")
            db.rollback()
            continue
        if not register_skills:
            continue
        skill_md = root / rel_path
        try:
            ctx.register_skill(skill_name, skill_md,
                               _frontmatter_description(skill_md))
            out["registered"].append(f"{PLUGIN}:{skill_name}")
        except Exception as exc:  # never fail the run on one registration
            out["errors"].append(f"register_skill[{key}]: {type(exc).__name__}")
            runtime.log.warning("starlearner-nexus: handler-time register_skill(%r) "
                                "-> %r", skill_name, exc)
    db.commit()
    db.close()
    return out


# ── status / review (the read surfaces) ──────────────────────────────────────


def status() -> dict:
    """The skills + pending-review part of starlearner_status."""
    db = _db()
    _init_db(db)
    rows = list(db.execute("SELECT skill_name, registered FROM skills"))
    pending = db.execute(
        "SELECT COUNT(*) FROM review WHERE llm_override=1").fetchone()
    db.close()
    return {"registered": [f"{PLUGIN}:{r[0]}" for r in rows if r[1]],
            "count": len(rows),
            "pending_review": (pending or [0])[0]}


def review_rows(since=None, category=None, opportunities_only=False,
                include_skill_md=False, last_run_ts=None) -> dict:
    """starlearner_review's data: the review table (newest last), filtered."""
    db = _db()
    _init_db(db)
    query = "SELECT * FROM review"
    conds, params = [], []
    if since:
        conds.append("ts >= ?")
        params.append(since)
    if category:
        conds.append("category = ?")
        params.append(category)
    if opportunities_only:
        conds.append("(llm_override=1 OR opportunity IS NOT NULL)")
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY ts, source_key"
    rows = list(db.execute(query, params))
    db.close()
    items = []
    for row in rows:
        (key, ts, item_id, author, text_head, category, integrate,
         integrate_reason, opportunity, opportunity_rationale, engine,
         llm_override, llm_integrate, skill_name, generated) = row
        item = {"id": key, "item_id": item_id, "author": author,
                "text_head": text_head, "category": category,
                "integrate": bool(integrate),
                "integrate_reason": integrate_reason or None,
                "opportunity": opportunity,
                "opportunity_rationale": opportunity_rationale or None,
                "engine": engine or "rules",
                "llm_override": bool(llm_override),
                "skill": f"{PLUGIN}:{skill_name}" if skill_name else None,
                "generated": bool(generated)}
        if include_skill_md and skill_name:
            skill_md = gen_root() / category / skill_name / "SKILL.md"
            if skill_md.is_file():
                lines = skill_md.read_text(
                    encoding="utf-8", errors="replace").splitlines()[:40]
                item["skill_md_head"] = "\n".join(lines)
        items.append(item)
    return {"items": items,
            "counts": {"total": len(items),
                       "integrated": sum(1 for i in items if i["integrate"]),
                       "opportunities": sum(1 for i in items
                                            if i["opportunity"]),
                       "llm_flagged": sum(1 for i in items
                                          if i["llm_override"])}}
