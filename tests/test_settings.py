#!/usr/bin/env python3
"""test_settings.py — the settings law (the skill's step-6 gate; the
starlearner twin of the reapx battery).

Every setting lives under
``plugins.entries.starlearner-nexus.settings.*`` (rendered as the
Desktop Settings form from ``plugin.yaml``'s config_schema), read
through ``runtime.setting`` with the precedence **tool args > settings >
default**, and the defaults are GENERIC (a settings field with a
hardcoded personal default is still a hardcode) and IDENTICAL to the
defaults the code actually uses (plugin.yaml == the code):

  * precedence: args override settings; settings override the default;
    a missing context (no register()) = the default; a raising/None
    ``get_config`` = the default (a settings read never crashes);
  * config_schema: the 5 keys (enrich / llm_max_items / generate_limit /
    max_pages / register_generated_skills), types + choices valid, every
    key carries a label + description (the Settings form), and every
    default is a generic value (no personal paths/names/numbers);
  * code defaults == the schema defaults;
  * tool args override the settings for one run (B.3.1's one-run
    overrides — enrich/generate_limit/max_pages);
  * llm_max_items=0 disables LLM enrichment (the cap's documented
    meaning) — zero ctx.llm calls;
  * requires_env (B.6.1): the ONE declared secret, the rich format
    (name UPPER_SNAKE + description + url + secret) the install prompt
    reads — and NO token anywhere in config_schema (secrets never touch
    config.yaml).
"""
import importlib.util
import json
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
    import yaml  # noqa: F401
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


class StubCtx:
    """get_config only (settings); optionally raising (never a crash)."""

    def __init__(self, settings=None, raise_on_read=False):
        self._settings = settings or {}
        self._raise = raise_on_read

    def get_config(self, key, default=None):
        if self._raise:
            raise RuntimeError("settings backend exploded")
        return self._settings.get(key, default)


class SettingPrecedenceTests(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()
        from starlearner_under_test import runtime
        self.runtime = runtime

    def tearDown(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_args_beat_settings_beat_default(self):
        self.runtime.set_ctx(StubCtx({"enrich": "rules"}))
        self.assertEqual(self.runtime.setting("enrich", "llm"), "rules")
        self.assertEqual(
            self.runtime.setting("enrich", "llm",
                                 {"enrich": "llm"}), "llm")

    def test_no_context_is_the_default(self):
        self.runtime.set_ctx(None)
        self.assertEqual(self.runtime.setting("enrich", "llm"), "llm")

    def test_raising_or_none_get_config_is_the_default(self):
        self.runtime.set_ctx(StubCtx(raise_on_read=True))
        self.assertEqual(self.runtime.setting("max_pages", 30), 30)
        self.runtime.set_ctx(StubCtx({"enrich": None}))
        self.assertEqual(self.runtime.setting("enrich", "llm"), "llm")

    def test_a_settings_read_never_crashes_on_a_bare_ctx(self):
        # the validate probe's recording stub has no get_config at all
        class Bare:
            pass
        self.runtime.set_ctx(Bare())
        self.assertEqual(self.runtime.setting("enrich", "llm"), "llm")


@unittest.skipUnless(HAVE_HERMES, "plugin.yaml yaml + the engine map")
class ConfigSchemaTests(unittest.TestCase):

    SCHEMA_DEFAULTS = {
        "enrich": "llm",
        "llm_max_items": 50,
        "generate_limit": 5,
        "max_pages": 30,
        "register_generated_skills": True,
    }

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        # pin the hermes home (a _Pipeline init touches plugin-data)
        self.tmp = tempfile.TemporaryDirectory(prefix="starlearner-set-")
        self.addCleanup(self.tmp.cleanup)
        from hermes_constants import (reset_hermes_home_override,
                                      set_hermes_home_override)
        home = Path(self.tmp.name) / "hermes-home"
        home.mkdir(parents=True)
        self._token = set_hermes_home_override(home)
        self.addCleanup(lambda: reset_hermes_home_override(self._token))
        self.plugin = _load_plugin()

    def tearDown(self):
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def _schema(self):
        with (REPO_ROOT / "plugin.yaml").open(encoding="utf-8") as f:
            return yaml.safe_load(f)["config_schema"]

    def test_every_key_has_type_label_description_default(self):
        schema = self._schema()
        self.assertEqual(sorted(schema), sorted(self.SCHEMA_DEFAULTS))
        for key, spec in schema.items():
            self.assertIn(key, self.SCHEMA_DEFAULTS, key)
            self.assertIn(spec["type"], ("str", "int", "float", "bool",
                                         "list", "dict", "secret"), key)
            self.assertIn("label", spec, key)
            self.assertTrue(spec["label"], key)
            self.assertIn("description", spec, key)
            self.assertTrue(spec["description"], key)
            self.assertIn("default", spec, key)

    def test_defaults_are_generic(self):
        """A settings field with a hardcoded personal default is still a
        hardcode: no personal paths / names / numbers in any default."""
        schema = self._schema()
        self.assertEqual({k: v["default"] for k, v in schema.items()},
                         self.SCHEMA_DEFAULTS)
        for key, default in self.SCHEMA_DEFAULTS.items():
            if isinstance(default, str):
                self.assertNotIn("/", default, key)
                self.assertNotIn(":", default, key)

    def test_choices(self):
        schema = self._schema()
        self.assertEqual(schema["enrich"]["choices"], ["llm", "rules"])

    def test_no_token_in_config_schema(self):
        """B.6.1: the token is a requires_env secret (the profile's .env,
        host-written) — secrets NEVER touch config.yaml."""
        schema = self._schema()
        for key, spec in schema.items():
            self.assertNotEqual(spec["type"], "secret", key)
            self.assertNotIn("TOKEN", key.upper())

    def test_requires_env_the_one_declared_secret(self):
        """B.6.1: the rich requires_env format — the install prompt (name
        + description + url + secret), UPPER_SNAKE, namespaced so it
        can't collide with a shared GITHUB_TOKEN."""
        import re
        with (REPO_ROOT / "plugin.yaml").open(encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        raw = manifest.get("requires_env") or []
        self.assertEqual(len(raw), 1)
        entry = raw[0]
        self.assertIsInstance(entry, dict)  # the rich format
        self.assertEqual(entry["name"], "STARLEARNER_GITHUB_TOKEN")
        self.assertTrue(re.match(r"^[A-Z0-9_]+$", entry["name"]))
        self.assertTrue(entry.get("secret"))
        self.assertTrue(entry.get("description"))
        self.assertIn("read-only", entry["description"])
        self.assertIn("never sees or stores", entry["description"])
        self.assertIn("docs.github.com", entry.get("url", ""))

    def test_code_defaults_equal_the_schema_defaults(self):
        """plugin.yaml == the code (the defaults the handlers actually
        use when nothing is configured)."""
        from starlearner_under_test import runtime
        runtime.set_ctx(StubCtx({}))
        from starlearner_under_test import harvest
        p = harvest._Pipeline({})
        self.assertEqual(p.enrich, "llm")
        self.assertEqual(p.llm_max_items, 50)
        self.assertEqual(p.generate_limit, 5)
        self.assertEqual(p.max_pages, 30)
        self.assertEqual(p.register_skills, True)
        from starlearner_under_test import tools
        self.assertEqual(tools.runtime.setting("enrich", "llm"), "llm")
        self.assertEqual(tools.runtime.setting("max_pages", 30), 30)


@unittest.skipUnless(HAVE_HERMES, "tools + the arg overrides")
class ToolArgOverrideTests(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        # pin the hermes home (a run touches plugin-data)
        self.tmp = tempfile.TemporaryDirectory(prefix="starlearner-arg-")
        self.addCleanup(self.tmp.cleanup)
        from hermes_constants import (reset_hermes_home_override,
                                      set_hermes_home_override)
        home = Path(self.tmp.name) / "hermes-home"
        home.mkdir(parents=True)
        self._token = set_hermes_home_override(home)
        self.addCleanup(lambda: reset_hermes_home_override(self._token))
        self.plugin = _load_plugin()
        from starlearner_under_test import runtime
        self.runtime = runtime
        from starlearner_under_test import tools
        self.tools = tools
        # the hermetic fetch (no network): the FIXTURE (4 items — the
        # one-run-override test runs a full rules run over it):
        from starlearner_under_test import github_fetch as gf
        self.gf = gf
        self._real_fetch = gf.fetch_starred
        self._real_secret = gf._secret
        gf._secret = lambda name: None
        gf.fetch_starred = lambda max_pages=30: json.loads(
            (REPO_ROOT / "tests" / "fixtures" /
             "starred_repos.sample.json").read_text(encoding="utf-8"))

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

    def _run(self, raw):
        return json.loads(raw)

    def test_tool_args_override_the_settings_for_one_run(self):
        """B.3.1's one-run overrides (args > settings): enrich=rules via
        the arg over an enrich=llm setting = zero ctx.llm calls (the
        setting/arg precedence drives the enrichment engine)."""
        self.runtime.set_ctx(StubCtx({"enrich": "llm"}))

        class Exploding:
            calls = []

            @property
            def llm(self):
                raise RuntimeError("must never be touched")

        class CtxWithLlm(StubCtx):
            def __init__(self):
                super().__init__({"enrich": "llm"})
                self.llm = Exploding()

        self.runtime.set_ctx(CtxWithLlm())
        from starlearner_under_test import harvest as h
        result = h.run_sync({"enrich": "rules"})  # the one-run override
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["enrichment"], "rules")
        self.assertEqual(result["llm"]["map"]["batches"], 0)

    def test_the_missing_token_is_a_clean_error_through_the_tool(self):
        """The R11/R12 guard: no token (the real fetch path) =
        starlearner_sync's clean token_not_set error JSON."""
        self.gf.fetch_starred = self._real_fetch
        self.gf._secret = lambda name: None
        out = self._run(self.tools.sync({}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "token_not_set")

    def test_llm_max_items_zero_disables_the_llm(self):
        """The cap's documented meaning: 0 = zero ctx.llm calls."""
        from starlearner_under_test import llm

        class Exploding:
            @property
            def llm(self):
                raise RuntimeError("must never be touched")

        class Ctx:
            def __init__(self):
                self.llm = Exploding()

            def get_config(self, key, default=None):
                return default

        # llm_max_items=0: _cap returns [] before the enricher is even
        # built → the (exploding) llm property is never reached:
        overrides, stats = llm.enrich_map(
            [{"id": 1, "name": "x", "description": "d",
              "topics": ["t"]}],
            ctx=Ctx(), llm_max_items=0, enrich="llm")
        self.assertEqual(overrides, {})
        self.assertEqual(stats.errors, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
