"""StarLearner-Nexus — the GitHub-stars → Hermes skills plugin (root package).

``register(ctx)`` is the whole plugin surface Hermes loads (B.2.3). Its
contract, proven by the mission-C probe (scratch/reapx-probe) and
enforced by ``hermes plugins validate`` (the recording-stub probe) and
``doctor`` (the network-blocked runtime):

  * touches ONLY ``ctx.get_config`` / ``ctx.register_*`` / ``ctx.on_unload``;
    NEVER ``ctx.llm`` / ``ctx.state`` / ``ctx.manifest`` (the validate
    probe's recording stub raises AttributeError for that surface — the llm
    facade + the secret_scope token are reached lazily, inside tool
    handlers);
  * no engine import at register time (the engine is imported through
    ``_engine`` lazily, at first tool call) — registration stays cheap, so
    the 10s load deadline, the doctor's socket blocks and the install
    scanner never see a network stack;
  * no network, no subprocess, no writes outside ``plugin_data_dir`` —
    nothing here can hang an unattended start (R12);
  * every optional step (aux task, startup skill scan, blueprint,
    on_unload) is individually guarded — a failure degrades one feature
    (logged), never the load;
  * THE PROBE ANSWER (A.7.4 = B.7): handler-time ``ctx.register_skill``
    IS accepted and the skill is live in the same session
    (``skill_view("starlearner-nexus:<name>")`` resolves it through the
    real agent path) — the sync handlers call it through
    ``runtime.get_ctx()``. The register()-time
    ``skills_out.register_all()`` scan of the plugin_db registry remains
    the guaranteed next-session form (a fresh process re-registers
    everything generated before it).

One tree, two install shapes (B.12): the same repo keeps working as the
standalone skill-pipeline (``bash scripts/daily_sync.sh``, the Makefile
targets, ``tests/run_smoke.sh``, ``scripts/run_starlearner_3day.sh``
cron) — nothing a standalone user runs changes, breaks, or requires
Hermes. The standalone's auth (gh-CLI-or-PAT-curl
``fetch_starred_repos.sh``) stays standalone-only; the plugin's fetch is
``github_fetch.py`` (in-process, ``requires_env`` →
``agent.secret_scope.get_secret`` — B.6).
"""
from __future__ import annotations

from pathlib import Path

from . import runtime, schemas

# Toolset (all three tools; NO check_fn mode gating — B.2.3: requires_env
# install-prompts for the token; the sync handler guards with the clean
# token_not_set error, and the read-only status/review surfaces work
# regardless).
TOOLSET = "starlearner"


def register(ctx) -> None:
    """The plugin's whole registration surface (see the module docstring)."""
    # 0. the captured context: handler-time ctx.register_skill (A.7.4/B.7
    #    probe WORLD A) + settings reads run through it. Set FIRST.
    runtime.set_ctx(ctx)
    log = runtime.log

    # 1. settings (cheap, no network). Never ctx.llm / ctx.state /
    #    ctx.manifest.
    mode_note = ("token not required at register time "
                 "(requires_env install-prompts; starlearner_sync guards)")

    # 2. our own auxiliary LLM task (zero consent: a plugin may only use a
    #    task it registered itself; operators pin it under
    #    auxiliary.starlearner_enricher — it follows the compression slot
    #    until they do). KEY MUST BE ALNUM+UNDERSCORE (a hyphen raises
    #    ValueError and fails the whole load).
    try:
        ctx.register_auxiliary_task(
            runtime.AUX_TASK,
            display_name="StarLearner-Nexus Enricher",
            description="Map/categorize/assess enrichment for the "
                        "StarLearner-Nexus sync (starred-repo metadata → "
                        "skill metadata). Follows your active model until "
                        "you pin one.",
            inherit_from="compression",
            defaults={"timeout": 60},
        )
    except Exception:  # a failed aux task degrades llm enrichment to rules
        log.warning("starlearner-nexus: register_auxiliary_task(%r) "
                    "failed", runtime.AUX_TASK, exc_info=True)

    # 3. the three tools (B.3). starlearner_sync's requires_env surface =
    #    the manifest declaration (install prompt); the handler guards.
    from . import tools

    ctx.register_tool(
        name="starlearner_sync", toolset=TOOLSET, schema=schemas.SYNC,
        handler=tools.sync,
    )
    ctx.register_tool(
        name="starlearner_status", toolset=TOOLSET, schema=schemas.STATUS,
        handler=tools.status,
    )
    ctx.register_tool(
        name="starlearner_review", toolset=TOOLSET, schema=schemas.REVIEW,
        handler=tools.review,
    )

    # 4. generated-skills registration (B.7 = A.7): the startup scan of
    #    the plugin_db registry — THE GUARANTEED FORM (probe run 1 P5 +
    #    run 2: a fresh process re-registers everything generated before
    #    it). The registry, never a walk of the data dir, is the index.
    try:
        from . import skills_out
        n = skills_out.register_all(ctx)
        log.info("starlearner-nexus: %s, %d generated skill(s) "
                 "registered (startup registry scan)", mode_note, n)
    except Exception:
        log.warning("starlearner-nexus: startup skills scan failed",
                    exc_info=True)

    # 5. the one bundled static skill (B.7): the agent always has
    #    starlearner-nexus:index from install.
    bundled = Path(__file__).resolve().parent / "skills"
    try:
        for child in sorted(bundled.iterdir()) if bundled.is_dir() else []:
            if (child / "SKILL.md").is_file():
                try:
                    ctx.register_skill(child.name, child / "SKILL.md",
                                       "StarLearner-Nexus index: what the "
                                       "plugin generated + how to open it")
                except Exception:
                    log.warning("starlearner-nexus: bundled skill %r "
                                "failed", child.name, exc_info=True)
    except Exception:
        log.warning("starlearner-nexus: bundled skills scan failed",
                    exc_info=True)

    # 6. the engine-module eviction (P3): the plugin layer imports the
    #    engine under its own namespace (the loader evicts that on
    #    reload), and _engine restores sys.path after every load (the R09
    #    no-shadow law) — nothing of the plugin ever stays on the path.
    try:
        ctx.on_unload(runtime.run_unload)
    except Exception:
        log.warning("starlearner-nexus: on_unload registration failed",
                    exc_info=True)

    # 7. the cron-surface replacement for run_starlearner_3day.sh (A.10
    #    gap 8): an Automation Blueprint (keys namespaced
    #    starlearner-nexus:sync; the operator must explicitly schedule it;
    #    jobs outlive the plugin; no manifest capability needed). The
    #    prompt is non-interactive by design (R12).
    try:
        ctx.register_automation_blueprint(
            "sync", title="StarLearner-Nexus sync", category="skills",
            description="Every 3 days: fetch the new GitHub stars, "
                        "assess them, generate + register skills. "
                        "Non-interactive; fails clean (a missing token "
                        "or a rate limit is a reported error).",
            schedule_template="0 5 */3 * *",
            prompt_template="Run a StarLearner-Nexus sync, then "
                            "summarize what was new. Do not ask "
                            "questions; if the sync errors (missing "
                            "token, rate limit), report the error only.",
        )
    except Exception:
        log.warning("starlearner-nexus: automation blueprint registration "
                    "failed", exc_info=True)
