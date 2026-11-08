"""harvest.py — the in-process sync driver (spec B.3.1; the starlearner
twin of the reapx harvest driver).

What ``scripts/daily_sync.sh`` orchestrates as a shell pipeline (minus
its fetch branch), run in-process inside a tool call — the same engine
stages, in the same order, into the host-owned
``plugin_data_dir("starlearner-nexus")`` (B.2.1's seam):

  ① fetch (github_fetch)               GET /user/starred (secret_scope
                                        token; in-process requests; the
                                        standalone's gh/curl fetcher is
                                        standalone-only — B.1.3/B.6.3)
  ② ledger diff (0 new ⇒ exit)         ledger.diff_new (key id:<GitHub id>)
  ③ llm.enrich_map                     (B.4 map: the curation pass over
                                        the repo objects)
  ④ skills_out.resolve_collisions      (A.7.2's law, BEFORE generate)
       → rewrite new_repos.json (the final identities)
  ⑤ categorize (rules)                 categorize_repos.categorize_repos
  ⑥ llm.enrich_categorize              (A.4.2's fixed fusion — see below)
  ⑦ assess (rules)                     assess_repos' pure functions (the
                                        driver replicates its main(): the
                                        rules engine's opportunities.json,
                                        bit-for-bit)
  ⑧ llm.enrich_assess                  (A.4.2's fusion — see below)
  ⑨ generate (Jinja2, NO LLM)          generate_skills.generate_skills(
                                           in, out, generate_limit,
                                           plugin_skill.md.j2)
  ⑩ skills_out.write_and_register      (registry + handler-time
                                        register_skill + the review rows)
  ⑪ ledger update (success only)       ledger.update_ledger (a mid-run
                                        failure never marks items seen)

**The categorize fusion (A.4.2, fixed + deterministic):** a keyword hit
always wins (it drives the directory structure); the LLM classifies (a)
items the keyword engine left ``uncategorized``; an LLM verdict
(confidence ≥ 0.8) that DISAGREES with a strong keyword verdict is
recorded as ``llm_override`` for the human (starlearner_review), never
applied.

**The assess fusion (A.4.2):** keyword hits are the floor (union) for
Track A (an LLM-true on a rules-false item adds a *candidate*, flagged
engine=llm/llm_override for review); LLM-derived Track-B hits land in
the review store ONLY — never in the rules opportunities.json
(bit-for-bit) and never in the ledger without review.

**enrich=rules (or llm_max_items=0, or every LLM failure) ⇒ the current
engine, bit-for-bit**: steps ③④(renames)/⑥⑧ collapse into the rules
output (verified by test_sync_driver's rules-mode fixture run).

**The error model (B.3.1, R12)**: every failure = a clean
``{"ok": false, "error": <kind>, "detail": …}`` — token_not_set (the
install-prompt fix), github_401 (never the token), github_403_rate,
github_5xx, fetch_timeout, max_pages_exhausted (a WARNING flag, not an
error), sync_already_running, llm_unavailable (NOT an error:
enrichment=rules + llm.errors) — never a prompt, never a hang, nothing
that waits for a person.

The single-flight lock makes cron + interactive + a curious model call
starlearner_sync twice safe.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import runtime

# ── the single-flight lock (B.3.1) ───────────────────────────────────────────

_FLIGHT = {"running": False, "started": None}
_FLIGHT_LOCK = threading.Lock()


class SyncBusy(RuntimeError):
    """A second concurrent sync (clean error JSON, R12)."""


def _acquire() -> float:
    with _FLIGHT_LOCK:
        if _FLIGHT["running"]:
            started = _FLIGHT["started"]
            raise SyncBusy(
                f"sync already running (started {started})")
        _FLIGHT["running"] = True
        _FLIGHT["started"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())
        return time.time()


def _release() -> None:
    with _FLIGHT_LOCK:
        _FLIGHT["running"] = False
        _FLIGHT["started"] = None


def harvest_running() -> bool:
    with _FLIGHT_LOCK:
        return bool(_FLIGHT["running"])


# ── the fetch error model (B.3.1) ────────────────────────────────────────────


class HarvestError(RuntimeError):
    """A mapped sync failure (kind + fix, never a traceback)."""

    def __init__(self, kind: str, detail: str = "", extra: dict | None = None):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail
        self.extra = extra or {}


def _map_fetch_error(exc: BaseException) -> HarvestError:
    """Map github_fetch's AuthError (and anything else) onto the B.3.1
    error kinds."""
    kind = getattr(exc, "kind", None)
    if kind:
        return HarvestError(kind, str(exc).split(":", 1)[-1].strip()
                            or getattr(exc, "detail", ""),
                            getattr(exc, "extra", {}))
    text = str(exc) or type(exc).__name__
    if "Max retries" in text or "New Connection" in text or \
            "Name or service" in text:
        return HarvestError(
            "fetch_error", text,
            {"fix": "api.github.com unreachable (network down? the "
                    "next sync retries clean)"})
    return HarvestError("engine_error", text)


# ── the run record (starlearner_status' data) ─────────────────────────────────


def _run_state_path() -> Path:
    from . import skills_out
    return skills_out.data_dir() / "run_state.json"


def _read_run_state() -> dict:
    try:
        return json.loads(_run_state_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_run_state(state: dict) -> None:
    path = _run_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False,
                              default=str), encoding="utf-8")
    tmp.replace(path)


# ── the driver ────────────────────────────────────────────────────────────────

# The B.3.1 note, written from the probe's answer (never from hope).
NOTE = ("New skills are registered and loadable now with "
        "skill_view(\"starlearner-nexus:<name>\"), listed by "
        "starlearner_status/starlearner_review, and appear in "
        "skills_list + the skills index on the next prompt build; a "
        "plugin (re)load re-registers them from the plugin_db registry "
        "(the guaranteed form).")

NOTE_RULES = ("No LLM enrichment was applied (enrich=rules): the "
              "deterministic rules engine ran bit-for-bit. Generated "
              "skills are loadable now with "
              "skill_view(\"starlearner-nexus:<name>\").")

NOTE_REVIEW_ONLY = ("register_generated_skills=false (the default): the "
                    "skill files are written and reviewable via "
                    "starlearner_review, not registered — switch the "
                    "setting on once you trust the output.")


# ── the per-call argument allowlist ──────────────────────────────────────────
#
# The review point: a tool call may carry ANY JSON object, so the only args
# honoured are these three — everything else is dropped. They never carry a
# setting: ``dry_run`` is per-call intent, the two caps are per-call tightening
# of a configured ceiling (``min(arg, setting)``); enrich / llm_max_items /
# register_generated_skills come from the plugin config alone.
SYNC_ARGS = ("dry_run", "max_pages", "generate_limit")


def _allowlisted(args: dict | None) -> dict:
    return {key: value for key, value in (args or {}).items()
            if key in SYNC_ARGS and value is not None}


class _Pipeline:
    """One sync run."""

    def __init__(self, args: dict):
        self.args = _allowlisted(args)
        from . import skills_out
        self.so = skills_out
        try:
            self.data = skills_out.data_dir()
            # engine files under the plugin data dir (B.2.1's seam)
            self.gen_root = self.data / "generated_skills"
            self.starred = self.data / "starred_repos.json"
            self.new_repos = self.data / "new_repos.json"
            self.categorized = self.data / "categorized_repos.json"
            self.opportunities = self.data / "opportunities.json"
            self.ledger_path = self.data / "ledger.json"
        except Exception:
            # no hermes / no plugin-data host at all (a hermes-free
            # import check): the run fails clean at its first data touch
            # (R12) — e.g. starlearner_sync without a hermes = the clean
            # token error from the github stage (which never touches the
            # data dir), never a plugin-import crash.
            self.data = None
            self.gen_root = None
            self.starred = self.new_repos = self.categorized = None
            self.opportunities = self.ledger_path = None
        # settings: the plugin config ONLY (the review point — never args).
        enrich = runtime.setting("enrich", "llm")
        self.enrich = enrich if enrich in ("llm", "rules") else "llm"
        self.llm_max_items = runtime.setting_int("llm_max_items", 50)
        self.register_skills = bool(runtime.setting(
            "register_generated_skills", False))
        # the per-call caps: min(arg, setting), the setting is the ceiling
        self.generate_limit = runtime.capped_arg(
            self.args, "generate_limit",
            runtime.setting_int("generate_limit", 5))
        self.max_pages = runtime.capped_arg(
            self.args, "max_pages", runtime.setting_int("max_pages", 30))
        self.dry_run = bool(self.args.get("dry_run"))
        self.result: dict = {"ok": True}
        # the enrichment layers' outputs (set as the run progresses)
        self._llm_map: dict = {}
        self._llm_cat: dict = {}
        self._llm_assess: dict = {}
        self.assess_data: dict = {}

    # ── ① fetch (github_fetch) ──────────────────────────────────────────
    def fetch(self):
        from . import github_fetch
        try:
            repos = github_fetch.fetch_starred(max_pages=self.max_pages)
        except github_fetch.AuthError as exc:
            raise _map_fetch_error(exc) from exc
        except BaseException as exc:  # never a bare escape
            raise _map_fetch_error(exc) from exc
        # ①' the starred set → the engine's data file (the fetcher IS the
        # map stage for stars: full GitHub repo objects; B.6.3 — the
        # standalone's gh/curl fetcher writes the same file)
        self.data.mkdir(parents=True, exist_ok=True)
        tmp = self.starred.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(repos, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.starred)
        self.result["fetched_total"] = len(repos)
        if github_fetch.last_max_pages_exhausted:
            self.result["max_pages_exhausted"] = True

    # ── ② ledger diff (0 new ⇒ early return) ────────────────────────────
    def diff(self) -> list:
        from . import _engine
        _engine.load()  # the one engine load (the ②-stage contract)
        items = self._load(self.starred)
        ledger = _engine.ledger.load_ledger(self.ledger_path)
        new = _engine.ledger.diff_new(items, ledger)
        self._dump(self.new_repos, new)
        self.result["new_count"] = len(new)
        self.result["ledger"] = _engine.ledger.report(ledger)
        return new

    # ── ③ llm.enrich_map + ④ collisions → the final identities ─────────
    def enrich_and_resolve(self, new: list):
        from . import llm as llm_mod
        from . import skills_out
        llm_map, map_stats = llm_mod.enrich_map(
            new, llm_max_items=self.llm_max_items, enrich=self.enrich)
        applied = 0
        for item in new:
            key = skills_out.item_source_key(item)
            override = llm_map.get(key)
            if override:
                item["name"] = override["name"]
                item["description"] = override["description"]
                item["topics"] = override["topics"]
                item["_map_engine"] = "llm"
                applied += 1
        # The collision law (A.7.2) — BEFORE the generate (the resolved
        # name is the generator's input).
        db = skills_out._db()
        skills_out._init_db(db)
        renames = skills_out.resolve_collisions(new, db)
        db.close()
        # Rewrite new_repos.json with the final identities.
        self._dump(self.new_repos, new)
        self.result["llm_map"] = {"applied": applied,
                                  **map_stats.as_dict()}
        self.result["collisions"] = len(renames)
        if renames:
            self.result["collision_renames"] = [
                {"key": k, **v} for k, v in renames.items()]
        return llm_map, map_stats

    # ── ⑤ categorize (rules) ────────────────────────────────────────────
    def categorize(self):
        from . import _engine
        _engine.categorize_repos.categorize_repos(
            str(self.new_repos), str(self.categorized))

    # ── ⑥ llm.enrich_categorize + the fixed fusion (A.4.2) ──────────────
    def enrich_categorize(self, new: list):
        from . import llm as llm_mod
        from . import skills_out
        cat_data = self._load(self.categorized)
        rules_cats = dict(cat_data.get("categories") or {})
        uncategorized = list(cat_data.get("uncategorized") or [])
        verdicts, cat_stats = llm_mod.enrich_categorize(
            new, llm_max_items=self.llm_max_items, enrich=self.enrich)

        # The rules verdict per item (keyword hits).
        rules_cat_by_key = {}
        for cat, repos in rules_cats.items():
            for repo in repos:
                rules_cat_by_key[skills_out.item_source_key(repo)] = cat
        for repo in uncategorized:
            rules_cat_by_key[skills_out.item_source_key(repo)] = \
                "uncategorized"

        applied = 0
        overrides = 0
        for item in new:
            key = skills_out.item_source_key(item)
            rules_cat = rules_cat_by_key.get(key) or "uncategorized"
            llm_verdict = verdicts.get(key)
            final_cat = rules_cat
            engine = "rules"
            llm_override = 0
            if llm_verdict:
                llm_cat = llm_verdict["category"]
                conf = llm_verdict["confidence"]
                # The fusion: a keyword hit always wins; the LLM classifies
                # the uncategorized; a confident DISAGREEMENT with a
                # keyword verdict is a review-only llm_override.
                if rules_cat == "uncategorized" and llm_cat != \
                        "uncategorized":
                    final_cat = llm_cat
                    engine = "llm"
                    applied += 1
                elif (rules_cat != "uncategorized"
                      and llm_cat != rules_cat
                      and conf >= 0.8):
                    llm_override = 1
                    overrides += 1
                elif rules_cat != "uncategorized" and llm_cat == rules_cat:
                    engine = "llm"
            item["_category"] = final_cat
            item["_cat_engine"] = engine
            item["_llm_override"] = llm_override
            item["_llm_cat"] = llm_verdict["category"] if llm_verdict else None

        # Re-bucket the categorized file with the fusion's verdicts.
        final_cats: dict = {}
        for item in new:
            final_cats[skills_out.item_source_key(item)] = item["_category"]
        merged: dict = {}
        for cat in list(rules_cats.keys()):
            merged[cat] = [r for r in rules_cats[cat]
                           if final_cats.get(skills_out.item_source_key(r))
                           == cat]
        for item in new:
            cat = item["_category"]
            if cat == "uncategorized":
                continue
            if cat not in merged:
                merged[cat] = []
            keys_in_cat = {skills_out.item_source_key(r)
                           for r in merged[cat]}
            key = skills_out.item_source_key(item)
            if key not in keys_in_cat:
                merged[cat].append(item)
        merged.pop("uncategorized", None)
        cat_data["categories"] = merged
        cat_data["uncategorized"] = [
            item for item in new if item["_category"] == "uncategorized"]
        cat_data["metadata"]["categorized_count"] = sum(
            len(v) for v in merged.values())
        cat_data["metadata"]["uncategorized_count"] = len(
            cat_data["uncategorized"])
        self._dump(self.categorized, cat_data)
        self.result["llm_categorize"] = {"applied": applied,
                                         "llm_overrides": overrides,
                                         **cat_stats.as_dict()}
        self.result["categories"] = {
            cat: len(repos) for cat, repos in sorted(merged.items())
            if repos} or {"uncategorized": len(cat_data["uncategorized"])}
        return verdicts, cat_stats

    # ── ⑦ assess (rules, replicated bit-for-bit) ────────────────────────
    def assess(self, new: list):
        from . import _engine
        from . import skills_out
        assess_mod = _engine.assess_repos
        integrated, opportunities = [], []
        for repo in new:
            name = repo.get("full_name") or repo.get("name") or "unknown"
            url = repo.get("html_url") or ""
            stars = repo.get("stargazers_count") or 0
            integ = assess_mod.assess_integration(repo)
            domain, rationale = assess_mod.assess_opportunity(repo)
            if integ:
                integrated.append({"name": name, "url": url, "stars": stars})
            if domain:
                opportunities.append({
                    "name": name, "url": url, "stars": stars,
                    "domain": domain, "rationale": rationale})
        import datetime
        result = {
            "generated_at": datetime.datetime.now().isoformat(),
            "counts": {
                "assessed": len(new),
                "integrated": len(integrated),
                "opportunities": len(opportunities),
            },
            "integrated": integrated,
            "opportunities": opportunities,
        }
        self._dump(self.opportunities, result)
        # _by_key: the review rows' rules verdicts (LLM-derived Track-B
        # never reaches the opportunities list — review only).
        by_key = {}
        for repo in new:
            key = skills_out.item_source_key(repo)
            integ = assess_mod.assess_integration(repo)
            domain, rationale = assess_mod.assess_opportunity(repo)
            by_key[key] = {"integrated": integ,
                           "opportunity": domain,
                           "opportunity_rationale": rationale}
            repo["_a_integrate"] = integ
            repo["_a_opportunity"] = domain
        result["_by_key"] = by_key
        self.assess_data = result
        self.result["opportunities"] = dict(result["counts"])

    # ── ⑧ llm.enrich_assess (the fixed fusion) ──────────────────────────
    def enrich_assess(self, new: list):
        from . import llm as llm_mod
        from . import skills_out
        verdicts, stats = llm_mod.enrich_assess(
            new, llm_max_items=self.llm_max_items, enrich=self.enrich)
        # The fusion (A.4.2) is applied in skills_out.write_and_register's
        # review rows (keyword floor / union for A candidates / review-only
        # for B) — the rules opportunities.json stays bit-for-bit.
        for item in new:
            verdict = verdicts.get(skills_out.item_source_key(item))
            if verdict:
                item["_assess_engine"] = "llm"
        self.result["llm_assess"] = stats.as_dict()
        return verdicts, stats

    # ── ⑨ generate (Jinja2, no LLM) ─────────────────────────────────────
    def generate(self):
        from . import _engine
        from . import runtime as _rt
        if self.generate_limit <= 0:
            self.result["skills"] = {"generated": 0, "unchanged": 0,
                                     "per_category": {},
                                     "skipped": "generate_limit=0 "
                                                "(assess-only)"}
            return {}
        stats = _engine.generate_skills.generate_skills(
            str(self.categorized), str(self.gen_root),
            generate_limit=self.generate_limit,
            template_name=_rt.PLUGIN_TEMPLATE)
        self.result["skills"] = {
            "generated": stats.get("skills_generated", 0),
            "unchanged": stats.get("skills_unchanged", 0),
            "per_category": {cat: c.get("skills_generated", 0)
                             for cat, c in (stats.get("categories")
                                            or {}).items()},
        }
        return stats

    # ── ⑩ skills_out ────────────────────────────────────────────────────
    def write_and_register(self, new: list, gen_stats: dict):
        from . import skills_out
        ctx = runtime.get_ctx()
        llm_map = getattr(self, "_llm_map", None) or {}
        llm_cat = getattr(self, "_llm_cat", None) or {}
        llm_assess = getattr(self, "_llm_assess", None) or {}
        # llm_cat rows carry the fusion markers for the review rows.
        marked_cat = {}
        for item in new:
            key = skills_out.item_source_key(item)
            if item.get("_cat_engine") == "llm" or item.get("_llm_override"):
                marked_cat[key] = {
                    "category": item.get("_llm_cat"),
                    "confidence": 1.0,
                    "_applied": item.get("_cat_engine") == "llm",
                    "_llm_override": item.get("_llm_override", 0)}
        out = skills_out.write_and_register(
            ctx=ctx, items=new,
            categories={skills_out.item_source_key(i): i.get("_category")
                        for i in new},
            assess_data=getattr(self, "assess_data", {}),
            llm_map=llm_map or {}, llm_cat=marked_cat,
            llm_assess=llm_assess or {}, gen_stats=gen_stats or {},
            register_skills=self.register_skills)
        self.result["skills"].update({
            "generated": out.get("generated", 0),
            "unchanged": out.get("unchanged", 0),
            "per_category": out.get("per_category", {}),
            "registry_errors": out.get("errors", [])})
        # B.3.1: the registered names are a TOP-LEVEL result field — the
        # namespaced names the agent reads out of the tool result and
        # skill_views (result["skills"] = the generation counts only).
        self.result["registered_skills"] = out.get("registered", [])
        self.result["review_rows"] = out.get("review_rows", 0)

    # ── ⑪ ledger update (success only) ──────────────────────────────────
    def update_ledger(self, new: list):
        from . import _engine
        ledger = _engine.ledger.load_ledger(self.ledger_path)
        _engine.ledger.update_ledger(ledger, new, source="github-stars")
        # The review verdicts ride the ledger rows (rules values only —
        # LLM-derived Track-B stays review-only).
        from . import skills_out
        for item in new:
            key = skills_out.item_source_key(item)
            row = ledger.get("items", {}).get(key)
            a_map = (getattr(self, "assess_data", {})
                     .get("_by_key", {}).get(key, {}))
            if row is not None:
                row["integrated"] = bool(a_map.get("integrated"))
                row["opportunity"] = a_map.get("opportunity")
        _engine.ledger.save_ledger(ledger, self.ledger_path)
        self.result["ledger"] = _engine.ledger.report(ledger)

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _count(path: Path) -> int:
        try:
            return len(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return 0

    @staticmethod
    def _load(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _dump(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False,
                                  default=str), encoding="utf-8")
        tmp.replace(path)


# ── the entry point (tools.py calls this) ─────────────────────────────────────


def run_sync(args: dict | None = None) -> dict:
    """starlearner_sync: the B.3.1 handler flow."""
    args = dict(args or {})
    _acquire()
    try:
        return _run(args)
    finally:
        _release()


def _run(args: dict) -> dict:
    p = _Pipeline(args)
    enrich = p.enrich
    try:
        # ① fetch (github_fetch; the token error model lives there)
        p.fetch()

        # ② ledger diff — 0 new ⇒ the R12-fast early return
        new = p.diff()
        p.result["run_id"] = time.strftime("%Y%m%dT%H%M%SZ",
                                           time.gmtime())
        if not new:
            p.result["new_count"] = 0
            p.result["note"] = ("No new stars since the last run "
                                "(the seen-ledger never forgets). Nothing "
                                "was processed.")
            _record(p, ok=True)
            return p.result

        # dry run: fetch + diff (+ enrich) only
        if p.dry_run:
            llm_map, map_stats = p.enrich_and_resolve(new)
            p.result["dry_run"] = True
            p.result["note"] = ("Dry run: fetched + diffed + enriched only; "
                                "no generation, no ledger update, nothing "
                                "registered.")
            _record(p, ok=True)
            return p.result

        # ③④ llm.enrich_map (the curation pass) + the collision law
        llm_map, map_stats = p.enrich_and_resolve(new)
        p._llm_map = llm_map

        # ⑤ categorize (rules)
        p.categorize()

        # ⑥ llm.enrich_categorize + the fixed fusion
        llm_cat, cat_stats = p.enrich_categorize(new)
        p._llm_cat = llm_cat

        # ⑦ assess (rules)
        p.assess(new)

        # ⑧ llm.enrich_assess (the fixed fusion)
        llm_assess, assess_stats = p.enrich_assess(new)
        p._llm_assess = llm_assess

        # ⑨ generate (Jinja2, no LLM)
        gen_stats = p.generate()

        # ⑩ skills_out (registry + handler-time registration + review)
        p.write_and_register(new, gen_stats)

        # ⑪ ledger update — ONLY on full success
        p.update_ledger(new)

        # the result (B.3.1). enrichment = "llm" iff some LLM output was
        # actually APPLIED (map identities / a category fusion verdict / an
        # assess verdict); anything else (failures, the cap, rules mode) is
        # the rules engine, with llm.errors counted (A.4.3).
        llm_any = (enrich == "llm"
                   and (p.result.get("llm_map", {}).get("applied", 0) > 0
                        or p.result.get("llm_categorize", {}).get("applied",
                                                                  0) > 0
                        or len(p._llm_assess or {}) > 0))
        p.result["enrichment"] = "llm" if llm_any else "rules"
        p.result["llm"] = {"map": p.result.get("llm_map", {}),
                           "categorize": p.result.get("llm_categorize", {}),
                           "assess": p.result.get("llm_assess", {})}
        p.result["note"] = (NOTE if p.register_skills else
                            NOTE_REVIEW_ONLY)
        if p.result["enrichment"] == "rules" and enrich == "rules":
            p.result["note"] = (NOTE_RULES if p.register_skills else
                                NOTE_RULES + " " + NOTE_REVIEW_ONLY)
        p.result["new_sample"] = _sample(new)
        _record(p, ok=True)
        return p.result

    except SyncBusy:
        raise
    except HarvestError as exc:
        err = {"ok": False, "error": exc.kind}
        if exc.detail:
            err["detail"] = exc.detail
        if exc.extra:
            err.update(exc.extra)
        p.result.update(err)
        _record(p, ok=False)
        return err
    except Exception as exc:  # never raise out of the driver
        runtime.log.error("starlearner-nexus sync failed: %s", exc,
                          exc_info=True)
        err = {"ok": False, "error": "internal",
               "detail": f"{type(exc).__name__}: {exc}"}
        p.result.update(err)
        _record(p, ok=False)
        return err


def _sample(new: list, limit: int = 5) -> list:
    """B.3.1's new_sample: id, full_name, stars, description head, the two
    tracks."""
    out = []
    for item in new[:limit]:
        out.append({
            "id": item.get("id"),
            "full_name": item.get("full_name"),
            "stars": item.get("stargazers_count"),
            "description_head": (item.get("description") or "")[:100],
            "category": item.get("_category") or "uncategorized",
            "integrate": bool((item.get("_a_integrate"))),
            "opportunity": item.get("_a_opportunity"),
        })
    return out


def _record(p: _Pipeline, ok: bool) -> None:
    """The run record (starlearner_status' last_run)."""
    state = _read_run_state()
    state["last_run"] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": ok,
        "error": None if ok else p.result.get("error"),
        "detail": None if ok else p.result.get("detail"),
        "fetched_total": p.result.get("fetched_total"),
        "new_count": p.result.get("new_count", 0),
        "enrichment": p.result.get("enrichment",
                                   "rules" if ok else None),
        "llm": p.result.get("llm", {}),
        "dry_run": p.dry_run,
    }
    state["register_generated_skills"] = p.register_skills
    try:
        _write_run_state(state)
    except Exception:
        runtime.log.warning("starlearner-nexus: run-state write failed",
                            exc_info=True)
