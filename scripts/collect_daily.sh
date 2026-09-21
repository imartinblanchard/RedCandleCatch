#!/usr/bin/env bash
# Collecte quotidienne du dataset de recherche (tous les éligibles PM + post-open).
# Lancé par cron chaque matin ET ; collecte TOUS les jours éligibles non encore faits
# (self-healing : rattrape automatiquement un jour manqué).
set -euo pipefail
cd /home/martin/dev/stock-journal-long
mkdir -p data/collected
echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
.venv/bin/python -m bot.collect_eligibles
