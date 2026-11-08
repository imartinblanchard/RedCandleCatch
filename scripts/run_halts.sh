#!/usr/bin/env bash
# Capture les arrêts de cotation (trade halts) Nasdaq du JOUR COURANT.
# Le flux RSS NasdaqTrader est GLISSANT (~23 derniers halts) : on l'interroge plusieurs
# fois PENDANT la séance (cron */15 9-16 ET) pour ne rien rater ; le collecteur est
# idempotent (merge + dédup dans halts-YYYY-MM-DD.json). Pas besoin d'IBKR.
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
mkdir -p data/collected_live
echo "=== $(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z') fetch_halts ===" >> data/collected_live/halts.log
python -m bot.fetch_halts >> data/collected_live/halts.log 2>&1
