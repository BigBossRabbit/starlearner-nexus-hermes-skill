# Default skill template for StarLearner-Nexus
---
name: seanime
description: "Free and open-source media server for anime and manga that includes library scanning, downloading, transcoding, torrent streaming, and more."
version: "1.1.0"
author: "GitHub Community (via StarLearner-Nexus)"
license: "MIT"
tags: ["video_streaming", "go", "github-derived", "auto-generated"]
related_skills: ["video-streaming-general", "video-downloader", "live-streamer"]
---

# seanime

Free and open-source media server for anime and manga that includes library scanning, downloading, transcoding, torrent streaming, and more.

## 🚀 Quick Start

```bash
# Install the skill (if not already installed)
hermes skills install seanime --tap BigBossRabbit/starlearner-nexus-hermes-skill

# Run the skill
hermes skills run seanime
```

## 🌟 Features


- Integrates with seanime (https://github.com/stormerino78/seanime)

- Provides: Free and open-source media server for anime and manga that includes library scanning, downloading, transcoding, torrent streaming, and more.

- Implemented in Go

- Distributed as Go module

- Repository with 56 GitHub stars

- Repository has 1 forks

- Licensed under GNU General Public License v3.0

- Large codebase (578539 KB)

- Monitored by 56 GitHub users


## 📖 Usage

# Basic Installation and Usage

```bash
# Install from your StarLearner-Nexus tap
hermes skills tap add { github_username }/starlearner-nexus-hermes-skill
hermes skills install seanime --tap { github_username }/starlearner-nexus-hermes-skill

# Run the skill
hermes skills run seanime
```

## Go-Specific Usage

This skill provides access to a Go repository. You may need to:
- Install Go (if not already installed)
- Get dependencies: `go get ./...`
- Build: `go build` or `go install`

Example:
```bash
# Clone and use the original repository
git clone https://github.com/stormerino78/seanime
cd seanime
go get ./...
# Follow repository-specific usage instructions
```
## General Usage Tips

- This skill provides convenient access to the seanime repository within your Hermes agent ecosystem
- For advanced usage, consult the original repository documentation at: https://github.com/stormerino78/seanime
- Consider starring the original repository on GitHub if you find it useful
- Check the repository's issues and discussions for community support and examples

## Configuration

Some repositories may require environment variables or configuration files. Check:
- https://github.com/stormerino78/seanime/#readme for setup instructions
- https://github.com/stormerino78/seanime/wiki for detailed documentation
- https://github.com/stormerino78/seanime/examples for usage examples



## 🔧 Installation

The seanime skill provides access to the repository within your Hermes agent.

## Language Runtime

This skill is for a Go repository. Depending on how you plan to use it, you may need to install:
- Go compiler and toolchain
- Git for fetching dependencies

## Hermes Integration

This skill is designed to work within the Hermes agent ecosystem:
- No additional Hermes installation required beyond the skill itself
- Can be combined with other Hermes skills for enhanced functionality
- Accessible to all Hermes profiles via Orchestrator delegation

## Source Verification

- Skill generated from: https://github.com/stormerino78/seanime
- Generation includes repository metadata and description
- For the most current version, refer to the original GitHub repository

## Troubleshooting

If you encounter issues:
1. Verify you have the necessary language runtimes installed
2. Check the original repository for specific setup requirements
3. Ensure your Hermes agent has internet access to fetch any needed dependencies
4. Consult the Hermes community for skill-specific usage help



## 📂 Source

This skill was automatically generated from the GitHub repository: https://github.com/stormerino78/seanime
Generated on: 2026-05-15 20:58:05
Original repository: 
Project homepage: https://seanime.rahim.app

## 📚 Documentation

For detailed documentation, refer to the original repository:
- Documentation: #readme
- Examples: #examples (if available)
- Issues: /issues
- Changelog: /blob/main/CHANGELOG.md (if available)

## 🛠️ Dependencies

This skill provides access to a Go repository. Actual dependencies depend on how you use the underlying repository:

- Go compiler and toolchain

Note: This skill provides repository access within Hermes. You may need to install additional tools or libraries depending on your specific use case.

## 🔄 Updates

This skill will be automatically updated when you run StarLearner-Nexus to refresh your GitHub stars.
To manually update: `hermes skills update seanime --tap BigBossRabbit/starlearner-nexus-hermes-skill`

## 💬 Support

For questions or issues with this skill:
- Check the original repository issues: /issues
- Visit the Hermes community for general skill usage help
- Consider contributing improvements back to the original project