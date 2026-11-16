#!/usr/bin/env bash
# Recherche nightly — PLACEHOLDER (16/11).
# Les anciennes recherches (strategy_search_full, indicator_lab.search, track_robust,
# leaderboard_all) sont en QUARANTAINE. Le nouveau pipeline en construction :
#   - gros GÉNÉRATEUR de stratégies (occasionnel, lancé à la main) -> liste courte robuste
#   - nightly : re-test de la liste courte sur la data accumulée (à brancher ici)
# No-op tant que la liste courte n'est pas prête.
set -uo pipefail
PROJ="/home/martin/dev/stock-journal-long"
LOG="$PROJ/data/collected_live/full_search_cron.log"
echo "$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z') recherche nightly = no-op (générateur en construction)" >> "$LOG"
exit 0
