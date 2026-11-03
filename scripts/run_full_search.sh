#!/usr/bin/env bash
# Recherche COMPLÈTE quotidienne : teste TOUTES les combinaisons sur TOUTE la data accumulée,
# chaque univers-jour en point-in-time (chaque ticker-jour avec SON univers du jour).
#   - strategy_search_full    : ~23 000 combos famille REPLI (gap×heure×repli×capit×sortie×indic)
#   - indicator_lab/search    : ~540 combos famille INDICATEURS (10 archétypes × grilles)
# Appelé par cron en semaine, APRÈS le leaderboard de 18:20 (qui régénère l'univers PM que la
# recherche indicateurs utilise). ⚠️ data courte + dizaines de milliers de combos = FAUX POSITIFS
# énormes : lire la PERSISTANCE dans le temps + la robustesse (t-stat, non-fragile), JAMAIS un
# gagnant isolé. Résultats -> research/*/results/*.csv (relus par le leaderboard/analyses).
set -uo pipefail
PROJ="/home/martin/dev/stock-journal-long"
PY="$PROJ/.venv/bin/python"
LOG="$PROJ/data/collected_live/full_search_cron.log"
ts(){ TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z'; }
log(){ echo "$(ts) $*" >> "$LOG"; }

cd "$PROJ" || exit 1
log "=== recherche complète quotidienne (repli ~23k + indicateurs ~540) ==="
"$PY" -m research.live_lab.studies.strategy_search_full >> "$LOG" 2>&1 \
  && log "strategy_search_full OK" || log "⚠️ échec strategy_search_full"
"$PY" -m research.indicator_lab.search >> "$LOG" 2>&1 \
  && log "indicator_lab search OK" || log "⚠️ échec indicator_lab search"
# PERSISTANCE walk-forward : quelles combos robustes RESTENT en haut au fil des séances (vs bruit)
"$PY" -m research.live_lab.studies.track_robust >> "$LOG" 2>&1 \
  && log "persistance robuste mise à jour (robust_persistence.csv)" || log "⚠️ échec track_robust"
log "=== terminé ==="
