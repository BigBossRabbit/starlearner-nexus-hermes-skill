# StarLearner-Nexus for Hermes Agent

**Automatically turn your GitHub starred repositories into usable Hermes Agent skills.**

![StarLearner-Nexus Banner](assets/starlearner-banner.svg)

## 🚀 Overview

StarLearner-Nexus is a Hermes Agent skill that transforms your GitHub starred repositories into a personalized, automatically-updating library of Hermes skills. Instead of manually creating skills for every interesting repo you find, this skill:

1. **Fetches** your starred repositories from GitHub
2. **Intelligently categorizes** them by topic (AI/ML, Dev Tools, Privacy/Security, Finance, etc.) using keyword analysis
3. **Generates complete, ready-to-use Hermes skills** for each repository with proper metadata, installation instructions, usage examples, and feature lists
4. **Updates automatically** when you star new repositories (via daily sync)

Once set up, your GitHub star collection becomes a living skill library that grows with your interests.

## 🌟 Features

- **Automated Repository Ingestion**: Fetches your starred repos from GitHub API
- **Intelligent Categorization**: Sorts repositories by topic using keyword matching
- **Skill Generation**: Creates complete Hermes skills (.SKILL.md) from repo data
- **Automatic Updates**: Daily sync keeps your skill library current
- **Multiple Categories**: Supports AI/ML, development tools, privacy, finance, and more
- **Easy Installation**: Simple tap, install, and configure workflow
- **Cron-Ready**: Designed for automatic daily execution via cron job

## 📋 Requirements

- Hermes Agent installed ([install guide](https://hermes-agent.nousresearch.com/docs/user-guide/installation))
- GitHub Personal Access Token ([create one](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)) with `public_repo` scope

## ⚙️ Installation

1. Tap the skill repository:
   ```bash
   hermes skills tap add https://github.com/BigBossRabbit/starlearner-nexus-hermes-skill
   ```

2. Install the skill:
   ```bash
   hermes skills install starlearner-nexus
   ```

3. Configure your GitHub token:
   ```bash
   hermes auth add github-token
   # When prompted, enter your GitHub personal access token
   ```

4. Run the initial sync:
   ```bash
   hermes skills run starlearner-nexus --script daily_sync.sh
   ```

## 🔑 How It Works (The Magic Behind the Scenes)

The skill uses four interconnected scripts that work together:

| Script | Purpose | Automation |
|--------|---------|------------|
| `fetch_starred_repos.sh` | Pulls your starred repositories from GitHub API (requires personal access token) | Can be cronned |
| `categorize_repos.py` | Sorts repos into topical categories using keyword matching (AI, crypto, dev tools, privacy, etc.) | Runs after fetch |
| `generate_skills.py` | Creates complete Hermes skill files (.SKILL.md) from categorized repo data using Jinja2 templates | Runs after categorization |
| `daily_sync.sh` | Orchestrates the full pipeline (fetch → categorize → generate) | Designed for daily cron execution |

**After initial setup**, simply:
1. Star interesting repositories on GitHub
2. Let your daily cron job run (or manually execute `daily_sync.sh`)
3. New skills appear automatically in your Hermes skills directory

## 🔄 Setting Up Automatic Updates

To have new starred repos automatically generate skills:
1. Edit your crontab: `crontab -e`
2. Add this line (runs daily at 2 AM):
   ```
   0 2 * * * /path/to/.hermes/skills/starlearner-nexus/scripts/daily_sync.sh >> /path/to/.hermes/skills/starlearner-nexus/logs/starlearner-nexus-cron.log 2>&1
   ```
3. Save and exit - your skill library will now update daily!

## 📁 Repository Structure

```
starlearner-nexus/
├── SKILL.md                  # The Hermes skill itself (this repository)
├── scripts/                  # Execution scripts
│   ├── fetch_starred_repos.sh    # Gets your starred repos from GitHub
│   ├── categorize_repos.py       # Sorts repos by topic using keyword matching
│   ├── generate_skills.py        # Creates .SKILL.md files from repo data
│   └── daily_sync.sh             # Orchestrates the full pipeline
├── references/               # Static data & templates
│   ├── categories.json       # Topic → keyword mappings for categorization
│   ├── profile-credential-verification.md # Guide for verifying credential isolation
│   └── skill_templates/      # Jinja2 templates for generated skills
│       └── default_skill.md.j2
├── data/                     # Generated JSON caches (starred_repos.json, categorized_repos.json)
├── generated_skills/         # Currently active generated skills (by category)
├── generated_skills_final/   # Latest build of generated skills
├── generated_skills_test/    # Test build (for verification)
├── logs/                     # Execution logs
└── requirements.txt          # Python dependencies (PyYAML, Jinja2, requests)
```

## 🛠️ What Gets Generated

For each starred repository, StarLearner-Nexus creates a complete Hermes skill including:
- Proper SKILL.md YAML frontmatter (name, description, version, author)
- Detailed description explaining what the original repo does
- Installation instructions (`hermes skills install`)
- Usage examples and common commands
- Links to the original GitHub repository
- Tags based on repo language and topics
- Automatic categorization into folders like:
  - `ai-ml/`
  - `development-tools/`
  - `privacy-security/`
  - `finance-trading/`
  - `social-media/`
  - `voice-audio/`
  - `video-streaming/`
  - `health-wellness/`
  - `education-learning/`
  - `bitcoin-lightning/`
  - `gaming-entertainment/`
  - ...and more based on content analysis

## 💡 Example Generated Skills

After running the sync, you might see skills like:
- `starlearner-nexus/generated_skills/ai-ml/everything-claude-code/SKILL.md`
- `starlearner-nexus/generated_skills/development-tools/shannon/SKILL.md`
- `starlearner-nexus/generated_skills/privacy-security/changedetection-io/SKILL.md`
- `starlearner-nexus/generated_skills/finance-trading/awesome-finance-skills/SKILL.md`
- `starlearner-nexus/generated_skills/voice-audio/hermes-agent-self-evolution/SKILL.md`

Each skill contains:
- Clear explanation of what the original repo does
- Why it's useful for Hermes Agent users
- Installation instructions
- Common use cases and examples
- Links to documentation and source

## ⚙️ Configuration Options

You can customize the behavior by editing:
- `references/categories.json` - Modify keyword mappings for better categorization
- `references/skill_templates/default_skill.md.j2` - Change the output skill template
- Scripts themselves - Adjust fetch limits, categorization logic, etc.

## 📝 Notes & Best Practices

- **GitHub Token Security**: Your token is stored securely in Hermes' credential system (not in plain text)
- **Rate Limits**: The script respects GitHub API rate limits (includes delays between requests)
- **Private Repos**: Only processes public repositories by default (to avoid token overexposure)
- **Updates**: Re-runs will update existing skills if the source repo changes significantly (stars, forks, description)
- **Manual Override**: You can always manually edit generated skills - they won't be overwritten unless you re-run the full sync for that specific repo

## 🔧 Troubleshooting

### No Skills Generated

- Verify your GitHub token is configured: `hermes auth list`
- Check that you have starred public repositories on GitHub
- Verify network connectivity to GitHub API
- Check execution logs: `cat ~/.hermes/skills/starlearner-nexus/logs/starlearner-nexus-*.log`

### GitHub API Rate Limits

- The script includes basic rate limiting and delays
- For large star collections (>500 repos), consider using a GitHub Personal Access Token for higher limits
- Wait and retry if you encounter rate limit errors

## 🎯 Customization

### Adjust Processing Limits

Edit the scripts to change how many repositories are processed:
- Modify `fetch_starred_repos.sh` to adjust API call limits
- Edit `generate_skills.py` to change the number of skills per category (currently top 5 by stars)

### Modify Categorization Rules

Edit `references/categories.json` to:
- Add/remove domains or adjust keywords
- Change how repositories are classified into topics
- Improve accuracy for your specific star collection

### Change Schedule

Update the cronjob schedule using your preferred cron editor:
```
# To change from daily 2 AM to daily 9 AM:
0 9 * * * /path/to/.hermes/skills/starlearner-nexus/scripts/daily_sync.sh
```

## 💝 Support This Project

If you find this project useful, please consider supporting its development with a donation. You can send Bitcoin to `bc1qrdc653jpc6psactzdgayl9xa5h3y5etycpdn8r` or via Lightning to `okin@blink.sv`. Your contributions help keep the project alive and improve it for everyone. Thank you!

## 🙏 Acknowledgements

- Built for [Hermes Agent](https://hermes-agent.nousresearch.com/) by Nous Research
- Uses GitHub API v3 for repository data
- Relies on community-powered categorization through keyword matching
- Inspired by the desire to make skill creation as effortless as starring a repo

## 📬 Ready to Use Your Stars as Skills?

1. **[Tap the skill](hermes skills tap add https://github.com/BigBossRabbit/starlearner-nexus-hermes-skill)**
2. **[Install it](hermes skills install starlearner-nexus)**
3. **[Add your GitHub token](hermes auth add github-token)**
4. **[Run the initial sync](hermes skills run starlearner-nexus --script daily_sync.sh)**
5. **[Set up daily cron](crontab -e)** → `0 2 * * * /path/to/.hermes/skills/starlearner-nexus/scripts/daily_sync.sh`

Your next starred repo on GitHub could be tomorrow's new Hermes skill - all automatically generated. 🌟

*Happy skill collecting!* 🚀

