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

# ===== DÉSACTIVÉ le 05/11 (ménage) : les recherches (strategy_search_full, indicator_lab.search,
# track_robust, leaderboard_all) sont en QUARANTAINE, on rebâtit l'analyse sur base réduite
# d'indicateurs. Ce script est un no-op tant que les nouvelles recherches ne sont pas prêtes. =====
log "recherche DÉSACTIVÉE (ménage 05/11, modules en quarantaine) -> no-op"
exit 0

cd "$PROJ" || exit 1
# VERROU anti-empilement : avec la dimension seuil-PM (04/11), un run peut dépasser 24h et déborder
# sur le cron du lendemain. flock -n => si un run précédent tourne encore, on SKIP (pas 2 en //).
LOCK="$PROJ/data/collected_live/.full_search.lock"
exec 9>"$LOCK"
if ! flock -n 9; then log "⏭️  run précédent encore EN COURS -> skip (évite 2 recherches en parallèle)"; exit 0; fi
log "=== recherche complète quotidienne (repli + indicateurs, dimension seuil-PM) ==="
"$PY" -m research.live_lab.studies.strategy_search_full >> "$LOG" 2>&1 \
  && log "strategy_search_full OK" || log "⚠️ échec strategy_search_full"
"$PY" -m research.indicator_lab.search >> "$LOG" 2>&1 \
  && log "indicator_lab search OK" || log "⚠️ échec indicator_lab search"
# PERSISTANCE walk-forward : quelles combos robustes RESTENT en haut au fil des séances (vs bruit)
"$PY" -m research.live_lab.studies.track_robust >> "$LOG" 2>&1 \
  && log "persistance robuste mise à jour (robust_persistence.csv)" || log "⚠️ échec track_robust"
# Rafraîchit le leaderboard unifié APRÈS les recherches (pour qu'il intègre le top du soir, pas la veille)
"$PY" research/core/leaderboard_all.py >> "$LOG" 2>&1 \
  && log "leaderboard unifié rafraîchi (post-recherche)" || log "⚠️ échec leaderboard post-recherche"
log "=== terminé ==="
