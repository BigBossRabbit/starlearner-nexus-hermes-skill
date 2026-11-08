# StarLearner-Nexus for Hermes Agent

**Automatically turn your GitHub starred repositories into usable Hermes
Agent skills.**

![StarLearner-Nexus Banner](assets/starlearner-nexus-hermes-skill-banner.svg)

**Origin of the reapx lineage.** The
[reapx](https://github.com/BigBossRabbit/reapx) plugin is derived from
this one (it reuses this pipeline's map → categorize → generate stages
verbatim, and replaces the GitHub-stars transport with a
logged-in-browser bookmark harvest); it discloses that in its README and
catalog entry. Same owner, both entries (R05), different transports and
capabilities (R16). Lineage evidence (from the local git logs of both
repos, re-verified at PR time): this repository's initial commit is
dated **2026-05-15**; the fork event is on the record in this history
(`bfd4931` "Add X-bookmarks ingestion source" at 2026-08-13 22:11,
reverted in `7ad9692` at 22:23 — with **reapx's** initial commit
`59937d1` at 22:16, the same evening, between the two); and both repos
merged the same incremental-ledger + two-track feature the same morning
(2026-09-20 10:30, PR #1 here / PR #2 there).

---

## Part 1 — the plugin (install it)

A **Hermes plugin** (manifest v2): three tools, one registered auxiliary
LLM task, one bundled index skill, one optional automation blueprint,
**one declared `requires_env` secret** (the read-only GitHub token —
prompted, hidden, at install; saved by the host; read back only through
the host's secret scope), zero keys in the plugin, zero capabilities
needed (no override arguments are ever passed to `ctx.llm`).

```bash
hermes plugins install <this repo>   # or the catalog entry, pinned SHA
# the install prompts (hidden) for your read-only GitHub token and the
# host saves it to the active profile's .env — the plugin never sees it
```

| Tool | What it does |
|---|---|
| `starlearner_sync` | The product: fetch the new stars → map (the LLM curation pass) → categorize → two-track assess → **generate skills** (`starlearner-nexus:<name>`, returned in the result; registered too when the `register_generated_skills` setting is on). |
| `starlearner_status` | Read-only: token state (set/not set), last sync, ledger counts, registered skills, assessment + LLM-enrichment state, pending review items. |
| `starlearner_review` | Read-only, item by item: each new starred repo, the two tracks, the generated skill. **Everything LLM-shaped lands here for the human** — never silently in the ledger. |

### The settings (Desktop → Plugins → starlearner-nexus)

| Setting | Default | Meaning |
|---|---|---|
| `enrich` | `llm` | `llm` = map/categorize/assess run through the host LLM (`ctx.llm` — your active provider and model, **host-owned credentials, zero keys in this plugin**) with the deterministic rules engine as the bit-for-bit fallback; `rules` = zero LLM calls. |
| `llm_max_items` | `50` | Per-run cap on items sent for LLM enrichment (a token-spend guard). `0` disables. |
| `generate_limit` | `5` | Max skills per category per run (top by stars). `0` = assess-only. |
| `max_pages` | `30` | Hard cap on the paginated `/user/starred` fetch (100 stars/page). A clean error, never a hang. |
| `register_generated_skills` | `false` | Register generated skills (`starlearner-nexus:<name>`, loaded with `skill_view`). Off by default — skill bodies are rendered from other people's READMEs, so you review first (`starlearner_review`) and switch registration on when you trust the output. If false: files + review only. |

**Settings are the only source of truth.** A tool call may pass just three
things, and none of them is a setting: `dry_run` (per-call intent),
`max_pages` and `generate_limit` (per-call caps, each one
`min(argument, setting)` — an argument can only tighten your ceiling). So a
prompt-injected call cannot switch LLM enrichment back on after you picked
`rules`, lift the `llm_max_items` spend cap, or force skill registration;
the tool schema declares exactly those three.

**Registration timing (probed on a live Hermes v0.22.6):** handler-time
`register_skill` is accepted **and live in the same session** — a
`skill_view("starlearner-nexus:<name>")` on a name returned by a sync
resolves through the real agent path the same second. A plugin
(re)load re-registers everything generated before it from the
`plugin_db` registry (the guaranteed form).

### The auth (the one credential — catalog rule 11, the textbook route)

`STARLEARNER_GITHUB_TOKEN`, declared `requires_env` (the rich format:
name + description + the PAT-creation doc URL + `secret: true`):

- **prompted (hidden input) at `hermes plugins install`**; **saved by
  the host** to the active profile's `.env`; read back per call through
  **`agent.secret_scope.get_secret`** (profile-scoped — never a bare
  `os.environ` read, never a `.env` file, never another tool's login);
- **the narrowest scope we can name**: a classic token with
  `public_repo`, or a fine-grained token with read-only access to
  public repositories — one endpoint
  (`GET /user/starred`, the repos **you** starred);
- **never** in the plugin tree, its logs, its errors (a 401 carries the
  class + the fix, never the value), its tool results, or its stored
  data;
- the plugin's fetch is **in-process** (`requests`): no `gh`, no
  `curl`, no `jq`, no subprocess (the standalone's gh-CLI/curl fetcher
  stays standalone-only — shelling out to `gh` would ride another
  tool's stored login);
- leaves the machine only to `api.github.com`, over HTTPS, bounded
  (`timeout=30` per page, the `max_pages` hard cap) — R12: a missing
  token, a rate limit, or a 401 is a reported error, never a hang.

*(The old README's `hermes auth add github-token` line was a doc-ism —
no such route exists; `requires_env` + the install prompt is the
route. This rewrite corrects it.)*

### The LLM layer (`ctx.llm`), and when there is no LLM

The engine today has **zero LLM calls** (the fetcher maps the full
GitHub repo objects, weighted-keyword categorizing, a two-track rules
assessor, Jinja2 generation). `ctx.llm` is a new, optional
**enrichment layer** over it:

- **map** — the curation pass (B.4): per starred repo, the LLM gives
  the skill identity it should carry (a 3–8 word name, a plain
  description) — **not necessarily the repo name**. The rules fallback
  = today's identity (the repo name verbatim + the raw description),
  bit-for-bit.
- **categorize** — **fixed fusion, deterministic:** a keyword hit
  always wins (auditable; drives the directory structure). The LLM
  classifies items the keyword engine left `uncategorized`; a confident
  LLM verdict that *disagrees* with a keyword verdict is recorded as
  `llm_override` **in `starlearner_review` for the human** — never
  applied.
- **assess** — keyword hits are the floor (union); LLM-derived Track-B
  (business-opportunity) hits land in `starlearner_review` with their
  rationale and are **never written to the ledger without review**.
- **generate** — never LLM. Jinja2 renders LLM-produced *variables*;
  the LLM never writes the SKILL.md structure.

Zero override arguments are ever passed (`provider=` / `model=` /
`agent_id=` / `profile=` — the trust gate is structurally unreachable);
`task=` is only this plugin's own registered auxiliary task
(`starlearner_enricher`). Every LLM failure — no provider configured, a
5xx through the host's fallback chain, the 30s timeout, non-JSON or
schema-invalid output (an error class only) — maps to ONE behavior:
**the rules fallback, never a failure, never a hang.**

---

## What this plugin does on your machine (R13 disclosures)

> **Network calls to third-party services**
> - **api.github.com** (one endpoint): `GET /user/starred` — the
>   repositories **you** have starred — authenticated with **your**
>   read-only GitHub token, over HTTPS, paginated, bounded
>   (`max_pages`, default 30). Nothing else on GitHub is called.
> - **Your LLM provider** (only if `enrich: llm`, the default): the
>   map/categorize/assess stages send **public repo metadata** (name,
>   description, topics, language, stars) through the **Hermes host**
>   (`ctx.llm`) to your active provider/model, host-owned credentials
>   — **the plugin never sees or stores any key**. Set `enrich: rules`
>   for zero LLM calls.
> - **No telemetry, no usage reporting, no phone-home of any kind.**
>
> **Reads outside the plugin's own data**
> - **None.** No browser, no cookies, no other applications' files, no
>   other tool's login. (The plugin's own
>   `plugin-data/starlearner-nexus/` store + one setting-declared token
>   are the only things it touches.)
>
> **Shell commands / processes**
> - **None.** The GitHub fetch is an in-process HTTPS request
>   (`requests`); no `gh`, no `curl`, no `jq`, no subprocesses of any
>   kind. (The standalone mode's `gh`-CLI option and curl script are
>   not part of the plugin.)
>
> **Long-running background processes**
> - **None of the plugin's own.** A sync runs inside a tool call
>   (bounded: `timeout=30` per page, `max_pages` hard cap). The
>   optional **Automation Blueprint "starlearner-nexus:sync"** (a
>   ready-made cron job you must explicitly schedule) runs the same
>   pipeline under hermes cron — non-interactive: a missing token, a
>   rate limit, or a 401 is a reported error, never a hang.
>
> **Stored credentials**
> - **One, and the plugin doesn't store it.** Your GitHub token is a
>   `requires_env` secret: prompted (hidden) at
>   `hermes plugins install`, **saved by Hermes** to the active
>   profile's `.env`, and read back only through the host's secret
>   scope (`agent.secret_scope.get_secret`) — profile-scoped, never a
>   bare environment read, never in the plugin's files, logs, errors,
>   or results. It leaves your machine only to `api.github.com`, in
>   the `Authorization` header of `GET /user/starred`. A read-only
>   token (classic `public_repo`, or a fine-grained read-only
>   public-repos token) is all it needs — this README says exactly
>   which. LLM credentials are entirely the host's.
>
> **Data + writes**
> - Everything the plugin writes lives in
>   `<hermes home>/plugin-data/starlearner-nexus/`: the raw stars
>   fetch, the seen-ledger, generated skills, assessment output. Your
>   starred-repo list (public repo metadata) stays on your machine (LLM
>   enrichment excepted + disclosed). Uninstalling the plugin leaves
>   your data.

---

## Part 2 — the standalone (run it by hand)

One tree, two install shapes (B.12): the same repo keeps working as the
**standalone skill-pipeline** — `bash scripts/daily_sync.sh`, the
`Makefile` targets, `tests/run_smoke.sh`,
`scripts/run_starlearner_3day.sh` cron. **Nothing a standalone user
runs changes, breaks, or requires the plugin.** The plugin layer
(`plugin.yaml`, `__init__.py`, `schemas.py`, `tools.py`, `llm.py`,
`skills_out.py`, `harvest.py`, `github_fetch.py`,
`skills/starlearner-index/`) is new files the standalone never imports;
the engine changes that made it possible are **additive seams**
(`starlearner_paths.py` (the data-dir convention,
`STARLEARNER_DATA_DIR`), `--generate-limit`/`--template` on
`generate_skills.py`, `scripts/__init__.py`, `plugin_skill.md.j2`
beside the standalone template — verified zero-behavior-change:
generate_skills(orig) vs generate_skills(seamed), defaults,
byte-identical output).

- **Standalone writes** go to the repo's `data/`, `logs/`,
  `generated_skills/` (all gitignored). **Plugin writes** go to
  `plugin-data/starlearner-nexus/` only (never the install tree).
- **Standalone auth** = `fetch_starred_repos.sh`: the GitHub CLI
  (`gh api --paginate user/starred`, gh's own login) **or** a
  `GITHUB_TOKEN`-bearing curl loop, else it fails clean. **Plugin
  auth** = `STARLEARNER_GITHUB_TOKEN` via `requires_env` →
  `agent.secret_scope.get_secret` (Part 1).
- **The standalone keeps its whole soul** (B.12):
  `daily_sync.sh`, the 3-day runner, the install gate
  (`install_skills.py` — "evolve, don't collect": dry-run default,
  never overwrite, no name collisions, size caps), the usage ledger
  (`usage_ledger.py` — which skills earn their place, counted from
  real `skill_view` loads), the tap distribution, the SKILL.md
  delegate/orchestrator patterns, the security-check +
  scanner-false-positive playbook, `references/` (github_api.md,
  profile-credential-verification.md).
- **What the plugin deliberately doesn't port** (B.10): the gh-CLI auth
  path (R11), the usage loop (reads the profiles' `state.db`s —
  standalone-only until a public skill-usage API), the install gate's
  copytree (`ctx.register_skill` replaces it), repo-tree writes.

**The plugin is the same engine, installed properly — the standalone is
the same engine, run by hand, with its own QA tools.**

### 🚀 Overview

StarLearner-Nexus transforms your GitHub starred repositories into a
personalized, automatically-updating library of skills. Instead of
manually creating skills for every interesting repo you find:

- **Automated Repository Ingestion**: fetches your starred
  repositories (the standalone: gh-CLI/PAT curl; the plugin:
  secret_scope token, in-process)
- **Intelligent Categorization**: sorts repositories by domain using
  keyword matching (12 categories)
- **Skill Generation**: creates complete skills from repo data (Jinja2
  templates)
- **Incremental (only-new) processing**: a persistent seen-ledger
  means each run only counts and assesses repositories you have not
  already taken into account
- **Two-track assessment**: every new repo is scored for (a)
  integrating into your own makeup and (b) business-opportunity
  value, surfaced in `data/opportunities.json`
- **Cron-Ready**: the standalone 3-day runner / the plugin's
  automation blueprint

### 🔁 Incremental Processing (seen-ledger)

StarLearner-Nexus is **incremental by design**. It keeps a persistent
ledger at `data/ledger.json` (gitignored) that records every repository
already taken into account. On each run:

1. **Fetch** the full current set of starred repos (unchanged).
2. **Diff** against the ledger → only **NEW** repos advance.
3. Only new repos are **categorized**, **assessed** and turned into
   skills.
4. New repos are recorded into the ledger **only after a successful
   run**, so a mid-run failure never marks items as seen.

The result: a repo you have already processed is never counted again.
Each run reports **how many are new**, what was integrated, and what is
a business opportunity — not the total.

```bash
# See how many repos have been seen so far
python3 scripts/ledger.py report data/ledger.json
```

The ledger keys on the GitHub repo `id` (a stable identity), so
re-stars and renames are handled correctly.

### 📋 Requirements (standalone)

- Python 3.11+ (`pip3 install -r requirements.txt`)
- **GitHub auth, one of**: the GitHub CLI (`gh auth login`), or a
  GitHub Personal Access Token ([create
  one](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token))
  with `public_repo` scope, exported as `GITHUB_TOKEN`
  (the **standalone** route; the **plugin** uses
  `STARLEARNER_GITHUB_TOKEN` via the host's secret scope — see Part 1)
- Nothing else: no paid APIs, no browser, no keychain

### ⚙️ Installation (standalone)

```bash
# 1. Tap the skill repository
hermes skills tap add https://github.com/BigBossRabbit/starlearner-nexus-hermes-skill

# 2. Install the skill
hermes skills install starlearner-nexus

# 3. Configure your GitHub token (the STANDALONE route)
export GITHUB_TOKEN=your_personal_access_token_here
# (the plugin route: hermes plugins install — the hidden token prompt)

# 4. Run the initial sync
hermes skills run starlearner-nexus --script daily_sync.sh
```

### 📂 Output Structure

```bash
starlearner-nexus/
├── plugin.yaml                # the plugin manifest v2 (Part 1)
├── __init__.py                # register() — the plugin surface
├── schemas.py · tools.py      # the 3 tools + their JSON schemas
├── llm.py                     # the ctx.llm enrichment layer (B.4)
├── skills_out.py              # the generated-skills subsystem (B.7)
├── harvest.py                 # the in-process sync driver
├── github_fetch.py            # the in-process fetcher (secret_scope)
├── SKILL.md                   # This skill's documentation (standalone)
├── README.md · LICENSE · requirements.txt
├── skills/starlearner-index/  # the bundled starlearner-nexus:index
├── scripts/                   # Execution scripts
│   ├── fetch_starred_repos.sh    # STANDALONE fetch (gh → PAT curl → exit 1)
│   ├── categorize_repos.py       # Sorts repos by topic (keyword matching)
│   ├── assess_repos.py           # Two-track rules assessment
│   ├── ledger.py                 # The persistent seen-ledger
│   ├── generate_skills.py        # Creates skills from Jinja2 templates
│   ├── starlearner_paths.py      # the data-dir seam (STARLEARNER_DATA_DIR)
│   ├── daily_sync.sh             # Orchestrates the full pipeline
│   ├── run_starlearner_3day.sh   # 3-day cron runner
│   ├── install_skills.py         # the v2 install gate (STANDALONE-ONLY)
│   ├── usage_ledger.py           # the usage loop (STANDALONE-ONLY)
│   └── verify_installation.py    # install verification gate
├── references/               # Static data & templates
│   ├── categories.json       # Topic → keyword mappings
│   ├── github_api.md         # the API (pagination, rate limits)
│   ├── profile-credential-verification.md
│   └── skill_templates/      # default (standalone) + plugin templates
├── data/ · logs/ · generated_skills/   # gitignored — never commit
└── tests/
```

### 💡 Example Output (standalone)

```bash
starlearner-nexus/generated_skills/bitcoin-lightning/lnd/SKILL.md
starlearner-nexus/generated_skills/ai-ml/langchain/SKILL.md
starlearner-nexus/generated_skills/privacy-security/changedetection-io/SKILL.md
```

Each generated skill contains a clear explanation of what the original
repository does, why it's useful, installation instructions, common use
cases, and links to the source. (Standalone-generated skills are
ordinary directories, shareable as a tap; **plugin-generated** skills
are namespaced `starlearner-nexus:<name>`, read-only, registered —
their Quick Start says `skill_view("starlearner-nexus:<name>)``.)

### 🔧 Usage (standalone)

```bash
# List available skills to find StarLearner-Nexus
hermes skills list

# Run the skill manually (fetches, categorizes, and generates skills)
hermes skills run starlearner-nexus --script daily_sync.sh
```

### 🔧 Troubleshooting (standalone)

#### No Skills Generated

- Verify your GitHub token (`gh auth status`, or `GITHUB_TOKEN` is
  exported — the standalone route)
- Check that you have starred public repositories on GitHub
- Verify network connectivity to the GitHub API
- Check the execution logs

#### GitHub API Rate Limits

- The fetcher stops cleanly at the rate limit (a reported error)
- For large star collections (>500 repos), an authenticated PAT gives
  5000 req/h (the unauthenticated 60/h window can't list stars)
- Wait and retry if you encounter rate limit errors

#### Skill Generation Errors

Some repositories may cause skill generation to fail with
`'NoneType' object has no attribute 'strip')` when repository data
contains null values. To resolve: check the execution logs for the
specific repository, and verify its metadata (description, topics) is
not null.

## 📜 License

This project is licensed under the MIT License - see the
[LICENSE](LICENSE) file for details.

---

*Transform your GitHub stars into a living skill library with
StarLearner-Nexus - where your curiosity becomes collective
intelligence.* 🌟⚡
