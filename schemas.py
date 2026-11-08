"""schemas.py — the three registered tool schemas (spec B.3, verbatim).

Every handler returns a JSON string always and never raises (tools.py).
The ``description`` fields are how the model decides when to use a tool.
"""
from __future__ import annotations

SYNC = {
    "name": "starlearner_sync",
    "description": (
        "Fetch the repositories the user has starred on GitHub (read-only, "
        "authenticated with the user's token from the host's secret scope) "
        "and, INCREMENTALLY (a persistent seen-ledger — a repo is never "
        "processed twice): map each NEW starred repo to a skill schema, "
        "categorize it into one of 12 domains, run a two-track assessment "
        "(worth integrating into the user's own makeup / "
        "business-opportunity value), and generate ready-to-load skills "
        "(registered namespaced as starlearner-nexus:<name>, returned in "
        "the result). Use when the user mentions their GitHub stars, "
        "starring repos, or refreshing their skill library from GitHub. "
        "Enrichment engine, LLM item cap and skill registration come from "
        "the plugin settings; the args below are the only per-call knobs "
        "(the caps can only lower the configured ceiling)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "max_pages":      {"type": "integer", "minimum": 1, "maximum": 100,
                               "description": "Fetch fewer star pages this run "
                                              "— min(argument, max_pages "
                                              "setting)."},
            "generate_limit": {"type": "integer", "minimum": 0, "maximum": 25,
                               "description": "Generate at most this many "
                                              "skills per category this run — "
                                              "min(argument, generate_limit "
                                              "setting); 0 = assess-only."},
            "dry_run":        {"type": "boolean", "default": False,
                               "description": "Fetch + diff + enrich only; no "
                                              "generation, no ledger update."},
        },
        "required": [],
    },
}

STATUS = {
    "name": "starlearner_status",
    "description": (
        "Read-only StarLearner-Nexus status: token state, last sync, "
        "ledger counts (total seen / new last run), skills generated + "
        "registered (namespaced names), last two-track assessment counts, "
        "LLM enrichment state (engine used, items, errors), and pending "
        "review items. Use before/after a sync, or whenever the user asks "
        "what StarLearner has done or what skills it gave them."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

REVIEW = {
    "name": "starlearner_review",
    "description": (
        "Review what the last sync produced, item by item: each new "
        "starred repo with its description, category, two-track "
        "assessment (integrate-into-makeup / business-opportunity + "
        "rationale), and the generated skill (namespaced name + "
        "frontmatter head). Supports since/category/opportunities "
        "filters. This is the human-in-the-loop surface of the two-track "
        "assessment — LLM-derived opportunities land here, never silently "
        "in the ledger."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "since":      {"type": "string", "description": "ISO datetime; review items "
                                "first seen after this (default: last run)."},
            "category":   {"type": "string", "description": "One of the 12 domain keys."},
            "opportunities_only": {"type": "boolean", "default": False},
            "include_skill_md":   {"type": "boolean", "default": False,
                                   "description": "Include each generated SKILL.md's "
                                                  "first 40 lines."},
        },
        "required": [],
    },
}

ALL = {"starlearner_sync": SYNC, "starlearner_status": STATUS,
       "starlearner_review": REVIEW}
