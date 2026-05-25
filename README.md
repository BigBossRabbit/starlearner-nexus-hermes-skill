# StarLearner-Nexus for Hermes Agent

**Automatically turn your GitHub starred repositories into usable Hermes Agent skills.**

![StarLearner-Nexus Banner](assets/starlearner-banner.svg)

## 🚀 Overview

StarLearner-Nexus is a Hermes Agent skill that transforms your GitHub starred repositories into a personalized, automatically-updating library of Hermes skills. Instead of manually creating skills for every interesting repo you find, this skill:

## 🌟 Features

- **Automated Repository Ingestion**: Fetches your starred repositories from GitHub API
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

### Method 1: Install as Hermes Skill (Recommended)

1. **Tap the skill repository**:
   ```bash
   hermes skills tap add https://github.com/BigBossRabbit/starlearner-nexus-hermes-skill
   ```

2. **Install the skill**:
   ```bash
   hermes skills install starlearner-nexus
   ```

3. **Configure your GitHub token**:
   ```bash
   hermes auth add github-token
   # When prompted, enter your GitHub personal access token
   ```

4. **Run the initial sync**:
   ```bash
   hermes skills run starlearner-nexus --script daily_sync.sh
   ```

## 📂 Output Structure

When StarLearner-Nexus processes your starred repositories, it creates:

```bash
~/.hermes/skills/starlearner-nexus/
├── SKILL.md                  # This skill's documentation
├── scripts/                  # Execution scripts
│   ├── fetch_starred_repos.sh    # Gets your starred repos from GitHub
│   ├── categorize_repos.py       # Sorts repos by topic using keyword matching
│   ├── generate_skills.py        # Creates .SKILL.md files from repo data
│   └── daily_sync.sh             # Orchestrates the full pipeline
├── references/               # Static data & templates
│   ├── categories.json       # Topic → keyword mappings for categorization
│   ├── profile-credential-verification.md # Guide for verifying credential isolation
│   └── skill_templates/      # Jinja2 templates for generated skills
├── data/                     # Generated JSON caches
│   ├── starred_repos.json      # Raw GitHub API response
│   └── categorized_repos.json  # Domain-classified repositories
├── generated_skills/         # Currently active generated skills (by category)
│   ├── bitcoin-lightning/
│   │   ├── lnd/
│   │   │   └── SKILL.md
│   │   └── ... (more skills)
│   ├── ai-ml/
│   │   ├── langchain/
│   │   │   └── SKILL.md
│   │   └── ... (more skills)
│   └── ... (more categories)
├── generated_skills_final/   # Latest build of generated skills
├── generated_skills_test/    # Test build (for verification)
├── logs/                     # Execution logs
└── requirements.txt          # Python dependencies (PyYAML, Jinja2, requests)
```

## 💡 Example Output

When successful, you'll see skills generated like:

```bash
starlearner-nexus/generated_skills/bitcoin-lightning/lnd/SKILL.md
starlearner-nexus/generated_skills/ai-ml/langchain/SKILL.md
starlearner-nexus/generated_skills/privacy-security/changedetection-io/SKILL.md
starlearner-nexus/generated_skills/finance-trading/awesome-finance-skills/SKILL.md
starlearner-nexus/generated_skills/voice-audio/hermes-agent-self-evolution/SKILL.md
```

Each generated skill contains:
- Clear explanation of what the original repository does
- Why it's useful for Hermes Agent users
- Installation instructions (`hermes skills install <skill-name>`)
- Common use cases and examples
- Links to documentation and source
- Proper SKILL.md formatting with metadata

## 📖 Documentation

- [SKILL.md](SKILL.md) - Complete skill documentation (this file)
- [references/categories.json](references/categories.json) - Domain categorization rules
- [references/skill_templates/default_skill.md.j2](references/skill_templates/default_skill.md.j2) - Skill generation template
- [scripts/daily_sync.sh](scripts/daily_sync.sh) - Main execution script
- [scripts/verify_installation.py](scripts/verify_installation.py) - Installation verification script

## 🔧 Usage

Once installed and configured, StarLearner-Nexus runs via:

```bash
# List available skills to find StarLearner-Nexus
hermes skills list

# Run the skill manually (fetches, categorizes, and generates skills)
hermes skills run starlearner-nexus --script daily_sync.sh

# Run individual steps if needed
hermes skills run starlearner-nexus --script fetch_starred_repos.sh
hermes skills run starlearner-nexus --script categorize_repos.py
hermes skills run starlearner-nexus --script generate_skills.py
```

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
```bash
# To change from daily 2 AM to daily 9 AM:
0 9 * * * /path/to/.hermes/skills/starlearner-nexus/scripts/daily_sync.sh
```

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

### Permission Denied on Scripts

Run these commands to fix permissions:
```bash
chmod +x ~/.hermes/skills/starlearner-nexus/scripts/*.py
chmod +x ~/.hermes/skills/starlearner-nexus/scripts/*.sh
```

### Skill Generation Errors

Some repositories may cause skill generation to fail with `'NoneType' object has no attribute 'strip'` when repository data contains null values. To resolve:
1. Check execution logs for the specific repository causing the issue
2. Consider creating skills manually for problematic repositories
3. Verify repository metadata (description, topics) is not null

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- Built for [Hermes Agent](https://hermes-agent.nousresearch.com/) by Nous Research
- Uses GitHub API v3 for repository data
- Relies on community-powered categorization through keyword matching
- Inspired by the desire to make skill creation as effortless as starring a repo

---

*Transform your GitHub stars into a living skill library with StarLearner-Nexus - where your curiosity becomes collective intelligence.* 🌟⚡