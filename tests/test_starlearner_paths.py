#!/usr/bin/env python3
"""test_starlearner_paths.py — the data-dir seam (B.2.1 principle 2).
Hermes-free.

The contract: explicit arg > ``STARLEARNER_DATA_DIR`` env >
``<repo>/data`` (the standalone default, unchanged). Zero standalone
behavior change; the plugin passes its plugin-data dir.

Plus the standalone-shape proofs: the seam module never imports the
engine; the engine scripts are argv-pure (categorize/assess/ledger take
paths — nothing resolves a data dir at import time); generate_skills
carries the ``--generate-limit``/``--template`` seams (B.2.2) and nothing
else changed.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import starlearner_paths  # noqa: E402


class ResolveDataDirTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("STARLEARNER_DATA_DIR", None)
        self.addCleanup(lambda: os.environ.pop("STARLEARNER_DATA_DIR",
                                               None))
        if self._env:
            os.environ["STARLEARNER_DATA_DIR"] = self._env

    def test_default_is_repo_data(self):
        self.assertEqual(starlearner_paths.resolve_data_dir(),
                         starlearner_paths.DEFAULT_DATA_DIR)
        self.assertEqual(starlearner_paths.DEFAULT_DATA_DIR,
                         SCRIPTS.parent / "data")

    def test_env_override(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["STARLEARNER_DATA_DIR"] = td
            self.assertEqual(starlearner_paths.resolve_data_dir(),
                             Path(td))

    def test_explicit_arg_beats_env(self):
        with tempfile.TemporaryDirectory() as td1, \
                tempfile.TemporaryDirectory() as td2:
            os.environ["STARLEARNER_DATA_DIR"] = td1
            self.assertEqual(starlearner_paths.resolve_data_dir(td2),
                             Path(td2))

    def test_env_empty_means_default(self):
        os.environ["STARLEARNER_DATA_DIR"] = ""
        self.assertEqual(starlearner_paths.resolve_data_dir(),
                         starlearner_paths.DEFAULT_DATA_DIR)

    def test_data_file(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                starlearner_paths.data_file("ledger.json", td),
                Path(td) / "ledger.json")


class StandaloneShapeTests(unittest.TestCase):
    """The seam never changes the standalone: the seam module imports no
    engine script; the engine scripts are argv-pure (nothing resolves a
    data dir at import time); generate_skills carries the
    generate_limit/template seams (and only those)."""

    def test_starlearner_paths_has_no_engine_imports(self):
        src = (SCRIPTS / "starlearner_paths.py").read_text(
            encoding="utf-8")
        self.assertNotIn("import ledger", src)
        self.assertNotIn("import categorize", src)
        self.assertNotIn("import generate_skills", src)
        self.assertNotIn("import assess_repos", src)

    def test_generate_skills_has_the_seams(self):
        src = (SCRIPTS / "generate_skills.py").read_text(
            encoding="utf-8")
        self.assertIn(
            "def generate_skills(input_file, output_base_dir, "
            "generate_limit=5,\n                    template_name=None):",
            src)
        self.assertIn(")[:generate_limit]", src)  # the hardcoded 5 → param
        self.assertIn("def get_skill_template(category_key, "
                      "template_name=None):", src)
        self.assertIn('if template_name:', src)  # the plugin-mode switch
        # …and the standalone default is UNCHANGED (5, no template):
        self.assertIn("generate_limit=5,", src)

    def test_the_engine_scripts_are_argv_pure(self):
        """categorize/assess/ledger take their paths as argv — nothing
        resolves a data dir at import time (the fetcher writes
        repo-relative data/; the PLUGIN's fetch = github_fetch)."""
        for name in ("categorize_repos.py", "assess_repos.py",
                     "ledger.py"):
            src = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn("starlearner_paths", src)
            self.assertNotIn("STARLEARNER_DATA_DIR", src)

    def test_the_plugin_layer_is_new_files_the_standalone_never_imports(
            self):
        """B.12: the plugin layer (plugin.yaml/__init__/tools/llm/
        skills_out/harvest/github_fetch) is NEW — no engine script
        references it. (verify_installation.py is the one documented
        mention: open item 6's comment explains requests = the PLUGIN
        fetcher (github_fetch.py) vs the standalone's curl — a comment,
        never an import.)"""
        for name in ("categorize_repos.py", "assess_repos.py",
                     "ledger.py", "generate_skills.py",
                     "fetch_starred_repos.sh", "daily_sync.sh",
                     "run_starlearner_3day.sh", "install_skills.py",
                     "usage_ledger.py", "verify_installation.py"):
            src = (SCRIPTS / name).read_text(encoding="utf-8",
                                             errors="replace")
            for plugin_layer in ("import tools", "from tools",
                                 "import llm", "from llm",
                                 "import harvest", "from harvest",
                                 "skills_out",
                                 "plugin_data_dir", "register_tool"):
                self.assertNotIn(plugin_layer, src,
                                 "%s references %r" % (name,
                                                       plugin_layer))
            if name != "verify_installation.py":
                self.assertNotIn("github_fetch", src,
                                 "%s references 'github_fetch'" % name)

    def test_the_standalone_auth_is_standalone_only(self):
        """B.1.3/B.6.3: the gh-CLI/PAT-curl fetcher stays in the shell
        script (standalone); the plugin's fetch = github_fetch.py."""
        sh = (SCRIPTS / "fetch_starred_repos.sh").read_text(
            encoding="utf-8")
        self.assertIn("gh api", sh)          # the gh path (standalone)
        self.assertIn("GITHUB_TOKEN", sh)    # the PAT path (standalone)
        # …and NOTHING in the plugin layer shells out (the code, not the
        # docstrings — which quote the ban):
        gf = (REPO_ROOT / "github_fetch.py").read_text(
            encoding="utf-8")
        code = gf.split('"""', 2)[2] if gf.count('"""') >= 2 else gf
        self.assertNotIn("gh ", code)        # no gh-CLI (R11)
        self.assertNotIn("curl", code)       # no curl
        self.assertNotIn("subprocess", code)  # no shell
        self.assertNotIn("os.environ", code)  # R11: get_secret only
        self.assertIn("api.github.com", code)  # the one endpoint


if __name__ == "__main__":
    unittest.main(verbosity=2)
