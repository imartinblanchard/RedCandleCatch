#!/usr/bin/env bash
# Appelé par cron le SOIR (20:30 ET, après l'after-hours) : capture le follow-through
# (jour N + jour N+1 complets, 1-min, after-hours inclus) de l'univers du jour de bourse
# PRÉCÉDENT. Permet d'étudier le maintien d'une position au-delà de la clôture.
cd /home/martin/dev/stock-journal-long || exit 1
echo "=== $(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z') run_followthrough ===" >> data/collected_live/followthrough.log
/home/martin/dev/stock-journal-long/.venv/bin/python -m bot.fetch_followthrough >> data/collected_live/followthrough.log 2>&1
