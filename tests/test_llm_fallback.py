#!/usr/bin/env python3
"""test_llm_fallback.py — the ctx.llm enrichment layer's failure law (B.4/A.4.3).

Every no-LLM condition maps to ONE behavior — the rules fallback, never a
failure, never a hang — and the enrichment functions NEVER raise:

  * no llm surface (a hermes without it) → rules ("disabled");
  * ``enrich: rules`` → the LLM is never even called (zero-call proof);
  * ``llm_max_items=0`` (disabled) → zero calls;
  * provider errors / timeouts (any Exception) → error CLASS only + rules;
  * ``PluginLlmTrustError`` (a PermissionError subclass) → same (we never
    pass an override arg, so this is structurally unreachable — the mock
    proves the catch-anyway);
  * ``complete_structured`` raising ValueError (empty input /
    schema-validation failure) → batch dropped + rules;
  * non-JSON output (content_type="text" / parsed None) → rules;
  * a JSON response that fails OUR per-item validation (a bad name, a
    missing item) → that item falls back, others survive;
  * ZERO override arguments are ever passed (the trust-gate-safety proof:
    assert the exact kwargs complete_structured received).

The fusion rules (keyword wins / llm classifies uncategorized /
llm_override recording / review-only Track B) are tested end-to-end in
test_sync_driver (they live in the pipeline, not in llm.py).
"""
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PLUGIN_PKG = "starlearner_under_test"


def _load_plugin(pkg=PLUGIN_PKG):
    if pkg in sys.modules:
        return sys.modules[pkg]
    spec = importlib_util_spec = __import__("importlib.util",
                                            fromlist=["util"]).spec_from_file_location(
        pkg, REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)])
    module = __import__("importlib.util", fromlist=["util"]).module_from_spec(
        spec)
    module.__path__ = [str(REPO_ROOT)]
    sys.modules[pkg] = module
    spec.loader.exec_module(module)
    return module


class FakeResult:
    """A PluginLlmStructuredResult lookalike."""

    def __init__(self, parsed=None, content_type="json"):
        self.parsed = parsed
        self.content_type = content_type


class FakeLLM:
    """A mock ctx.llm: records the exact kwargs it was called with (the
    zero-override proof) and returns canned results / raises on demand."""

    def __init__(self, results=None, raise_exc=None):
        self.results = list(results or [])
        self.raise_exc = raise_exc
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.results:
            item = self.results.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return FakeResult(parsed=None, content_type="text")


class FakeCtx:
    """A mock PluginContext: llm via property + get_config."""

    def __init__(self, llm=None, settings=None):
        self._llm = llm
        self._settings = settings or {}

    @property
    def llm(self):
        return self._llm

    def get_config(self, key, default=None):
        return self._settings.get(key, default)


# the starred-repo shape (a fetched GitHub repo object).
ITEMS = [
    {"id": 1, "name": "sample-gpt", "full_name": "sample-org/sample-gpt",
     "description": "a local model runner with a clean cli",
     "topics": ["localai"], "stargazers_count": 3,
     "owner": {"login": "sample-org"}},
    {"id": 2, "name": "great-thread-on-lightning",
     "full_name": "sample-bob/ln-ops",
     "description": "lightning network channel management with lnd",
     "topics": ["bitcoin"], "stargazers_count": 7,
     "owner": {"login": "sample-bob"}},
]


class MapFallbackTests(unittest.TestCase):
    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()

    def tearDown(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_rules_mode_never_calls_the_llm(self):
        from starlearner_under_test import llm
        fake = FakeLLM()
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="rules")
        self.assertEqual(overrides, {})
        self.assertEqual(fake.calls, [])  # ZERO calls (A.4.3)
        self.assertEqual(stats.errors, 0)  # clean zeros, not "disabled"

    def test_llm_max_items_zero_never_calls(self):
        from starlearner_under_test import llm
        fake = FakeLLM()
        llm.enrich_map(ITEMS, ctx=FakeCtx(fake), llm_max_items=0,
                       enrich="llm")
        self.assertEqual(fake.calls, [])

    def test_no_llm_surface_is_rules(self):
        from starlearner_under_test import llm
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(None),
                                          llm_max_items=50, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.errors, 1)
        self.assertEqual(stats.error_kinds, ["disabled"])

    def test_provider_error_is_class_only_plus_rules(self):
        from starlearner_under_test import llm
        fake = FakeLLM(raise_exc=RuntimeError("connect timeout in "
                                              "api.example.internal"))
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.error_kinds, ["RuntimeError"])
        self.assertEqual(stats.errors, 1)  # one batch (≤10 items)

    def test_trust_error_is_caught_too(self):
        """We never pass an override arg, so PluginLlmTrustError is
        structurally unreachable — but IF the host ever raises one, the law
        is still rules-fallback (catch-everything proof)."""
        from starlearner_under_test import llm
        fake = FakeLLM(raise_exc=PermissionError(
            "Plugin 'reapx' cannot override the model"))
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.error_kinds, ["PermissionError"])

    def test_valueerror_batch_dropped(self):
        from starlearner_under_test import llm
        fake = FakeLLM(raise_exc=ValueError(
            "PluginLlmStructuredResult did not match schema"))
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.error_kinds, ["ValueError"])

    def test_not_json_is_rules(self):
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed=None,
                                           content_type="text")])
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.error_kinds, ["not_json"])

    def test_good_map_overrides_apply_and_bad_items_fall_back(self):
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed={
            "items": [
                {"id": 1, "name": "sample-gpt-local-runner",
                 "description": "Runs local models behind a clean CLI.",
                 "topics": ["localai", "llm", "cli"]},
                {"id": 2, "name": "BAD NAME (spaces!)",  # invalid
                 "description": "x", "topics": ["y"]},
                # item 3: missing → falls back
            ]})])
        overrides, stats = llm.enrich_map(ITEMS, ctx=FakeCtx(fake),
                                          llm_max_items=50, enrich="llm")
        self.assertIn("id:1", overrides)
        self.assertEqual(overrides["id:1"]["name"],
                         "sample-gpt-local-runner")
        self.assertNotIn("id:2", overrides)  # invalid name → rules identity
        self.assertIn("invalid_item", stats.error_kinds)

    def test_zero_override_arguments(self):
        """THE trust-gate-safety proof (A.4.1): the exact kwargs
        complete_structured received — request-shaping args + our own task
        only, NEVER provider/model/agent_id/profile."""
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed={"items": []})])
        llm.enrich_map(ITEMS, ctx=FakeCtx(fake), llm_max_items=50,
                       enrich="llm")
        self.assertEqual(len(fake.calls), 1)
        kwargs = fake.calls[0]
        self.assertEqual(sorted(kwargs), sorted(
            ["instructions", "input", "json_schema", "schema_name",
             "purpose", "task", "temperature", "max_tokens", "timeout"]))
        self.assertEqual(kwargs["task"], "starlearner_enricher")  # OUR own task
        self.assertEqual(kwargs["temperature"], 0.0)
        self.assertEqual(kwargs["timeout"], 30)
        # structurally impossible to hit the trust gate:
        for forbidden in ("provider", "model", "agent_id", "profile"):
            self.assertNotIn(forbidden, kwargs)

    def test_never_raises(self):
        """The zero-raise-paths proof: a mock llm that raises everything
        from BaseException classes that could ever escape."""
        from starlearner_under_test import llm

        class Evil:
            @property
            def llm(self):
                raise RuntimeError("property exploded")

        class EvilCtx:
            @property
            def llm(self):
                raise RuntimeError("property exploded")

        for evil_ctx in (EvilCtx(),):
            try:
                llm.enrich_map(ITEMS, ctx=evil_ctx, llm_max_items=50,
                               enrich="llm")
            except Exception as exc:  # pragma: no cover
                self.fail(f"enrich_map raised: {exc!r}")


class CategorizeFallbackTests(unittest.TestCase):
    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()

    def tearDown(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_verdicts_validate_the_category_keys(self):
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed={
            "items": [
                {"id": 1, "category": "ai-ml", "confidence": 0.9},
                {"id": 2, "category": "not-a-key", "confidence": 0.9},
            ]})])
        verdicts, stats = llm.enrich_categorize(ITEMS, ctx=FakeCtx(fake),
                                                llm_max_items=50,
                                                enrich="llm")
        self.assertIn("id:1", verdicts)
        self.assertNotIn("id:2", verdicts)  # invalid category key → rules
        self.assertIn("invalid_item", stats.error_kinds)

    def test_rules_mode_zero_calls(self):
        from starlearner_under_test import llm
        fake = FakeLLM()
        llm.enrich_categorize(ITEMS, ctx=FakeCtx(fake), llm_max_items=50,
                              enrich="rules")
        llm.enrich_assess(ITEMS, ctx=FakeCtx(fake), llm_max_items=50,
                          enrich="rules")
        self.assertEqual(fake.calls, [])


class AssessFallbackTests(unittest.TestCase):
    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()

    def tearDown(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_verdicts_shape(self):
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed={
            "items": [
                {"id": 1, "integrate": True,
                 "integrate_rationale": "tool-like, reusable",
                 "opportunity": "ai-integration",
                 "opportunity_rationale": "agent tooling candidate"},
                {"id": 2, "integrate": False,
                 "integrate_rationale": "a nice photo",
                 "opportunity": None,
                 "opportunity_rationale": ""},
            ]})])
        verdicts, stats = llm.enrich_assess(ITEMS, ctx=FakeCtx(fake),
                                            llm_max_items=50, enrich="llm")
        self.assertEqual(verdicts["id:1"]["integrate"], True)
        self.assertEqual(verdicts["id:1"]["opportunity"],
                         "ai-integration")
        self.assertEqual(verdicts["id:2"]["opportunity"], None)

    def test_bad_integrate_type_falls_back(self):
        from starlearner_under_test import llm
        fake = FakeLLM(results=[FakeResult(parsed={
            "items": [{"id": 1, "integrate": "yes please",
                       "integrate_rationale": "x",
                       "opportunity": None,
                       "opportunity_rationale": ""}]})])
        verdicts, stats = llm.enrich_assess(ITEMS, ctx=FakeCtx(fake),
                                            llm_max_items=50, enrich="llm")
        self.assertEqual(verdicts, {})
        self.assertIn("invalid_item", stats.error_kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
