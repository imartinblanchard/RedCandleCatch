#!/usr/bin/env bash
# Tire les bougies 1-min IBKR de l'univers capté en direct (après la clôture).
# Appelé par cron. Log dans data/collected_live/fetch.log.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
mkdir -p data/collected_live
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') fetch_universe_bars ===" >> data/collected_live/fetch.log
python -m bot.fetch_universe_bars >> data/collected_live/fetch.log 2>&1
