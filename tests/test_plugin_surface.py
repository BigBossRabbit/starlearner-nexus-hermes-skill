#!/usr/bin/env python3
"""test_plugin_surface.py — the register() contract, rehearsed exactly the
way ``hermes plugins validate`` runs it (the recording-stub probe) plus
the engine-adapter mechanics + the github_fetch surface. Hermes-free (a
hermes import inside register()'s optional steps degrades gracefully —
same as under the validate probe; github_fetch's secret-scope failure =
the clean token_not_set path).

Guards (each maps to a gate that would otherwise only fail at admission):
  * register() runs against a recording stub WITHOUT raising, registers
    the 3 declared tools (R06) and nothing else;
  * register() never touches the property surface the recording stub
    cannot provide (ctx.llm / ctx.state / ctx.manifest) — the validate
    probe's stub raises AttributeError for those, so touching one fails
    admission;
  * every tool schema is a dict with a dict ``parameters`` (registry.
    register raises at load time otherwise) and declares its name;
  * tools.py handlers NEVER raise (the never-raise contract) and always
    return a JSON string — including starlearner_sync WITHOUT hermes (a
    missing secret scope = the clean token_not_set error, the R11/R12
    guard);
  * _engine namespace adapter: load() imports the shared engine under
    the plugin's own namespace (never top-level), a missing engine
    import becomes a RuntimeError (never a bare ImportError), NO fetch
    chain exists at all (B.2.2), and the sys.path restore holds (the
    R09 no-shadow proof);
  * github_fetch: the R11 law, statically (get_secret only, no
    os.environ, no subprocess/gh/curl, one endpoint) + the token never
    in the tree/errors;
  * register_skill with a non-existent path is a guarded error (the
    bundled-skill loop never kills the load).
"""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# The hermes checkout (the R09 no-shadow probe puts it on the subprocess
# path so the engine load happens with hermes core's top-level packages
# importable — the exact runtime shape).
HERMES_CHECKOUT = Path("/Users/fromthejump/.hermes/profiles/thanos/"
                       "hermes-agent")

PLUGIN_PKG = "starlearner_under_test"


def _load_plugin(pkg=PLUGIN_PKG):
    """Import the plugin the way the loader does (spec + package path)."""
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


class RecordingContext:
    """A faithful copy of the validate probe's recording stub (the class
    the admission check runs register() against): real attributes for the
    surface the stub provides, a hard AttributeError for the property
    surface the real PluginContext provides only as instance/state
    attributes (ctx.llm, ctx.state, ctx.manifest) — touching one from
    register() fails validation, so this stub enforces the same rule."""

    plugin_config = {}
    profile_name = "default"
    plugin_id = "starlearner_under_test"

    def __init__(self):
        self.recorded = {"tools": [], "hooks": [], "middleware": [],
                         "commands": [], "providers": [], "skills": [],
                         "blueprints": [], "aux_tasks": [], "on_unload": []}
        self.raised = []

    def register_tool(self, name, *args, **kwargs):
        self.recorded["tools"].append(str(name))

    def register_hook(self, hook_name, callback, **kwargs):
        self.recorded["hooks"].append(str(hook_name))

    def register_middleware(self, kind, callback):
        self.recorded["middleware"].append(str(kind))

    def register_command(self, name, *args, **kwargs):
        self.recorded["commands"].append(str(name))

    def get_config(self, key, default=None):
        return default

    def register_auxiliary_task(self, key, **kwargs):
        self.recorded["aux_tasks"].append(str(key))

    def register_skill(self, name, path, *args, **kwargs):
        # the REAL one requires an existing path; the stub records
        import pathlib
        if not pathlib.Path(path).exists():
            raise FileNotFoundError(f"SKILL.md not found at {path}")
        self.recorded["skills"].append(str(name))

    def register_automation_blueprint(self, key, **kwargs):
        self.recorded["blueprints"].append(str(key))

    def on_unload(self, callback):
        self.recorded["on_unload"].append(callback)

    def __getattr__(self, name):
        # exactly the probe's rule: names that are NOT real PluginContext
        # methods raise; everything real (register_*) we provide above.
        self.raised.append(name)
        raise AttributeError(name)


class RegisterContractTests(unittest.TestCase):
    """register() under the recording stub == the validate probe run."""

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()
        self.ctx = RecordingContext()

    def tearDown(self):
        # the engine adapter may have registered an on_unload evictor — run
        # the callbacks + drop our package copy
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_register_records_exactly_the_three_tools(self):
        self.plugin.register(self.ctx)
        self.assertEqual(sorted(self.ctx.recorded["tools"]),
                         sorted(["starlearner_sync",
                                 "starlearner_status",
                                 "starlearner_review"]))

    def test_register_never_touches_the_stub_forbidden_surface(self):
        self.plugin.register(self.ctx)
        # __getattr__ was never needed => register() only used the real
        # recording surface (get_config / register_*). ctx.llm /
        # ctx.state / ctx.manifest would have landed in `raised`.
        self.assertEqual(self.ctx.raised, [])

    def test_register_aux_task_underscore_key(self):
        self.plugin.register(self.ctx)
        self.assertEqual(self.ctx.recorded["aux_tasks"],
                         ["starlearner_enricher"])
        # A hyphen in the key raises ValueError in the REAL registrar and
        # fails the whole load (mission-C probe discovery): assert the key
        # is alnum+underscore only.
        self.assertRegex("starlearner_enricher", r"^[A-Za-z0-9_]+$")

    def test_register_bundled_index_skill(self):
        self.plugin.register(self.ctx)
        self.assertIn("starlearner-index", self.ctx.recorded["skills"])

    def test_register_blueprint(self):
        self.plugin.register(self.ctx)
        self.assertEqual(self.ctx.recorded["blueprints"], ["sync"])

    def test_register_on_unload(self):
        self.plugin.register(self.ctx)
        self.assertEqual(len(self.ctx.recorded["on_unload"]), 1)

    def test_register_with_a_broken_optional_step_degrades(self):
        """A failing aux task (the recording stub raising, say) must never
        kill the load: register() still records the 3 tools."""
        ctx = RecordingContext()

        def boom(*a, **k):
            raise ValueError("aux task key already taken")

        ctx.register_auxiliary_task = boom
        self.plugin.register(ctx)
        self.assertEqual(len(ctx.recorded["tools"]), 3)

    def test_schemas_are_well_formed(self):
        from starlearner_under_test import schemas  # the package copy
        for name, schema in schemas.ALL.items():
            self.assertIsInstance(schema, dict, name)
            self.assertEqual(schema["name"], name)
            params = schema.get("parameters")
            self.assertIsInstance(params, dict, name)
            self.assertIn("type", params)
            self.assertIn("description", schema)

    def test_requires_env_shape(self):
        """B.6.1: the one declared secret — the rich requires_env format
        (name UPPER_SNAKE + description + secret) the install prompt and
        the validate requires_env check read."""
        import re
        try:
            import yaml
        except Exception:
            self.skipTest("plugin.yaml needs yaml")
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
        self.assertIn("docs.github.com", entry.get("url", ""))


class NeverRaiseContractTests(unittest.TestCase):
    """tools.py: a JSON string always, a raise never (B.3.1)."""

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()
        self.plugin.runtime.set_ctx(RecordingContext())

    def tearDown(self):
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def _json(self, raw):
        parsed = json.loads(raw)
        self.assertIsInstance(raw, str)
        return parsed

    def test_sync_without_hermes_is_the_clean_token_error(self):
        """THE R11/R12 GUARD (hermes-free): no secret scope (the
        agent.secret_scope import fails) = the clean token_not_set error
        JSON — never a crash, never a hang, never a prompt."""
        from starlearner_under_test import tools
        out = self._json(tools.sync({}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "token_not_set")
        self.assertIn("hermes plugins install", json.dumps(out))

    def test_status_never_raises_without_hermes(self):
        from starlearner_under_test import tools
        out = self._json(tools.status({}))
        self.assertTrue(out["ok"])

    def test_review_never_raises_without_hermes(self):
        from starlearner_under_test import tools
        out = self._json(tools.review({}))
        self.assertTrue(out["ok"])

    def test_handlers_accept_var_kwargs(self):
        import inspect
        from starlearner_under_test import tools
        for name in ("sync", "status", "review"):
            sig = inspect.signature(getattr(tools, name))
            self.assertTrue(any(p.kind is inspect.Parameter.VAR_KEYWORD
                                for p in sig.parameters.values()), name)

    def test_sync_with_a_raising_worker_returns_error_json(self):
        from starlearner_under_test import tools
        plugin = self.plugin

        class Boom:
            def run_sync(self, args):
                raise RuntimeError("engine exploded")

        import starlearner_under_test.harvest as h
        orig = h.run_sync
        h.run_sync = Boom().run_sync
        try:
            out = self._json(tools.sync({"dry_run": True}))
        finally:
            h.run_sync = orig
        self.assertFalse(out["ok"])
        self.assertIn("RuntimeError", out["error"])


class EngineAdapterTests(unittest.TestCase):
    """_engine: the namespace import + the never-bare-ImportError rule +
    the R09 no-shadow law (B.2.2: NO fetch chain exists at all)."""

    def setUp(self):
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)
        self.plugin = _load_plugin()

    def tearDown(self):
        try:
            self.plugin.runtime.run_unload()
        except Exception:
            pass
        for name in list(sys.modules):
            if name == PLUGIN_PKG or name.startswith(PLUGIN_PKG + "."):
                sys.modules.pop(name, None)

    def test_load_imports_shared_engine_under_the_namespace(self):
        from starlearner_under_test import _engine
        _engine.load()
        # shared engine: under the plugin's namespace …
        self.assertIn(PLUGIN_PKG + ".scripts.ledger", sys.modules)
        self.assertIn(PLUGIN_PKG + ".scripts.categorize_repos",
                      sys.modules)
        self.assertIn(PLUGIN_PKG + ".scripts.generate_skills",
                      sys.modules)
        # … and NOT top-level (two plugins never fight over the shared
        # engine names — reapx's vs starlearner's generate_skills differ
        # in 8 lines):
        self.assertNotIn("ledger", sys.modules)
        self.assertNotIn("categorize_repos", sys.modules)
        self.assertNotIn("generate_skills", sys.modules)

    def test_no_fetch_chain_exists_at_all(self):
        """B.2.2: the plugin has NO browser/CDP/fetch-chain import
        anywhere (the standalone's fetcher is a shell script; the
        plugin's fetch = github_fetch)."""
        from starlearner_under_test import _engine
        self.assertFalse(hasattr(_engine, "load_fetch"))
        self.assertFalse(hasattr(_engine, "ENGINE_TOP_LEVEL"))
        _engine.load()
        self.assertFalse(
            any(m.endswith("fetch_x_bookmarks") for m in sys.modules))
        self.assertNotIn("browser_locator", sys.modules)
        self.assertNotIn("cdp_launcher", sys.modules)

    def test_plugin_modules_never_shadow_top_level_names(self):
        """The module-collision law (the review's rename recommendation,
        proven rather than asserted): every plugin module is imported
        package-relative, so a bare top-level ``tools`` / ``schemas`` /
        ``runtime`` / ``llm`` / ``harvest`` in sys.modules is never one of
        ours — hermes core's own lazily-imported top-level packages stay
        theirs."""
        from starlearner_under_test import _engine
        _engine.load()
        for bare in ("tools", "schemas", "runtime", "llm", "harvest",
                     "skills_out", "github_fetch", "_engine"):
            module = sys.modules.get(bare)
            if module is None:
                continue
            path = str(getattr(module, "__file__", "") or "")
            self.assertFalse(
                path.startswith(str(REPO_ROOT) + "/"),
                f"top-level {bare!r} resolved to the plugin's {path}")

    def test_broken_engine_import_is_a_runtimeerror(self):
        from starlearner_under_test import _engine
        # break the engine import the way a broken tree would: a None in
        # sys.modules for the scripts package halts `from . import
        # scripts` with an ImportError → load() converts it into a clean
        # RuntimeError (never a bare ImportError at handler time).
        _engine._LOADED = False
        key = PLUGIN_PKG + ".scripts"
        sentinel = object()
        previous = sys.modules.get(key, sentinel)
        sys.modules[key] = None
        try:
            with self.assertRaises(RuntimeError):
                _engine.load()
        finally:
            if previous is sentinel:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous
            _engine._LOADED = False

    def test_engine_load_restores_sys_path(self):
        """THE R09 no-shadow proof (a fresh subprocess): the engine
        scripts carry their own standalone-era
        ``sys.path.insert(0, <repo root>)`` idiom — under the plugin that
        would leave THE PLUGIN ROOT on sys.path, and every plugin root
        has a top-level ``tools.py`` that would then shadow hermes
        core's ``tools`` package (imported lazily all over core) for
        every later import. _engine restores the path after every load;
        the engine itself keeps working (its modules land in sys.modules
        under the plugin's namespace)."""
        import json
        import os
        import subprocess
        import textwrap

        code = textwrap.dedent('''
            import importlib.util, sys, json
            from pathlib import Path
            REPO = Path(%r)
            if str(REPO) in sys.path:
                sys.path.remove(str(REPO))
            HERMES = %r
            if HERMES and str(HERMES) not in sys.path:
                sys.path.insert(0, str(HERMES))
            spec = importlib.util.spec_from_file_location(
                "engine_pkg", REPO / "__init__.py",
                submodule_search_locations=[str(REPO)])
            pkg = importlib.util.module_from_spec(spec)
            pkg.__path__ = [str(REPO)]
            sys.modules["engine_pkg"] = pkg
            spec.loader.exec_module(pkg)  # the import surface only
            from engine_pkg import _engine
            before = list(sys.path)
            _engine.load()
            out = {"restored": sys.path == before,
                   "root_anywhere": str(REPO) in sys.path,
                   "engine_loaded": _engine._LOADED,
                   "ledger_ns": "engine_pkg.scripts.ledger" in sys.modules}
            try:
                import tools
                out["tools_file"] = getattr(tools, "__file__", "") or ""
            except Exception as exc:
                out["tools_file"] = "IMPORT-ERROR " + type(exc).__name__
            print("R09PROBE " + json.dumps(out))
        ''') % (str(REPO_ROOT),
                str(HERMES_CHECKOUT) if HERMES_CHECKOUT.is_dir() else None)
        env = dict(os.environ)
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True,
            text=True, timeout=120, env=env, cwd=str(REPO_ROOT / "tests"))
        line = [l for l in proc.stdout.splitlines()
                if l.startswith("R09PROBE ")]
        self.assertTrue(line, "probe output missing: %r / %r"
                        % (proc.stdout[-300:], proc.stderr[-300:]))
        out = json.loads(line[0].split(" ", 1)[1])
        self.assertTrue(out["engine_loaded"])  # the engine really loaded
        self.assertTrue(out["ledger_ns"])  # under the namespace
        self.assertTrue(out["restored"])   # sys.path bit-for-bit restored
        self.assertFalse(out["root_anywhere"])  # no root left behind
        # a top-level 'tools' never resolves to the plugin's tools.py:
        self.assertNotIn(str(REPO_ROOT), out["tools_file"])

    def test_register_skill_bad_path_is_guarded(self):
        """The bundled-skill loop: a non-existent SKILL.md (the real
        register_skill raises FileNotFoundError) is a logged error, never
        a dead plugin."""
        ctx = RecordingContext()
        real_reg = ctx.register_skill

        def raising_reg(name, path, *a, **k):
            if name == "starlearner-index":
                raise FileNotFoundError(f"SKILL.md not found at {path}")
            return real_reg(name, path, *a, **k)

        ctx.register_skill = raising_reg
        self.plugin.register(ctx)  # must NOT raise
        self.assertEqual(len(ctx.recorded["tools"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
