#!/usr/bin/env bash
# Watchdog IB Gateway.
# Surveille le PORT 4001 (pas le process : lors du reset hebdo IBKR le Java reste
# vivant mais bloqué LOGGED_OUT, donc Restart=always de systemd ne voit rien).
# Si le port est fermé STRIKES_NEEDED ticks de suite -> restart ibgw.service.
# Notifie Discord si DISCORD_WEBHOOK est défini dans .env.
set -uo pipefail

PROJ="/home/martin/dev/stock-journal-long"
PORT=4001
STATE="/tmp/ibgw_watchdog.state"
LOG="$PROJ/data/collected_live/watchdog.log"
STRIKES_NEEDED=2          # 2 ticks (~10 min) avant d'agir : ignore le blip du restart quotidien 20:05

ts()  { date '+%Y-%m-%d %H:%M:%S %Z'; }
log() { echo "$(ts) $*" >> "$LOG"; }

notify() {
  local url=""
  if [ -f "$PROJ/.env" ]; then
    url=$(grep -E '^DISCORD_WEBHOOK=' "$PROJ/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\' )
  fi
  [ -n "$url" ] || return 0
  curl -sf -m 10 -H 'Content-Type: application/json' \
       -d "{\"content\": \"$1\"}" "$url" >/dev/null 2>&1 || true
}

port_up() { ss -tln 2>/dev/null | grep -q ":$PORT "; }

if port_up; then
  [ -f "$STATE" ] && rm -f "$STATE"
  exit 0
fi

# Port fermé : compter les strikes consécutifs.
strikes=0
[ -f "$STATE" ] && strikes=$(cat "$STATE" 2>/dev/null || echo 0)
strikes=$((strikes + 1))
echo "$strikes" > "$STATE"
log "port $PORT FERMÉ (strike $strikes/$STRIKES_NEEDED)"
[ "$strikes" -lt "$STRIKES_NEEDED" ] && exit 0   # attendre confirmation

log "redémarrage ibgw.service (port fermé $strikes ticks)"
notify "⚠️ IB Gateway : port $PORT fermé — restart automatique du watchdog ($(ts))"
systemctl --user restart ibgw.service
rm -f "$STATE"

# Vérifier le retour du port (jusqu'à ~2 min, le temps du boot + relogin).
for _ in $(seq 1 24); do
  sleep 5
  if port_up; then
    log "✅ reconnecté après restart"
    notify "✅ IB Gateway : reconnecté, port $PORT ouvert ($(ts))"
    exit 0
  fi
done
log "❌ toujours fermé après restart — intervention requise (2FA ?)"
notify "🔴 IB Gateway : TOUJOURS déconnecté après restart auto — intervention manuelle requise (2FA ?) ($(ts))"
exit 1
