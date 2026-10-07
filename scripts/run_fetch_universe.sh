#!/usr/bin/env bash
# Tire les bougies 1-min IBKR de l'univers capté en direct (après la clôture).
# Appelé par cron. Log dans data/collected_live/fetch.log.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
mkdir -p data/collected_live
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') fetch_universe_bars ===" >> data/collected_live/fetch.log
python -m bot.fetch_universe_bars >> data/collected_live/fetch.log 2>&1

# News Yahoo (horodatée) du même univers — indépendant d'IBKR, doit tourner LE JOUR MÊME.
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') fetch_universe_news ===" >> data/collected_live/fetch.log
python -m bot.fetch_universe_news >> data/collected_live/fetch.log 2>&1

# Bougies 15s PRÉ-MARCHÉ des gappers >=10% (étude momentum PM). Besoin IBKR (port 4001).
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') fetch_pm15s (>=10%) ===" >> data/collected_live/fetch.log
python -m bot.fetch_pm15s --min-band 10 >> data/collected_live/fetch.log 2>&1
