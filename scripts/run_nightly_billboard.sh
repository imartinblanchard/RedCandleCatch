#!/usr/bin/env bash
# Billboard nightly (~20:00, jours de bourse) : rafraîchit les fichiers de bande avec le jour,
# teste toutes les configs sur LA journée (incrémental), append daily-stats, recompose le billboard.
# Le fetch des chandelles est fait par run_fetch_universe.sh (16:20) ; ici on vérifie juste qu'il est là.
set -uo pipefail
PROJ=/home/martin/dev/stock-journal-long
cd "$PROJ"
LOG="$PROJ/data/collected_live/billboard_cron.log"
TODAY=$(TZ=America/New_York date +%F)
{
  echo "=== $(TZ=America/New_York date '+%F %T %Z') nightly_billboard $TODAY ==="
  if [ ! -f "data/collected_live/bars-$TODAY.parquet" ]; then
    echo "bars-$TODAY absent -> skip (jour férié ou fetch 16:20 non fait)"
    exit 0
  fi
  "$PROJ/.venv/bin/python" research/live_lab/build_bands.py \
    && "$PROJ/.venv/bin/python" -m research.live_lab.nightly_billboard --date "$TODAY"
  echo "--- réconciliation (attendus vs réels) ---"
  "$PROJ/.venv/bin/python" -m research.live_lab.reconcile_live --date "$TODAY"
  echo "=== fini $(TZ=America/New_York date '+%T %Z') ==="
} >> "$LOG" 2>&1
