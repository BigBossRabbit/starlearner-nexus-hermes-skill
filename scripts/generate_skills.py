#!/usr/bin/env python3
# generate_skills.py
# Generates Hermes skills from categorized repositories

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import jinja2

# Add the skill directory to path for imports
SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))

def load_categorized_repos(input_file):
    """Load categorized repositories from JSON file"""
    with open(input_file, 'r') as f:
        return json.load(f)

def get_skill_template(category_key):
    """Get the Jinja2 template for a specific category"""
    template_dir = SKILL_DIR / "references" / "skill_templates"
    
    # Try to load category-specific template first
    template_file = template_dir / f"{category_key}_skill.md.j2"
    if template_file.exists():
        with open(template_file, 'r') as f:
            return f.read()
    
    # Fall back to default template
    default_template = template_dir / "default_skill.md.j2"
    if default_template.exists():
        with open(default_template, 'r') as f:
            return f.read()
    
    # Ultimate fallback - basic template
    return '''---\
name: {{ skill_name }}\
description: "{{ skill_description }}"\
version: "{{ version }}"\
author: "{{ author }}"\
license: "{{ license }}"\
tags: {{ tags | tojson }}\
related_skills: {{ related_skills | tojson }}\
---\
# {{ skill_name }}\
\
{{ skill_description }}\
\
## Features\
{% for feature in features %}\
- {{ feature }}\
{% endfor %}\
\
## Usage\
```bash\
# Example usage\
{{ usage_example }}\
```\
\
## Installation\
The skill is ready to use! No additional installation required.\
```\

'''

def generate_skill_name(repo):
    """Generate a skill name from repository information"""
    # Clean the repo name for use as a skill identifier
    name = repo.get('name', 'unknown')
    # Convert to lowercase, replace non-alphanumeric with hyphens
    import re
    skill_name = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # Ensure it starts with a letter
    if skill_name and not skill_name[0].isalpha():
        skill_name = 'skill-' + skill_name
    return skill_name or 'unknown-skill'

def generate_skill_description(repo):
    """Generate a skill description from repository information"""
    description = (repo.get('description') or '').strip()
    if not description:
        # Fallback to repo name if no description
        description = f"A skill derived from the {repo.get('name', 'unknown')} GitHub repository"
    return description

def generate_skill_tags(repo, category_key):
    """Generate tags for the skill based on repository and category"""
    tags = [category_key.replace('-', '_')]  # Category as tag
    
    # Add language if available
    language = repo.get('language')
    if language:
        tags.append(language.lower())
    
    # Add topics as tags if available
    if 'topics' in repo and repo['topics']:
        for topic in repo['topics']:
            # Clean topic for use as tag
            clean_topic = topic.lower().replace(' ', '-').replace('/', '-')
            tags.append(clean_topic)
    
    # Add some standard tags
    tags.extend(['github-derived', 'auto-generated'])
    
    # Remove duplicates and return
    return list(dict.fromkeys(tags))  # Preserves order while removing dups

def generate_related_skills(repo, category_key):
    """Generate related skills based on repository and category"""
    related = []
    
    # Add other skills from same category as potentially related
    # (In practice, this would be smarter based on actual dependencies)
    related.append(f"{category_key}-general")
    
    # Add some standard related skills based on category
    category_relations = {
        'bitcoin-lightning': ['bitcoin-wallet', 'lightning-invoice', 'crypto-exchange'],
        'ai-ml': ['model-training', 'data-preprocessing', 'nlp-processing'],
        'privacy-security': ['encryption-tools', 'auth-management', 'secure-communication'],
        'finance-trading': ['portfolio-tracker', 'trade-executor', 'market-analyzer'],
        'development-tools': ['ci-cd-pipeline', 'testing-framework', 'package-manager'],
        'social-media': ['content-scheduler', 'analytics-dashboard', 'engagement-tracker'],
        'health-wellness': ['fitness-tracker', 'nutrition-guide', 'meditation-timer'],
        'travel-exploration': ['trip-planner', 'expense-tracker', 'itinerary-builder'],
        'voice-audio': ['speech-recognizer', 'text-to-speech', 'audio-processor'],
        'video-streaming': ['video-downloader', 'live-streamer', 'video-converter'],
        'education-learning': ['course-manager', 'quiz-generator', 'progress-tracker'],
        'gaming-entertainment': ['game-engine', 'asset-manager', 'multiplayer-handler']
    }
    
    if category_key in category_relations:
        related.extend(category_relations[category_key][:2])  # Add up to 2 related
    
    return related

def generate_features(repo):
    """Generate feature list for the skill based on repository"""
    features = []
    
    # Add repository name and URL
    repo_name = repo.get('name', 'unknown')
    repo_url = repo.get('html_url', '')
    if repo_url:
        features.append(f"Integrates with {repo_name} ({repo_url})")
    else:
        features.append(f"Derived from GitHub repository: {repo_name}")
    
    # Add description if available and meaningful
    description = (repo.get('description') or '').strip()
    if description and len(description) > 10:
        # Truncate long descriptions
        if len(description) > 200:
            description = description[:197] + "..."
        features.append(f"Provides: {description}")
    
    # Add language-specific features with more detail
    language = repo.get('language')
    if language:
        features.append(f"Implemented in {language}")
        # Add language-specific insights
        if language.lower() == 'python':
            features.append("Can be used as a Python library or package")
        elif language.lower() in ['javascript', 'typescript']:
            features.append("Available as npm/yarn package")
        elif language.lower() == 'go':
            features.append("Distributed as Go module")
        elif language.lower() == 'rust':
            features.append("Available on crates.io")
        elif language.lower() == 'java':
            features.append("Available via Maven/Gradle")
    
    # Add stars count with context
    stargazers_count = repo.get('stargazers_count', 0)
    if stargazers_count > 0:
        if stargazers_count >= 10000:
            features.append(f"Highly popular with {stargazers_count:,} GitHub stars")
        elif stargazers_count >= 1000:
            features.append(f"Well-known project with {stargazers_count:,} GitHub stars")
        elif stargazers_count >= 100:
            features.append(f"Popular repository with {stargazers_count:,} GitHub stars")
        else:
            features.append(f"Repository with {stargazers_count:,} GitHub stars")
    
    # Add fork count with context
    forks_count = repo.get('forks_count', 0)
    if forks_count > 0:
        if forks_count >= 1000:
            features.append(f"Widely forked with {forks_count:,} forks indicating community engagement")
        elif forks_count >= 100:
            features.append(f"Actively developed with {forks_count:,} forks")
        else:
            features.append(f"Repository has {forks_count:,} forks")
    
    # Add topics as features if available
    if 'topics' in repo and repo['topics']:
        topics = repo['topics'][:5]  # Limit to top 5 topics
        if topics:
            features.append(f"Related to: {', '.join(topics)}")
    
    # Add license information
    license_info = repo.get('license')
    if license_info and isinstance(license_info, dict):
        license_name = license_info.get('name')
        if license_name:
            features.append(f"Licensed under {license_name}")
    elif isinstance(license_info, str):
        features.append(f"Licensed under {license_info}")
    
    # Add repository size/context if available
    size = repo.get('size')
    if size and size > 0:
        if size > 100000:  # > 100MB
            features.append(f"Large codebase ({size} KB)")
        elif size > 10000:  # > 10MB
            features.append(f"Substantial codebase ({size} KB)")
    
    # Add watchers count if significant
    watchers_count = repo.get('watchers_count', 0)
    if watchers_count > 50:
        features.append(f"Monitored by {watchers_count:,} GitHub users")
    
    # Ensure we have at least some basic features
    if not features:
        features = [
            f"Derived from GitHub repository: {repo_name}",
            "Automatically generated by StarLearner-Nexus",
            "Ready for immediate use with Hermes Agent"
        ]
    
    return features

def generate_usage_details(repo):
    """Generate detailed usage instructions for the skill"""
    skill_name = generate_skill_name(repo)
    repo_name = repo.get('name', 'unknown')
    language = repo.get('language', '')
    
    usage = f"""# Basic Installation and Usage

```bash
# Install from your StarLearner-Nexus tap
hermes skills tap add {{ github_username }}/starlearner-nexus-hermes-skill
hermes skills install {skill_name} --tap {{ github_username }}/starlearner-nexus-hermes-skill

# Run the skill
hermes skills run {skill_name}
```

"""
    
    # Add language-specific usage if applicable
    if language:
        usage += f"""## {language}-Specific Usage

"""
        if language.lower() == 'python':
            usage += f"""This skill provides access to a Python repository. You may need to:
- Install Python dependencies: `pip install -r requirements.txt` (if present)
- Import modules in your Python code
- Run examples or tests as documented in the repository

Example:
```bash
# Clone and use the original repository
git clone {repo.get('html_url', '')}
cd {repo_name}
# Follow repository-specific setup instructions
```
"""
        elif language.lower() in ['javascript', 'typescript']:
            usage += f"""This skill provides access to a JavaScript/TypeScript repository. You may need to:
- Install Node.js dependencies: `npm install` or `yarn install`
- Build the project: `npm run build` or similar
- Use the provided CLI or API

Example:
```bash
# Clone and use the original repository
git clone {repo.get('html_url', '')}
cd {repo_name}
npm install
# Follow repository-specific usage instructions
```
"""
        elif language.lower() == 'go':
            usage += f"""This skill provides access to a Go repository. You may need to:
- Install Go (if not already installed)
- Get dependencies: `go get ./...`
- Build: `go build` or `go install`

Example:
```bash
# Clone and use the original repository
git clone {repo.get('html_url', '')}
cd {repo_name}
go get ./...
# Follow repository-specific usage instructions
```
"""
        else:
            usage += f"""This skill provides access to a {language} repository. Refer to the original repository for specific usage instructions.

Example:
```bash
# Clone and use the original repository
git clone {repo.get('html_url', '')}
cd {repo_name}
# Follow repository-specific setup and usage instructions
```
"""
    
    # Add general usage tips
    usage += f"""## General Usage Tips

- This skill provides convenient access to the {repo_name} repository within your Hermes agent ecosystem
- For advanced usage, consult the original repository documentation at: {repo.get('html_url', '')}
- Consider starring the original repository on GitHub if you find it useful
- Check the repository's issues and discussions for community support and examples

## Configuration

Some repositories may require environment variables or configuration files. Check:
- {repo.get('html_url', '')}/#readme for setup instructions
- {repo.get('html_url', '')}/wiki for detailed documentation
- {repo.get('html_url', '')}/examples for usage examples

"""
    
    return usage

def generate_installation_notes(repo):
    """Generate installation notes acknowledging potential dependencies"""
    language = repo.get('language', '')
    
    notes = f"""The {repo.get('name', 'unknown')} skill provides access to the repository within your Hermes agent.

"""
    
    if language:
        notes += f"""## Language Runtime

This skill is for a {language} repository. Depending on how you plan to use it, you may need to install:
"""
        if language.lower() == 'python':
            notes += "- Python 3.x runtime\n- Pip package manager\n- Any Python dependencies listed in requirements.txt or setup.py\n"
        elif language.lower() in ['javascript', 'typescript']:
            notes += "- Node.js runtime\n- npm or yarn package manager\n- Any Node.js dependencies in package.json\n"
        elif language.lower() == 'go':
            notes += "- Go compiler and toolchain\n- Git for fetching dependencies\n"
        elif language.lower() == 'rust':
            notes += "- Rust compiler and cargo package manager\n"
        elif language.lower() == 'java':
            notes += "- Java Development Kit (JDK)\n- Maven or Gradle build tool\n"
        else:
            notes += f"- {language} runtime and development tools\n"
    else:
        notes += "- Appropriate runtime for the repository's primary language\n"
    
    notes += f"""
## Hermes Integration

This skill is designed to work within the Hermes agent ecosystem:
- No additional Hermes installation required beyond the skill itself
- Can be combined with other Hermes skills for enhanced functionality
- Accessible to all Hermes profiles via Orchestrator delegation

## Source Verification

- Skill generated from: {repo.get('html_url', 'unknown repository')}
- Generation includes repository metadata and description
- For the most current version, refer to the original GitHub repository

## Troubleshooting

If you encounter issues:
1. Verify you have the necessary language runtimes installed
2. Check the original repository for specific setup requirements
3. Ensure your Hermes agent has internet access to fetch any needed dependencies
4. Consult the Hermes community for skill-specific usage help

"""
    
    return notes

def generate_dependencies_note(repo):
    """Generate dependencies note"""
    language = repo.get('language', '')
    
    if language:
        deps = f"""This skill provides access to a {language} repository. Actual dependencies depend on how you use the underlying repository:

"""
        if language.lower() == 'python':
            deps += "- Python runtime (version varies by repository)\n- Potential dependencies: Check requirements.txt, setup.py, or pyproject.toml in the original repository\n"
        elif language.lower() in ['javascript', 'typescript']:
            deps += "- Node.js runtime\n- Potential dependencies: Check package.json in the original repository\n"
        elif language.lower() == 'go':
            deps += "- Go compiler and toolchain\n"
        elif language.lower() == 'rust':
            deps += "- Rust compiler and cargo\n"
        elif language.lower() == 'java':
            deps += "- Java Development Kit (JDK)\n- Potential build tools: Maven or Gradle\n"
        else:
            deps += f"- {language} runtime and development tools\n"
    else:
        deps = "Dependencies vary based on the repository's primary language and intended use. Refer to the original repository for specific requirements.\n"
    
    deps += f"\nNote: This skill provides repository access within Hermes. You may need to install additional tools or libraries depending on your specific use case."
    
    return deps

def generate_skill(repo, category_key, output_dir):
    """Generate a single Hermes skill for a repository"""
    # Load template
    template_str = get_skill_template(category_key)
    template = jinja2.Template(template_str)
    
    # Prepare template variables
    skill_name = generate_skill_name(repo)
    skill_description = generate_skill_description(repo)
    tags = generate_skill_tags(repo, category_key)
    related_skills = generate_related_skills(repo, category_key)
    features = generate_features(repo)
    usage_details = generate_usage_details(repo)
    installation_notes = generate_installation_notes(repo)
    dependencies_note = generate_dependencies_note(repo)
    repo_url = repo.get('html_url', repo.get('url', ''))
    generation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    homepage = repo.get('homepage', '')
    
    # Render the template
    rendered = template.render(
        skill_name=skill_name,
        skill_description=skill_description,
        version="1.1.0",  # Updated version
        author="GitHub Community (via StarLearner-Nexus)",
        license="MIT",
        tags=tags,
        related_skills=related_skills,
        features=features,
        usage_details=usage_details,
        installation_notes=installation_notes,
        dependencies_note=dependencies_note,
        repo_url=repo_url,
        generation_date=generation_date,
        homepage=homepage,
        github_username="BigBossRabbit"  # This would ideally come from config
    )
    
    # Create output directory
    skill_output_dir = output_dir / skill_name
    skill_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write the skill file
    skill_file = skill_output_dir / "SKILL.md"
    with open(skill_file, 'w') as f:
        f.write(rendered)
    
    return skill_file

def generate_skills(input_file, output_base_dir):
    """Main function to generate skills from categorized repositories"""
    # Load categorized data
    data = load_categorized_repos(input_file)
    
    # Create output directory
    output_dir = Path(output_base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track generation stats
    stats = {
        'total_processed': 0,
        'skills_generated': 0,
        'categories': {}
    }
    
    # Process each category
    categories = data.get('categories', {})
    for category_key, repos in categories.items():
        if not repos:
            continue
           
        category_output_dir = output_dir / category_key
        category_output_dir.mkdir(parents=True, exist_ok=True)
       
        # Limit to top repositories per category to avoid too many skills
        # Sort by stars count (descending) and take top 5
        sorted_repos = sorted(
            repos, 
            key=lambda r: r.get('stargazers_count', 0), 
            reverse=True
        )[:5]
       
        category_skills = 0
        for repo in sorted_repos:
            try:
                skill_file = generate_skill(repo, category_key, category_output_dir)
                print(f"Generated skill: {skill_file}")
                category_skills += 1
                stats['skills_generated'] += 1
            except Exception as e:
                print(f"Error generating skill for {repo.get('name', 'unknown')}: {e}")
       
        stats['categories'][category_key] = {
            'repos_processed': len(sorted_repos),
            'skills_generated': category_skills
        }
        stats['total_processed'] += len(sorted_repos)
   
    # Print summary
    print("\n=== Skill Generation Summary ===")
    print(f"Total repositories processed: {stats['total_processed']}")
    print(f"Total skills generated: {stats['skills_generated']}")
    for category, cat_stats in stats['categories'].items():
        if cat_stats['skills_generated'] > 0:
            print(f"  {category}: {cat_stats['skills_generated']}/{cat_stats['repos_processed']} skills")
   
    return stats

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate_skills.py <input_json> <output_directory>")
        sys.exit(1)
   
    input_file = sys.argv[1]
    output_dir = sys.argv[2]
   
    generate_skills(input_file, output_dir)