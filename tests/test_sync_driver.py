#!/usr/bin/env python3
"""test_sync_driver.py — the end-to-end driver tests (B.13 steps 7-9;
the starlearner twin of the reapx test_harvest_driver).

THE acceptance battery for the pipeline, all against the fixture
``tests/fixtures/starred_repos.sample.json`` (4 starred repos: an ai-ml
one, a bitcoin-lightning one, an uncategorized mountain photo, a
development-tools scraper), a pinned tmp HERMES_HOME (everything the run
writes lands under it — never the real home, never the repo tree), and a
monkeypatched ``github_fetch.fetch_starred`` (the hermetic fetch: no
network in the battery):

  * **sync mode, rules engine, bit-for-bit** — run_sync with the
    fixture + enrich=rules: the engine files (starred/new/categorized/
    opportunities/ledger) under plugin-data match the standalone-engine
    verdicts on the same fixture (the probe-pinned rules reality); nothing
    LLM-shaped anywhere (llm stats zero-error-zero-calls);
  * **the fetch error model** (B.3.1/R12) — a 401 from github_fetch = the
    clean github_401 error JSON; a missing token = the clean
    token_not_set error (the REAL fetch path, _secret monkeypatched to
    None) — never a raise, never a hang, nothing that waits for a person;
  * **NO gh, NO curl, NO subprocess, no browser** (B.6.3): the sync path
    never imports the fetch chain (no browser_locator/CDP), the code
    never shells out (static R11 proof), and the github_fetch transport
    carries no subprocess/os.environ anywhere;
  * **the single-flight lock** — a second concurrent run returns
    sync_already_running;
  * **dry_run** — fetch + diff only: no generation, no ledger update,
    nothing registered;
  * **0-new** — a second run over the same stars is the R12-fast early
    return (the seen-ledger never forgets);
  * **the LLM fusion law** (A.4.2) with a mock ctx.llm — keyword hits
    always win; the LLM classifies the uncategorized; a confident
    disagreement is llm_override (review-only); an LLM Track-B hit lands
    in the review store ONLY (never the rules opportunities.json, never
    the ledger);
  * **register_generated_skills=false** — files + review rows + registry
    rows, no register_skill calls;
  * **no repo metadata in the sqlite store** (the review rows carry the
    description head only; the full objects stay in the engine's data
    files).
"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "starred_repos.sample.json"

PLUGIN_PKG = "starlearner_under_test"
HERMES_CHECKOUT = Path("/Users/fromthejump/.hermes/profiles/thanos/"
                       "hermes-agent")

# plugin-data (plugin_db/plugin_data_dir) needs hermes: run under the
# hermes venv with the checkout on the path (mission-A's HAVE_HERMES
# pattern).
if str(HERMES_CHECKOUT) not in sys.path and HERMES_CHECKOUT.is_dir():
    sys.path.insert(0, str(HERMES_CHECKOUT))
try:
    import hermes_constants  # noqa: F401
    HAVE_HERMES = True
except Exception:
    HAVE_HERMES = False


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


class FakeLLM:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.results:
            item = self.results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return FakeResult(parsed=None, content_type="text")


class FakeResult:
    def __init__(self, parsed=None, content_type="json"):
        self.parsed = parsed
        self.content_type = content_type


class RecordingCtx:
    """The mock PluginContext: get_config (settings) + llm (the mock) +
    register_skill recording (handler-time registration, the probe's
    WORLD-A mechanism)."""

    def __init__(self, settings=None, llm=None):
        self._settings = settings or {}
        self.llm = llm
        self.registered = []
        self.register_errors = []

    def get_config(self, key, default=None):
        return self._settings.get(key, default)

    def register_skill(self, name, path, *args, **kwargs):
        self.registered.append((str(name), str(path)))


@unittest.skipUnless(HAVE_HERMES,
                     "plugin-data/plugin_db need hermes (run under the "
                     "hermes venv)")
class SyncDriverTests(unittest.TestCase):
    """The sync end-to-end (the plugin-data-rooted pipeline)."""

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.tmp = tempfile.TemporaryDirectory(prefix="starlearner-drv-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "hermes-home"
        self.home.mkdir(parents=True)
        # pin the hermes home (everything the run writes lands under it)
        from hermes_constants import (get_hermes_home,
                                      reset_hermes_home_override,
                                      set_hermes_home_override)
        self._token = set_hermes_home_override(self.home)
        self.addCleanup(lambda: reset_hermes_home_override(self._token))
        self.assertEqual(Path(get_hermes_home()), self.home)
        self.plugin = _load_plugin()
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        # the hermetic fetch: github_fetch.fetch_starred monkeypatched
        from starlearner_under_test import github_fetch as gf
        self.gf = gf
        self._real_fetch = gf.fetch_starred
        self._real_secret = gf._secret
        gf.fetch_starred = self._fixture_fetch
        gf.last_max_pages_exhausted = False

    def tearDown(self):
        self.gf.fetch_starred = self._real_fetch
        self.gf._secret = self._real_secret
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def _fixture_fetch(self, max_pages=30):
        self.gf.last_max_pages_exhausted = False
        return [dict(r) for r in self.fixture]

    # ── the rules run (bit-for-bit) ───────────────────────────────────────
    def test_sync_rules_run_end_to_end(self):
        from starlearner_under_test import harvest as h
        ctx = RecordingCtx(settings={"enrich": "rules",
                                     "register_generated_skills": True})
        self.plugin.runtime.set_ctx(ctx)
        result = h.run_sync({})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["fetched_total"], 4)
        self.assertEqual(result["new_count"], 4)
        # engine files under plugin-data
        data = self.home / "plugin-data" / "starlearner-nexus"
        for name in ("starred_repos.json", "new_repos.json",
                     "categorized_repos.json", "opportunities.json",
                     "ledger.json"):
            self.assertTrue((data / name).is_file(), name)
        # the fixture's categories (the rules engine, zero LLM): 0003
        # (the mountain photo) is rules-uncategorized — no keyword hits,
        # no skill generated for it (the fusion test's LLM-applied lever):
        self.assertEqual(result["enrichment"], "rules")
        self.assertEqual(result["llm"]["map"]["errors"], 0)
        cats = result["categories"]
        self.assertEqual(cats, {"ai-ml": 1, "bitcoin-lightning": 1,
                                "development-tools": 1})
        # generated skills (plugin template), registered (probe WORLD A)
        self.assertEqual(result["skills"]["generated"], 3)
        self.assertEqual(len(ctx.registered),
                         len(result["registered_skills"]))
        for qualified in result["registered_skills"]:
            self.assertTrue(
                qualified.startswith("starlearner-nexus:"))
            bare = qualified.split(":", 1)[1]
            self.assertIn((bare, mock.ANY), [(n, p) for n, p in
                                             ctx.registered])
        # the generated files carry the plugin Quick Start (no tap
        # language):
        gen = data / "generated_skills"
        for skill_md in gen.glob("*/*/SKILL.md"):
            text = skill_md.read_text(encoding="utf-8")
            self.assertIn('skill_view("starlearner-nexus:', text)
            self.assertNotIn("hermes skills tap", text)
        # the rules engine's opportunities.json (bit-for-bit shape): the
        # rules verdicts on the fixture identities — 0001
        # (ai-integration via 'llm' topics) + 0002 (bitcoin-lightning)
        # Track-B, 0001/0002/0004 Track-A integrated (0002 via
        # 'dashboard' in its description):
        opp = json.loads((data / "opportunities.json").read_text())
        self.assertEqual(opp["counts"], {"assessed": 4, "integrated": 3,
                                         "opportunities": 2})
        # the ledger recorded everything (the run succeeded; keys =
        # id:<GitHub id>):
        ledger = json.loads((data / "ledger.json").read_text())
        self.assertEqual(len(ledger["items"]), 4)
        self.assertEqual(ledger["source"], "github-stars")
        # review rows
        self.assertEqual(result["review_rows"], 4)
        # the note (probe-informed)
        self.assertIn("skill_view", result["note"])
        # nothing LLM-shaped
        self.assertEqual(result["llm"]["map"]["batches"], 0)

    def test_no_gh_no_curl_no_subprocess_no_browser(self):
        """B.6.3/R11: the sync path never imports a browser/CDP stack,
        and the code never shells out (static proof)."""
        from starlearner_under_test import harvest as h
        for name in ("browser_locator", "cdp_launcher",
                     "fetch_x_bookmarks"):
            sys.modules.pop(name, None)
        ctx = RecordingCtx(settings={"enrich": "rules"})
        self.plugin.runtime.set_ctx(ctx)
        result = h.run_sync({})
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(any(m.endswith("fetch_x_bookmarks")
                             for m in sys.modules))
        self.assertNotIn("browser_locator", sys.modules)
        self.assertNotIn("cdp_launcher", sys.modules)
        # the static R11 proof (the code, never the docstrings):
        gf_src = (REPO_ROOT / "github_fetch.py").read_text(
            encoding="utf-8")
        code = gf_src.split('"""', 2)[2]
        self.assertNotIn("subprocess", code)
        self.assertNotIn("os.environ", code)
        self.assertNotIn("gh ", code)
        self.assertNotIn("curl", code)

    def test_second_run_is_zero_new(self):
        from starlearner_under_test import harvest as h
        self.plugin.runtime.set_ctx(RecordingCtx(
            settings={"enrich": "rules"}))
        first = h.run_sync({})
        self.assertTrue(first["ok"])
        self.assertEqual(first["new_count"], 4)
        second = h.run_sync({})
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["new_count"], 0)
        self.assertIn("No new stars", second["note"])

    def test_dry_run_touches_nothing(self):
        from starlearner_under_test import harvest as h
        ctx = RecordingCtx(settings={"enrich": "rules"})
        self.plugin.runtime.set_ctx(ctx)
        result = h.run_sync({"dry_run": True})
        self.assertTrue(result.get("ok"), result)
        self.assertTrue(result["dry_run"])
        self.assertEqual(ctx.registered, [])  # nothing registered
        data = self.home / "plugin-data" / "starlearner-nexus"
        self.assertFalse((data / "ledger.json").exists())  # no update
        gen = data / "generated_skills"
        if gen.exists():  # no generation
            self.assertEqual(list(gen.glob("*/*/SKILL.md")), [])

    def test_the_error_model_github_401(self):
        """A 401 from github_fetch = the clean github_401 error JSON
        (R12)."""
        from starlearner_under_test import harvest as h
        from starlearner_under_test import github_fetch as gf

        def fetch_401(max_pages=30):
            raise gf.AuthError(
                "github_401",
                "GitHub rejected the token (expired/revoked).",
                {"fix": "create a fresh token"})
        gf.fetch_starred = fetch_401
        self.plugin.runtime.set_ctx(RecordingCtx(
            settings={"enrich": "rules"}))
        result = h.run_sync({})
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(result["error"], "github_401")
        self.assertIn("fix", result)

    def test_the_error_model_token_not_set(self):
        """A missing token (the REAL fetch path, _secret = None) = the
        clean token_not_set error (R11/R12)."""
        from starlearner_under_test import harvest as h
        from starlearner_under_test import github_fetch as gf
        gf.fetch_starred = self._real_fetch
        gf._secret = lambda name: None
        self.plugin.runtime.set_ctx(RecordingCtx(
            settings={"enrich": "rules"}))
        result = h.run_sync({})
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(result["error"], "token_not_set")
        self.assertIn("hermes plugins install", json.dumps(result))

    def test_single_flight_lock(self):
        from starlearner_under_test import harvest as h
        h._FLIGHT["running"] = True
        h._FLIGHT["started"] = "just now"
        self.addCleanup(lambda: h._release())
        with self.assertRaises(h.SyncBusy):
            h.run_sync({})

    def test_register_generated_skills_false(self):
        from starlearner_under_test import harvest as h
        ctx = RecordingCtx(settings={"enrich": "rules",
                                     "register_generated_skills": False})
        self.plugin.runtime.set_ctx(ctx)
        result = h.run_sync({})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(ctx.registered, [])  # NOT registered
        self.assertEqual(result["registered_skills"], [])
        self.assertEqual(result["skills"]["generated"], 3)  # files written
        self.assertEqual(result["review_rows"], 4)  # reviewable
        # the registry rows exist but registered=0
        db = sqlite3.connect(self.home / "plugin-data" /
                             "starlearner-nexus" / "data.db")
        rows = db.execute("SELECT registered, COUNT(*) FROM skills "
                          "GROUP BY registered").fetchall()
        db.close()
        self.assertEqual(rows, [(0, 3)])

    def test_no_repo_metadata_in_the_sqlite_store(self):
        """The review rows carry the description HEAD only (privacy: the
        full repo objects stay in the engine's data files)."""
        from starlearner_under_test import harvest as h
        self.plugin.runtime.set_ctx(RecordingCtx(
            settings={"enrich": "rules"}))
        h.run_sync({})
        db = sqlite3.connect(self.home / "plugin-data" /
                             "starlearner-nexus" / "data.db")
        heads = [r[0] for r in db.execute("SELECT text_head FROM review")]
        db.close()
        self.assertEqual(len(heads), 4)
        for head in heads:
            self.assertLessEqual(len(head or ""), 160)

    # ── the LLM fusion law (A.4.2) ────────────────────────────────────────
    def test_the_fusion_law(self):
        """keyword hits win; the LLM classifies the uncategorized; a
        confident disagreement = llm_override (review-only); an LLM
        Track-B hit = review-only (never the rules opportunities.json,
        never the ledger)."""
        from starlearner_under_test import harvest as h

        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

        # map: the LLM re-identifies all 4 (B.4: the curation pass). THE
        # MOCK IDENTITIES ARE THE TEST'S LEVERS — their rules verdicts
        # (post-map) were verified against the real engine and pin every
        # fusion branch:
        #   0001 "sample-gpt-local-runner" → rules cat development-tools
        #        (topics 'llm' ×3 lose to 'cli' desc+topics), intA True
        #        (cli), oppB ai-integration ('llm' topics);
        #   0002 "channel-ops-notes" → bitcoin-lightning ('channel'),
        #        intA False, oppB None (the CLEAN row);
        #   0003 "mountain-photo-notes" → uncategorized (the LLM-applied
        #        branch), intA False, oppB None;
        #   0004 "sample-scraper-lib" → development-tools, intA True,
        #        oppB None.
        llm = FakeLLM(results=[
            # map (batch 1: all 4 items)
            FakeResult(parsed={"items": [
                {"id": 9000000001,
                 "name": "sample-gpt-local-runner",
                 "description": "Runs local models behind a clean CLI.",
                 "topics": ["localai", "llm", "cli"]},
                {"id": 9000000002,
                 "name": "channel-ops-notes",
                 "description": "Channel operations notes.",
                 "topics": ["notes", "ops"]},
                {"id": 9000000003,
                 "name": "mountain-photo-notes",
                 "description": "A pleasant photo.",
                 "topics": ["photo", "nature"]},
                {"id": 9000000004,
                 "name": "sample-scraper-lib",
                 "description": "A scraping library.",
                 "topics": ["scraper", "crawler"]},
            ]}),
            # categorize (batch 1)
            FakeResult(parsed={"items": [
                {"id": 9000000001, "category": "ai-ml",
                 "confidence": 0.9},           # DISAGREES (rules said
                                                # development-tools) →
                                                # review-only llm_override
                                                # (the A.4.2 law), keyword
                                                # wins
                {"id": 9000000002, "category": "bitcoin-lightning",
                 "confidence": 0.9},           # agrees (the clean row)
                {"id": 9000000003, "category": "travel-exploration",
                 "confidence": 0.85},          # classifies the
                                                # uncategorized (the rules
                                                # identity hit no keyword)
                                                # → APPLIED
                {"id": 9000000004, "category": "development-tools",
                 "confidence": 0.9},           # agrees
            ]}),
            # assess (batch 1)
            FakeResult(parsed={"items": [
                {"id": 9000000001, "integrate": True,
                 "integrate_rationale": "tool-like",
                 "opportunity": None,
                 "opportunity_rationale": ""},
                {"id": 9000000002, "integrate": False,
                 "integrate_rationale": "notes",
                 "opportunity": None, "opportunity_rationale": ""},
                {"id": 9000000003, "integrate": False,
                 "integrate_rationale": "a photo",
                 "opportunity": "ecommerce",   # LLM-ONLY Track-B hit →
                 "opportunity_rationale": "LLM Track-B candidate"},
                {"id": 9000000004, "integrate": False,
                 "integrate_rationale": "LLM says no (rules said yes)",
                 "opportunity": None, "opportunity_rationale": ""},
            ]}),
        ])
        ctx = RecordingCtx(settings={"enrich": "llm",
                                     "register_generated_skills": True},
                           llm=llm)
        self.plugin.runtime.set_ctx(ctx)
        result = h.run_sync({})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["enrichment"], "llm")

        data = self.home / "plugin-data" / "starlearner-nexus"

        # THE FUSION — keyword hits always win:
        cats = json.loads((data / "categorized_repos.json").read_text())
        by_name = {}
        for cat, repos in cats["categories"].items():
            for r in repos:
                by_name[r["name"]] = cat
        # …the LLM's confident ai-ml verdict on 0001 DISAGREED with the
        # keyword verdict (development-tools, post-map identity) — the
        # keyword won; nothing LLM moved the directory structure:
        self.assertEqual(by_name.get("sample-gpt-local-runner"),
                         "development-tools")   # keyword wins
        # …0002 (the LLM agreed with its keyword verdict):
        self.assertEqual(by_name.get("channel-ops-notes"),
                         "bitcoin-lightning")
        # …and the LLM's classification of the uncategorized photo APPLIED:
        self.assertEqual(by_name.get("mountain-photo-notes"),
                         "travel-exploration")
        self.assertEqual(by_name.get("sample-scraper-lib"),
                         "development-tools")
        self.assertEqual(cats["uncategorized"], [])
        # llm_map: 4 applied (the LLM's identities); llm_categorize:
        # 1 applied (the uncategorized photo) + 1 llm_override (0001):
        self.assertEqual(result["llm_map"]["applied"], 4)
        self.assertEqual(result["llm_categorize"]["applied"], 1)
        self.assertEqual(result["llm_categorize"]["llm_overrides"], 1)

        # THE ASSESS FUSION — the rules opportunities.json is untouched by
        # the LLM (bit-for-bit: Track-B LLM hits are review-only):
        opp = json.loads((data / "opportunities.json").read_text())
        opp_names = [o["name"] for o in opp["opportunities"]]
        opp_domains = [o["domain"] for o in opp["opportunities"]]
        # …0001's RULES Track-B (ai-integration, via its map topics) is
        # the only one there:
        self.assertEqual(opp_names, ["sample-org/sample-gpt"])
        self.assertEqual(opp_domains, ["ai-integration"])
        # …the LLM's Track-B hit on the photo (ecommerce) is NOT there:
        self.assertNotIn("ecommerce", opp_domains)
        # …and the ledger rows carry the RULES verdicts only:
        ledger = json.loads((data / "ledger.json").read_text())
        for row in ledger["items"].values():
            self.assertIn("opportunity", row)

        # THE REVIEW STORE: everything LLM-shaped is there, flagged:
        from starlearner_under_test import skills_out
        review = skills_out.review_rows()
        by_key = {i["id"]: i for i in review["items"]}
        gpt = by_key["id:9000000001"]
        self.assertEqual(gpt["engine"], "llm")
        # the LLM-vs-keyword DISAGREEMENT (it said ai-ml, the keyword said
        # development-tools) ORs into llm_override — the A.4.2
        # review-visibility law:
        self.assertTrue(gpt["llm_override"])
        self.assertEqual(gpt["integrate"], True)  # union (both said yes)
        self.assertEqual(gpt["opportunity"], "ai-integration")  # the RULES
        # the clean row — the LLM agreed on every axis → nothing flagged:
        notes = by_key["id:9000000002"]
        self.assertEqual(notes["category"], "bitcoin-lightning")  # keyword
        self.assertFalse(notes["llm_override"])
        self.assertFalse(notes["integrate"])
        # the LLM Track-B hit (ecommerce) = review-only:
        photo = by_key["id:9000000003"]
        self.assertEqual(photo["category"],
                         "travel-exploration")  # APPLIED
        self.assertTrue(photo["llm_override"])   # the LLM Track-B hit
        self.assertIsNone(photo["opportunity"])  # rules verdict (None)
        # the LLM-false on a rules-true integrate = flagged (fusion floor):
        scraper = by_key["id:9000000004"]
        self.assertTrue(scraper["integrate"])  # keyword floor (union)
        self.assertTrue(scraper["llm_override"])
        # opportunities_only surfaces the flagged + rules-opportunity rows
        # (0002 — the clean row, no rules Track-B — is excluded):
        opp_only = skills_out.review_rows(opportunities_only=True)
        self.assertEqual(opp_only["counts"]["total"], 3)
        self.assertEqual(opp_only["counts"]["llm_flagged"], 3)

        # review-only proof at the ledger level — nothing LLM leaked into
        # the ledger rows (0001 keeps its RULES Track-B; 0003, the LLM
        # Track-B item, has none):
        self.assertEqual(
            ledger["items"]["id:9000000001"]["opportunity"],
            "ai-integration")                    # the RULES verdict
        self.assertIsNone(
            ledger["items"]["id:9000000003"]["opportunity"])
        ledger_opps = [r.get("opportunity")
                       for r in ledger["items"].values()]
        self.assertNotIn("ecommerce", ledger_opps)  # LLM-only → absent

        # the map enrichment worked (the LLM's names):
        self.assertEqual(result["llm_map"]["applied"], 4)
        # registered under the LLM's (collision-resolved) names:
        self.assertEqual(len(result["registered_skills"]), 4)
        self.assertTrue(all(q.startswith("starlearner-nexus:")
                            for q in result["registered_skills"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
