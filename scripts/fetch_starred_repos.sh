#!/bin/bash
# fetch_starred_repos.sh
# Fetches starred repositories from GitHub and saves them to a JSON file

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../data"
OUTPUT_FILE="$DATA_DIR/starred_repos.json"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

# Ensure data directory exists
mkdir -p "$DATA_DIR"

# Check if GitHub CLI is available and authenticated
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    echo "Using GitHub CLI to fetch starred repositories..."
    gh api --paginate user/starred > "$OUTPUT_FILE"
elif [ -n "$GITHUB_TOKEN" ]; then
    echo "Using GitHub API with personal access token..."
    PAGE=1
    : > "$OUTPUT_FILE"
    while : ; do
        BODY=$(curl -s -f -H "Authorization: Bearer ${GITHUB_TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/user/starred?page=${PAGE}&per_page=100" || true)
        if [ -z "$BODY" ] || [ "$(echo "$BODY" | jq 'type')" != '"array"' ]; then
            break
        fi
        echo "$BODY" | jq -c '.[]' >> "$OUTPUT_FILE"
        COUNT=$(echo "$BODY" | jq length)
        if [ "$COUNT" -lt 100 ]; then break; fi
        PAGE=$((PAGE+1))
    done
    cat "$OUTPUT_FILE" | jq -s '.' > "$OUTPUT_FILE.tmp" && mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"
else
    echo "Error: Neither GitHub CLI (gh) nor GITHUB_TOKEN environment variable available."
    echo "Please either:"
    echo "  1. Install GitHub CLI and run 'gh auth login'"
    echo "  2. Set GITHUB_TOKEN environment variable with a personal access token"
    exit 1
fi

# Validate output
if [ ! -s "$OUTPUT_FILE" ]; then
    echo "Error: No data retrieved from GitHub"
    exit 1
fi

REPO_COUNT=$(jq length "$OUTPUT_FILE")
echo "Successfully fetched $REPO_COUNT starred repositories"
echo "Data saved to: $OUTPUT_FILE"