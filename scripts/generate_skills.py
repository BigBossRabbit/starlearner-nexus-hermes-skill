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
    return '''---
name: {{ skill_name }}
description: "{{ skill_description }}"
version: "{{ version }}"
author: "{{ author }}"
license: "{{ license }}"
tags: {{ tags | tojson }}
related_skills: {{ related_skills | tojson }}
---
# {{ skill_name }}

{{ skill_description }}

## Features
{% for feature in features %}
- {{ feature }}
{% endfor %}

## Usage
```bash
# Example usage
{{ usage_example }}
```

## Installation
The skill is ready to use! No additional installation required.
```

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
    description = repo.get('description', '').strip()
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
    features = [
        "Derived from GitHub repository: {}".format(repo.get('name', 'unknown')),
        "Automatically generated by StarLearner-Nexus",
        "Ready for immediate use with Hermes Agent"
    ]
    
    # Add language-specific features
    language = repo.get('language')
    if language:
        features.append(f"Primarily uses {language} language")
    
    # Add stars count if available and significant
    stargazers_count = repo.get('stargazers_count', 0)
    if stargazers_count > 10:
        features.append(f"Popular repository with {stargazers_count} GitHub stars")
    
    # Add fork count if significant
    forks_count = repo.get('forks_count', 0)
    if forks_count > 5:
        features.append(f"Active repository with {forks_count} forks")
    
    return features

def generate_usage_example(repo):
    """Generate a usage example for the skill"""
    skill_name = generate_skill_name(repo)
    return f"hermes skills run {skill_name}"

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
    usage_example = generate_usage_example(repo)
    
    # Render the template
    rendered = template.render(
        skill_name=skill_name,
        skill_description=skill_description,
        version="1.0.0",
        author="GitHub Community (via StarLearner-Nexus)",
        license="MIT",
        tags=tags,
        related_skills=related_skills,
        features=features,
        usage_example=usage_example
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