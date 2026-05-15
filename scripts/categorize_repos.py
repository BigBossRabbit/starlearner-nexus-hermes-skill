#!/usr/bin/env python3
# categorize_repos.py
# Categorizes GitHub starred repositories by domain using keyword matching

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

# Add the skill directory to path for imports
SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILL_DIR))

def load_categories():
    """Load domain categories and keywords from references"""
    categories_file = SKILL_DIR / "references" / "categories.json"
    if categories_file.exists():
        with open(categories_file, 'r') as f:
            return json.load(f)
    else:
        # Default categories if file doesn't exist yet
        return {
            "bitcoin-lightning": {
                "name": "Bitcoin & Lightning Network",
                "keywords": ["bitcoin", "btc", "lightning", "ln", "satoshi", "wallet", 
                           "node", "lnd", "clightning", "eclair", "bolt", "invoice", 
                           "payment", "channel", "routing", "taproot", "segwit"],
                "icon": "💰"
            },
            "ai-ml": {
                "name": "AI & Machine Learning",
                "keywords": ["ai", "artificial intelligence", "machine learning", "ml", 
                           "deep learning", "neural network", "nlp", "computer vision", 
                           "tensorflow", "pytorch", "keras", "scikit-learn", "model", 
                           "training", "inference", "llm", "gpt", "bert"],
                "icon": "🤖"
            },
            "privacy-security": {
                "name": "Privacy & Security",
                "keywords": ["privacy", "security", "encryption", "cryptography", "hash", 
                           "ssl", "tls", "vpn", "tor", "anonymous", "zero knowledge", 
                           "zkp", "secure", "auth", "oauth", "jwt", "password", 
                           "firewall", "ids", "ips", "malware", "antivirus"],
                "icon": "🔒"
            },
            "finance-trading": {
                "name": "Finance & Trading",
                "keywords": ["finance", "financial", "trading", "trade", "stock", "crypto", 
                           "defi", "dex", "exchange", "wallet", "portfolio", "analytics", 
                           "quantitative", "algo", "algorithm", "backtest", "ohlc", 
                           "candlestick", "forex", "fx", "banking", "payment", "invoice"],
                "icon": "📈"
            },
            "development-tools": {
                "name": "Development Tools",
                "keywords": ["devops", "ci/cd", "pipeline", "build", "test", "testing", 
                           "framework", "library", "sdk", "api", "cli", "ide", "editor", 
                           "debugger", "profiler", "linter", "formatter", "package", 
                           "dependency", "maven", "gradle", "npm", "yarn", "pip", 
                           "docker", "kubernetes", "k8s", "container", "orchestration"],
                "icon": "🛠️"
            },
            "social-media": {
                "name": "Social Media",
                "keywords": ["social", "media", "facebook", "twitter", "x", "instagram", 
                           "tiktok", "linkedin", "youtube", "reddit", "discord", 
                           "slack", "messaging", "chat", "forum", "community", 
                           "network", "sharing", "content", "influencer", "marketing"],
                "icon": "📱"
            },
            "health-wellness": {
                "name": "Health & Wellness",
                "keywords": ["health", "wellness", "fitness", "exercise", "workout", 
                           "nutrition", "diet", "medical", "healthcare", "hospital", 
                           "clinic", "telemedicine", "mental health", "therapy", 
                           "meditation", "mindfulness", "sleep", "vitamin", "supplement"],
                "icon": "❤️"
            },
            "travel-exploration": {
                "name": "Travel & Exploration",
                "keywords": ["travel", "trip", "tourism", "flight", "hotel", "booking", 
                           "navigation", "map", "gps", "geolocation", "trail", "hiking", 
                           "camping", "adventure", "explore", "guide", "itinerary", 
                           "vacation", "holiday", "destination", "itinerary"],
                "icon": "✈️"
            },
            "voice-audio": {
                "name": "Voice & Audio",
                "keywords": ["voice", "audio", "speech", "tts", "stt", "text-to-speech", 
                           "speech-to-text", "recognize", "synthesize", "vocoder", 
                           "audio processing", "sound", "music", "dsp", "filter", 
                           "equalizer", "mixer", "recorder", "podcast", "audiobook"],
                "icon": "🎙️"
            },
            "video-streaming": {
                "name": "Video & Streaming",
                "keywords": ["video", "stream", "streaming", "youtube", "twitch", 
                           "videoconference", "meeting", "call", "livestream", 
                           "broadcast", "encoding", "decoding", "codec", "h264", 
                           "h265", "vp9", "av1", "rtmp", "webrtc", "ffmpeg", "gstreamer", 
                           "transcode", "mux", "demux", "subtitle", "caption"],
                "icon": "🎥"
            },
            "education-learning": {
                "name": "Education & Learning",
                "keywords": ["education", "learning", "tutorial", "course", "lesson", 
                           "training", "workshop", "guide", "documentation", "ebook", 
                           "mooc", "curriculum", "syllabus", "quiz", "assignment", 
                           "homework", "exam", "test", "certification", "certify", 
                           "skill", "knowledge", "academy", "university", "college"],
                "icon": "📚"
            },
            "gaming-entertainment": {
                "name": "Gaming & Entertainment",
                "keywords": ["game", "gaming", "player", "multiplayer", "singleplayer", 
                           "2d", "3d", "unity", "unreal", "engine", "physics", 
                           "rendering", "graphics", "shader", "texture", "model", 
                           "animation", "sprite", "tile", "level", "world", "scene", 
                           "quest", "level", "score", "leaderboard", "achievement"],
                "icon": "🎮"
            }
        }

def load_starred_repos(input_file):
    """Load starred repositories from JSON file"""
    with open(input_file, 'r') as f:
        return json.load(f)

def categorize_repo(repo, categories):
    """Categorize a single repository based on its attributes"""
    # Extract searchable text from repository
    searchable_text = f"{repo.get('name', '')} {repo.get('description', '') or ''} {repo.get('language', '') or ''}".lower()
    
    # Add topics if available
    if 'topics' in repo and repo['topics']:
        searchable_text += ' ' + ' '.join(repo['topics']).lower()
    
    # Score each category
    category_scores = defaultdict(int)
    
    for category_key, category_data in categories.items():
        keywords = category_data.get('keywords', [])
        for keyword in keywords:
            if keyword.lower() in searchable_text:
                category_scores[category_key] += 1
    
    # Return the category with highest score, or 'uncategorized' if no matches
    if category_scores:
        return max(category_scores.items(), key=lambda x: x[1])[0]
    else:
        return 'uncategorized'

def categorize_repos(input_file, output_file):
    """Main function to categorize all starred repositories"""
    # Load categories
    categories = load_categories()
    
    # Load repositories
    repos = load_starred_repos(input_file)
    
    # Categorize each repository
    categorized = defaultdict(list)
    uncategorized = []
    
    for repo in repos:
        category = categorize_repo(repo, categories)
        if category == 'uncategorized':
            uncategorized.append(repo)
        else:
            categorized[category].append(repo)
    
    # Prepare output data
    output_data = {
        "metadata": {
            "total_repos": len(repos),
            "categorized_count": sum(len(repos) for repos in categorized.values()),
            "uncategorized_count": len(uncategorized),
            "categories": {key: data["name"] for key, data in categories.items() if key != 'uncategorized'}
        },
        "categories": dict(categorized),
        "uncategorized": uncategorized
    }
    
    # Save results
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    # Print summary
    print(f"Categorized {output_data['metadata']['categorized_count']} repositories")
    print(f"Uncategorized: {output_data['metadata']['uncategorized_count']} repositories")
    
    for category_key, repos in categorized.items():
        if repos:
            category_name = categories[category_key]["name"]
            print(f"  {category_name}: {len(repos)} repos")
    
    if uncategorized:
        print(f"  Uncategorized: {len(uncategorized)} repos")
    
    return output_data

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python categorize_repos.py <input_json> <output_json>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    categorize_repos(input_file, output_file)