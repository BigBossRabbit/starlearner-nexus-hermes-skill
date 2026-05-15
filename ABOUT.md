# StarLearner-Nexus for Hermes Agent

## About This Project

StarLearner-Nexus is a Hermes Agent skill that automatically transforms your GitHub starred repositories into a personalized, continuously updating library of reusable AI skills.

### Core Concept
Instead of manually creating Hermes skills for each interesting GitHub repository you encounter, this skill automates the entire process:
- Fetches your starred repositories from GitHub
- Intelligently categorizes them by topic (AI/ML, Dev Tools, Privacy/Security, Finance, etc.)  
- Generates complete, ready-to-use Hermes skills for each repository
- Updates automatically when you star new repositories

### Key Features
- **Automatic Repository Ingestion**: Securely fetches all your starred GitHub repositories
- **Smart Categorization**: Organizes repos into 10+ domains using keyword analysis
- **Skill Generation**: Creates production-ready Hermes skills with metadata, docs, and examples
- **Continuous Learning**: Built-in cron job support for daily updates
- **Zero Manual Effort**: Once configured, your star collection becomes a living skill library

### How It Works
1. **Fetch**: Uses your GitHub token to retrieve starred repositories (securely stored in Hermes credentials)
2. **Categorizes**: Sorts repos into topics using intelligent keyword matching
3. **Generates**: Creates complete .SKILL.md files from templates with repo-specific content
4. **Deploys**: Outputs skills directly to your Hermes skills directory for immediate use

### Generated Skill Quality
Each created skill includes:
- Proper YAML frontmatter with name, description, version
- Detailed explanation of the original repository's purpose
- Installation and usage instructions
- Links to source and documentation
- Automatic categorization into relevant folders (ai-ml/, development-tools/, privacy-security/, etc.)

### Perfect For
- Power users who star many repositories and want to leverage them in Hermes
- Researchers building domain-specific skill libraries
- Anyone wanting to automate skill discovery from their GitHub activity
- Teams sharing curated skill collections based on collective starring behavior

### Getting Started
```bash
# 1. Tap the skill repository
hermes skills tap add https://github.com/BigBossRabbit/starlearner-nexus-hermes-skill

# 2. Install the skill  
hermes skills install starlearner-nexus

# 3. Configure GitHub token (one-time setup)
hermes auth add github-token
# Enter your GitHub personal access token (public_repo scope sufficient)

# 4. Run initial synchronization
hermes skills run starlearner-nexus --script daily_sync.sh

# 5. Set up automatic daily updates (recommended)
crontab -e
# Add: 0 2 * * * /path/to/.hermes/skills/starlearner-nexus/scripts/daily_sync.sh
```

### Repository Structure
```
starlearner-nexus/
├── SKILL.md                  # This skill's definition
├── scripts/                  # Automation scripts (fetch, categorize, generate, sync)
├── references/               # Templates and categorization rules
├── data/                     # Generated JSON caches
├── generated_skills/         # Active skills by category
├── logs/                     # Execution history
└── requirements.txt          # Python dependencies
```

### Privacy & Security
- GitHub tokens stored securely in Hermes' credential system (never in plain text)
- Only processes public repositories by default
- Respects GitHub API rate limits
- No data leaves your Hermes instance except for authenticated GitHub API calls

---

*Transform your GitHub stars into AI skills automatically. Star a repo today, use it as a Hermes skill tomorrow.* 🌟
