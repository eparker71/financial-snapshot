#!/usr/bin/env bash
# Daily entry point for cron/launchd: send the snapshot, then publish the dashboard.
set -uo pipefail
cd "$(dirname "$0")"
source venv/bin/activate
python financial_snapshot.py && ./publish_pages.sh
