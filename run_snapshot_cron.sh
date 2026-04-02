#!/bin/bash
#set -euo pipefail

# API keys
export AGENTMAIL_API_KEY="am_us_f27ae9c82876ff5a2f35e4aeb3239069258a1f30e990741bf77903eae95fd282"
export AGENTMAIL_INBOX_ID="disturbedrate918@agentmail.to"
export EIA_API_KEY="fPua9sLk01qyUQwRnT9FNexqWoIw2x0oWmeLZn7X"
export FRED_API_KEY="5f97f476af8e786f7c6ce232f676f588"

# Paths and environment
export ROOT="/Users/eric/Desktop/openclaw_backup"
export VENV="$ROOT/venv"
export PY="$VENV/bin/python"
export LOG_FILE="$ROOT/financial_snapshot.log"

#echo "Cron works! $(date)" >> /Users/eric/Desktop/openclaw_backup/cron_test.log

echo "running snapshot cron with environment variables:" >> "$LOG_FILE"
echo "$PY /Users/eric/Desktop/openclaw_backup/financial_snapshot.py" >> "$LOG_FILE"
$PY /Users/eric/Desktop/openclaw_backup/financial_snapshot.py
