#!/usr/bin/env bash
# Daily entry point for cron/launchd: send the snapshot and regenerate html/ locally.
# Publishing to GitHub Pages is disabled; run ./publish_pages.sh manually to re-enable.
set -uo pipefail
cd "$(dirname "$0")"
# app_secrets.py treats ENV=DEV (the default) as TEST_MODE; cron must send for real.
export ENV="${ENV:-PROD}"
source venv/bin/activate
python financial_snapshot.py
