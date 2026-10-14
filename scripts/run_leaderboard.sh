#!/usr/bin/env bash
# Lance le leaderboard APRÈS s'être assuré que le fetch du jour est TERMINÉ.
# Protection : on attend que bars-<jour>.parquet existe ET soit STABLE (non modifié
# depuis STABLE_SEC) = l'écriture du fetch est finie. Sinon, après DEADLINE, on
# s'abstient (pas de classement sur données incomplètes). Appelé par cron en semaine.
set -uo pipefail

PROJ="/home/martin/dev/stock-journal-long"
TODAY="$(TZ=America/New_York date +%F)"
BARS="$PROJ/data/collected_live/bars-$TODAY.parquet"
LOG="$PROJ/data/collected_live/leaderboard_cron.log"
STABLE_SEC=90                 # fichier inchangé depuis 90s = fetch fini
DEADLINE=$(( $(date +%s) + 5400 ))   # attente max 90 min

ts(){ TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z'; }
log(){ echo "$(ts) $*" >> "$LOG"; }

log "=== run_leaderboard : attente du fetch ($TODAY) ==="
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if [ -f "$BARS" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$BARS") ))
    if [ "$age" -ge "$STABLE_SEC" ]; then
      log "bars du jour présent et stable (${age}s) -> fetch terminé"
      break
    fi
    log "bars présent mais encore en écriture (${age}s < ${STABLE_SEC}s), on patiente"
  fi
  sleep 60
done

if [ ! -f "$BARS" ]; then
  log "ABANDON : bars-$TODAY absent après le délai (fetch non fait / jour férié ?). Leaderboard NON lancé."
  exit 0
fi

log "lancement du leaderboard"
cd "$PROJ" || exit 1
"$PROJ/.venv/bin/python" research/live_lab/leaderboard.py >> "$LOG" 2>&1
log "=== terminé ==="
