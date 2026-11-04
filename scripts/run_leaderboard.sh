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
# Régénère l'univers PM-liquidité (sinon les stratégies INDICATEURS du leaderboard restent figées
# à la dernière date du CSV -> vwap/bb ne reflètent pas les nouveaux jours). DOIT précéder le leaderboard unifié.
"$PROJ/.venv/bin/python" -m research.live_lab.studies.build_liquid_universe_pm >> "$LOG" 2>&1 \
  && log "univers PM-liquidité régénéré (liquid_universe_pm.csv)" || log "⚠️ échec rebuild univers PM"
# Leaderboard UNIFIÉ (toutes familles : repli + indicateurs) -> leaderboard_all_latest.csv + _history.csv
# --no-persist = aperçu RAPIDE (le walk-forward de persistance, ~7min, est refait au complet à 19:30
# par run_full_search.sh, APRÈS la recherche du soir qui rafraîchit les CSV sources).
"$PROJ/.venv/bin/python" research/core/leaderboard_all.py --no-persist >> "$LOG" 2>&1 \
  && log "leaderboard unifié mis à jour, aperçu rapide (core/leaderboard_all_*.csv)" || log "⚠️ échec leaderboard unifié"
# Régénère le visuel HTML autonome (research/live_lab/leaderboard.html) depuis le CSV frais.
"$PROJ/.venv/bin/python" research/live_lab/render_leaderboard_html.py >> "$LOG" 2>&1 \
  && log "visuel HTML régénéré" || log "⚠️ échec rendu visuel HTML"
log "=== terminé ==="
