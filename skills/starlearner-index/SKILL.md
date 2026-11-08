---
name: starlearner-index
description: "StarLearner-Nexus index: what the plugin generated from your GitHub stars, how to list and open the generated skills (starlearner_status / skill_view(\"starlearner-nexus:<name>\")), and what the categories mean."
---

# StarLearner-Nexus Index

This plugin turns the repositories you star on GitHub into a library of
Hermes skills. This index skill is always there from install; everything
the plugin **generates** is a sibling skill under the
`starlearner-nexus:` namespace, loaded on demand.

## What the plugin did for this profile

- `starlearner_status` — the ledger (every star ever seen; a repo is never
  processed twice), the generated + registered skills (namespaced
  `starlearner-nexus:<name>`), the last two-track assessment, the LLM
  enrichment state, and the pending review items.
- `starlearner_review` — item by item: each new starred repo with its
  description, category, the two-track assessment (worth integrating
  into your own makeup / business-opportunity value), and the generated
  skill. Everything LLM-shaped lands here for the human — never silently
  in the ledger.
- `starlearner_sync` — the run itself (fetch the new stars → map →
  categorize → assess → generate). Bounded, non-interactive, fails
  clean. Generated skills are **registered only when the
  `register_generated_skills` setting is on** (off by default; review
  with `starlearner_review` first, then switch it on).

## How to open a generated skill

```
skill_view("starlearner-nexus:<name>")
```

The names come out of `starlearner_status` / `starlearner_review` / the
`starlearner_sync` result (`registered_skills` when the setting is on,
otherwise the generated files are listed by `starlearner_review`). When
the agent loads a
plugin skill, a bundle context banner lists the sibling skills generated
by the same runs.

## What the categories mean

Generated skills are grouped into the 12 domain categories
(`references/categories.json`): bitcoin-lightning, ai-ml,
privacy-security, finance-trading, development-tools, social-media,
health-wellness, travel-exploration, voice-audio, video-streaming,
education-learning, gaming-entertainment. The keyword engine's verdict
drives the directory structure; the optional LLM enrichment only
classifies what the keywords left uncategorized (and every
LLM-vs-keyword disagreement is flagged in `starlearner_review`).

## When the user says…

- "what was that repo I starred" / "that bookmarked tool" → it is
  probably one of these skills: `starlearner_status` for the list,
  `skill_view("starlearner-nexus:<name>")` for the one they mean.
- "review what the last sync found" → `starlearner_review` (the
  human-in-the-loop surface).
- "refresh my skills from GitHub" → `starlearner_sync`.

## Auth (the plugin)

One read-only GitHub token, `STARLEARNER_GITHUB_TOKEN` — a `requires_env`
secret: prompted (hidden) at `hermes plugins install`, saved by the HOST
to the active profile's `.env`, read back only through the host's secret
scope. The plugin never sees or stores it. A classic `public_repo`-scope
token (or a fine-grained read-only public-repos token) is all it needs.
