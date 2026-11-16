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

# NB : la recherche tourne sur l'univers LARGE 3-500 (bars-*.parquet via fetch_universe_bars
# ci-dessus) = TOUS les gappers, pas seulement ceux qu'on trade (choix Martin 15/11). Le
# fetch_eligible_bars (bars_eligible, sous-ensemble tradé) est retiré du cron -> audit manuel
# seulement : python -m bot.fetch_eligible_bars --date YYYY-MM-DD

# Leaderboard NIGHTLY sur l'univers large (évolue chaque soir). Pas d'IBKR (relit le parquet).
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') nightly_real_leaderboard ===" >> data/collected_live/fetch.log
python -m research.live_lab.nightly_real_leaderboard >> data/collected_live/fetch.log 2>&1
