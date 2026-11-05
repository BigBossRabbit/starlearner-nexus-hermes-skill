#!/usr/bin/env python3
"""test_skills_out.py — the generated-skills subsystem (spec B.7 = A.7).

The money-shot layer's own law, unit-pinned (the driver tests cover the
end-to-end flows; these pin the A.7.2 mechanics):

  * naming — ``safe_skill_name`` (the generator's slug rules) +
    ``item_source_key`` (the one-identity law: id:/name:/hash: — a GitHub
star's key);
  * the collision law (A.7.2.2-3) — same source_key = idempotent (no
    rename); same skill_name + a different source_key = the deterministic
    sha256(source_key)[:6] suffix (resolved BEFORE generate; never
    overwrite, never drop), including against pre-existing REGISTRY rows;
  * write_and_register — the review rows' construction (the A.4.2
    review-visibility law: llm_a AND llm_c divergences both OR into
    llm_override; LLM Track-B stays review-only) + the registry rows +
    handler-time register_skill (the probe's WORLD-A mechanism) +
    ``register_generated_skills: false`` (files + rows, no calls);
  * register_all — the startup scan: the registry (never a walk of the
    data dir) is the index; registered=0 rows are skipped; orphaned files
    on disk are not registered;
  * status / review_rows — pending_review = the llm_override rows;
    llm_flagged = llm_override (not engine); the filters.

Everything runs under a pinned tmp HERMES_HOME (plugin-data/plugin_db need
hermes; same skip pattern as the driver tests).
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PLUGIN_PKG = "starlearner_under_test"
HERMES_CHECKOUT = Path("/Users/fromthejump/.hermes/profiles/thanos/"
                       "hermes-agent")

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


class RecordingCtx:
    """The mock PluginContext (register_skill records; get_config)."""

    def __init__(self, settings=None):
        self._settings = settings or {}
        self.registered = []

    def get_config(self, key, default=None):
        return self._settings.get(key, default)

    def register_skill(self, name, path, *args, **kwargs):
        self.registered.append((str(name), str(path)))


@unittest.skipUnless(HAVE_HERMES,
                     "plugin-data/plugin_db need hermes (run under the "
                     "hermes venv)")
class SkillsOutTests(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.tmp = tempfile.TemporaryDirectory(prefix="starlearner-skillsout-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "hermes-home"
        self.home.mkdir(parents=True)
        from hermes_constants import (get_hermes_home,
                                      reset_hermes_home_override,
                                      set_hermes_home_override)
        self._token = set_hermes_home_override(self.home)
        self.addCleanup(lambda: reset_hermes_home_override(self._token))
        self.plugin = _load_plugin()
        from starlearner_under_test import skills_out
        self.so = skills_out

    def tearDown(self):
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    # ── naming + the identity law ────────────────────────────────────────
    def test_safe_skill_name(self):
        self.assertEqual(self.so.safe_skill_name("Sample-GPT"), "sample-gpt")
        self.assertEqual(self.so.safe_skill_name("a b c"), "a-b-c")
        # a non-letter lead gets the skill- prefix (the engine's rule)
        self.assertEqual(self.so.safe_skill_name("123-numbers"),
                         "skill-123-numbers")
        self.assertEqual(self.so.safe_skill_name(""), "unknown-skill")
        self.assertEqual(self.so.safe_skill_name(None), "unknown-skill")
        self.assertLessEqual(len(self.so.safe_skill_name("x" * 300)), 96)
        # register-safe: [a-zA-Z0-9_-]+ (no ':')
        import re
        for name in ("Sample-GPT", "a b c", "123", "x" * 300):
            self.assertRegex(self.so.safe_skill_name(name),
                             r"^[a-zA-Z0-9_-]+$")

    def test_item_source_key_the_one_identity_law(self):
        self.assertEqual(self.so.item_source_key(
            {"id": 42}), "id:42")
        self.assertEqual(self.so.item_source_key(
            {"id": "42", "name": "x"}), "id:42")
        self.assertEqual(self.so.item_source_key(
            {"name": "x"}), "name:x")
        key = self.so.item_source_key({"blob": True})
        self.assertTrue(key.startswith("hash:"))
        self.assertEqual(len(key), len("hash:") + 16)

    # ── the collision law (A.7.2) ────────────────────────────────────────
    def _blank_db(self):
        db = self.so._db()
        self.so._init_db(db)
        return db

    def test_same_source_key_is_idempotent(self):
        db = self._blank_db()
        items = [{"id": 1, "name": "same-name"}]
        renames = self.so.resolve_collisions(items, db)
        self.assertEqual(renames, {})  # rule 2: no rename
        self.assertEqual(items[0]["name"], "same-name")
        db.close()

    def test_same_name_different_key_gets_the_hash_suffix(self):
        import hashlib
        db = self._blank_db()
        items = [{"id": 1, "name": "collide-me"},
                 {"id": 2, "name": "collide-me"}]
        renames = self.so.resolve_collisions(items, db)
        # rule 3: the SECOND registration is the one that gets the
        # deterministic suffix (never overwrite, never drop):
        self.assertEqual(items[0]["name"], "collide-me")
        expected = "collide-me-" + hashlib.sha256(
            b"id:2").hexdigest()[:6]
        self.assertEqual(items[1]["name"], expected)
        self.assertEqual(renames,
                         {"id:2": {"from": "collide-me",
                                      "to": expected}})
        db.close()

    def test_registry_rows_win_over_new_names(self):
        # a previous run recorded "taken" under a different source key:
        db = self._blank_db()
        db.execute("INSERT INTO skills (skill_name, source_key, category, "
                   "first_seen, last_seen, rel_path, frontmatter_name, "
                   "registered) VALUES ('taken', 'id:99', 'ai-ml', "
                   "'t', 't', 'ai-ml/taken/SKILL.md', 'taken', 1)")
        db.commit()
        items = [{"id": 7, "name": "taken"}]
        renames = self.so.resolve_collisions(items, db)
        self.assertTrue(items[0]["name"].startswith("taken-"))
        self.assertIn("id:7", renames)
        # …but the SAME source key re-registers idempotently:
        items2 = [{"id": 99, "name": "taken"}]
        self.assertEqual(self.so.resolve_collisions(items2, db), {})
        db.close()

    # ── write_and_register (the review rows + the registry) ──────────────
    def _gen_file(self, category, skill_name):
        root = self.so.gen_root()
        skill_md = root / category / skill_name / "SKILL.md"
        skill_md.parent.mkdir(parents=True, exist_ok=True)
        skill_md.write_text(
            "---\nname: %s\ndescription: a test skill\n---\nbody\n"
            % skill_name, encoding="utf-8")
        return skill_md

    def _item(self, bid, name, desc="a test item"):
        # the starred-repo shape (id = the GitHub id).
        return {"id": int(bid), "name": name, "description": desc,
                "topics": ["t"], "owner": {"login": "sample-org"},
                "html_url": "https://github.com/sample-org/%s" % name,
                "stargazers_count": 1}

    def test_write_and_register_and_the_a4_2_review_law(self):
        ctx = RecordingCtx()
        self._gen_file("ai-ml", "llm-named-skill")
        self._gen_file("dev-tools", "rules-named-skill")
        self._gen_file("travel", "photo-skill")
        items = [self._item("1", "llm-named-skill"),
                 self._item("2", "rules-named-skill"),
                 self._item("3", "photo-skill")]
        gen_stats = {"skills_generated": 3, "skills_unchanged": 0}
        # llm_map: item 1 re-identified (the LLM's name won);
        # llm_cat: item 1 = a confident DISAGREEMENT (never applied);
        #          item 3 = an APPLIED verdict (the uncategorized case);
        # llm_assess: item 2 = LLM-false on a rules-true (Track A);
        #             item 3 = an LLM-ONLY Track-B hit.
        out = self.so.write_and_register(
            ctx=ctx, items=items,
            categories={"id:1": "ai-ml", "id:2": "dev-tools",
                        "id:3": "travel"},
            assess_data={
                "_by_key": {"id:1": {"integrated": True,
                                        "opportunity": None},
                            "id:2": {"integrated": True,
                                        "opportunity": None},
                            "id:3": {"integrated": False,
                                        "opportunity": None}}},
            llm_map={"id:1": {"name": "llm-named-skill",
                                 "description": "d", "topics": ["t"]}},
            llm_cat={"id:1": {"category": "bitcoin-lightning",
                                 "confidence": 1.0, "_applied": False,
                                 "_llm_override": 1},
                     "id:3": {"category": "travel",
                                 "confidence": 0.9, "_applied": True,
                                 "_llm_override": 0}},
            llm_assess={"id:2": {"integrate": False,
                                    "integrate_rationale": "no",
                                    "opportunity": None,
                                    "opportunity_rationale": ""},
                        "id:3": {"integrate": False,
                                    "integrate_rationale": "photo",
                                    "opportunity": "ecommerce",
                                    "opportunity_rationale": "LLM B"}},
            gen_stats=gen_stats, register_skills=True)
        self.assertEqual(out["registered"], ["starlearner-nexus:llm-named-skill",
                                             "starlearner-nexus:rules-named-skill",
                                             "starlearner-nexus:photo-skill"])
        self.assertEqual(out["review_rows"], 3)
        self.assertEqual(out["errors"], [])
        self.assertEqual(len(ctx.registered), 3)
        # THE A.4.2 REVIEW-VISIBILITY LAW (pinned at the unit level):
        rows = self.so.review_rows()
        by_key = {i["id"]: i for i in rows["items"]}
        # item 1: a categorize DISAGREEMENT ORs into llm_override (the law
        # this fix closed — pre-fix this row was llm_override=0) — and
        # with NO assess verdict + nothing applied, engine stays "rules":
        # the flag is the divergence marker, the engine is what was
        # actually APPLIED:
        self.assertTrue(by_key["id:1"]["llm_override"])
        self.assertEqual(by_key["id:1"]["engine"], "rules")
        self.assertTrue(by_key["id:1"]["integrate"])  # rules floor
        # item 2: the LLM-false-on-rules-true = flagged:
        self.assertTrue(by_key["id:2"]["llm_override"])
        self.assertTrue(by_key["id:2"]["integrate"])  # keyword floor
        # item 3: the LLM-ONLY Track-B hit = review-only …
        self.assertTrue(by_key["id:3"]["llm_override"])
        self.assertIsNone(by_key["id:3"]["opportunity"])
        # …and llm_flagged counts the FLAGS (not engine=llm rows):
        self.assertEqual(rows["counts"]["llm_flagged"], 3)
        # LLM Track-B never touches the opportunity column:
        rows = self.so.review_rows(opportunities_only=True)
        self.assertEqual(rows["counts"]["total"], 3)

    def test_register_generated_skills_false(self):
        ctx = RecordingCtx()
        self._gen_file("ai-ml", "unregistered-skill")
        out = self.so.write_and_register(
            ctx=ctx, items=[self._item("1", "unregistered-skill")],
            categories={"id:1": "ai-ml"},
            assess_data={"_by_key": {}}, llm_map={}, llm_cat={},
            llm_assess={}, gen_stats={"skills_generated": 1},
            register_skills=False)
        self.assertEqual(out["registered"], [])
        self.assertEqual(ctx.registered, [])  # NEVER called
        self.assertEqual(out["review_rows"], 1)  # still reviewable
        db = sqlite3.connect(self.home / "plugin-data" /
                             "starlearner-nexus" / "data.db")
        rows = db.execute("SELECT registered, COUNT(*) FROM skills "
                          "GROUP BY registered").fetchall()
        db.close()
        self.assertEqual(rows, [(0, 1)])

    def test_items_without_a_generated_file_get_review_rows_only(self):
        ctx = RecordingCtx()
        out = self.so.write_and_register(
            ctx=ctx, items=[self._item("9", "never-generated")],
            categories={"id:9": "uncategorized"},
            assess_data={"_by_key": {}}, llm_map={}, llm_cat={},
            llm_assess={}, gen_stats={}, register_skills=True)
        self.assertEqual(out["registered"], [])
        self.assertEqual(out["review_rows"], 1)
        self.assertEqual(ctx.registered, [])

    # ── register_all (the startup scan) ──────────────────────────────────
    def test_register_all_the_registry_is_the_index(self):
        ctx = RecordingCtx()
        # in the registry, file on disk → registered:
        self._gen_file("ai-ml", "good-skill")
        # in the registry, file MISSING (drifted) → not registered:
        # (rel_path points nowhere)
        # NOT in the registry, file on disk (orphan) → not registered:
        self._gen_file("ai-ml", "orphan-skill")
        db = self.so._db()
        self.so._init_db(db)
        db.execute("INSERT INTO skills (skill_name, source_key, category, "
                   "first_seen, last_seen, rel_path, frontmatter_name, "
                   "registered) VALUES ('good-skill', 'id:1', 'ai-ml', "
                   "'t', 't', 'ai-ml/good-skill/SKILL.md', 'good-skill', "
                   "1)")
        db.execute("INSERT INTO skills (skill_name, source_key, category, "
                   "first_seen, last_seen, rel_path, frontmatter_name, "
                   "registered) VALUES ('drifted', 'id:2', 'ai-ml', "
                   "'t', 't', 'ai-ml/DRIFTED/SKILL.md', 'drifted', 1)")
        # registered=0 → skipped (register_generated_skills=false rows):
        db.execute("INSERT INTO skills (skill_name, source_key, category, "
                   "first_seen, last_seen, rel_path, frontmatter_name, "
                   "registered) VALUES ('muted', 'id:3', 'ai-ml', "
                   "'t', 't', 'ai-ml/muted/SKILL.md', 'muted', 0)")
        self._gen_file("ai-ml", "muted")
        db.commit()
        db.close()
        n = self.so.register_all(ctx)
        self.assertEqual(n, 1)  # good-skill only
        self.assertEqual([name for name, _ in ctx.registered],
                         ["good-skill"])

    # ── status ────────────────────────────────────────────────────────────
    def test_status_counts_pending_review(self):
        ctx = RecordingCtx()
        self._gen_file("ai-ml", "flagged-skill")
        self._gen_file("ai-ml", "clean-skill")
        self.so.write_and_register(
            ctx=ctx,
            items=[self._item("1", "flagged-skill"),
                   self._item("2", "clean-skill")],
            categories={"id:1": "ai-ml", "id:2": "ai-ml"},
            assess_data={"_by_key": {"id:1": {"integrated": True,
                                                 "opportunity": None}}},
            llm_map={}, llm_cat={"id:1": {"category": "x",
                                             "confidence": 1.0,
                                             "_applied": False,
                                             "_llm_override": 1}},
            llm_assess={}, gen_stats={"skills_generated": 2},
            register_skills=True)
        status = self.so.status()
        self.assertEqual(status["count"], 2)
        self.assertEqual(sorted(status["registered"]),
                         ["starlearner-nexus:clean-skill",
                          "starlearner-nexus:flagged-skill"])
        self.assertEqual(status["pending_review"], 1)  # the llm_override


if __name__ == "__main__":
    unittest.main(verbosity=2)
