#!/bin/bash
# run_starlearner_3day.sh
# Runs the StarLearner-Nexus skill every 3rd day.
# Cron fires this daily; the state file gates execution to once per 3 days.
# stdout carries ONLY a compact summary line (cron delivers it to Telegram).

set -euo pipefail

REPO="/Users/fromthejump/starlearner-nexus-hermes-skill"
STATE="$REPO/.last_sync_ts"
LOG="$REPO/logs/starlearner-$(date +%Y%m%d).log"
NOW=$(date +%s)
INTERVAL_SEC=$((3 * 24 * 60 * 60))

# Read last run timestamp (0 if never)
LAST=0
[ -f "$STATE" ] && LAST=$(cat "$STATE" 2>/dev/null || echo 0)

# Gate: run only if 3+ days elapsed
if [ -n "$LAST" ] && [ "$LAST" -gt 0 ]; then
  ELAPSED=$((NOW - LAST))
  if [ "$ELAPSED" -lt "$INTERVAL_SEC" ]; then
    NEXT=$((LAST + INTERVAL_SEC - NOW))
    DAYS=$((NEXT / 86400)); HRS=$(((NEXT % 86400) / 3600))
    echo "⏳ StarLearner skip — next run in ~${DAYS}d ${HRS}h (every 3 days)"
    exit 0
  fi
fi

# Record timestamp BEFORE running so a mid-run failure doesn't cause a tight retry loop
echo "$NOW" > "$STATE"

# Run the full pipeline
echo "🚀 StarLearner-Nexus sync started $(date '+%Y-%m-%d %H:%M')"
bash "$REPO/scripts/daily_sync.sh" > "$LOG" 2>&1

# Compact summary (single line for Telegram)
REPOS=$(grep -oE "Fetched: [0-9]+" "$LOG" | tail -1 | grep -oE "[0-9]+" || echo "?")
SKILLS=$(find "$REPO/generated_skills" -name SKILL.md -type f 2>/dev/null | wc -l | tr -d ' ')
echo "✅ StarLearner sync done — ${REPOS} repos · ${SKILLS} skills · log $LOG"
