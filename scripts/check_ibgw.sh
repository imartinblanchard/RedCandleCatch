#!/usr/bin/env bash
# Vérifie l'état d'IB Gateway + de l'API après un (re)démarrage.
# Usage : bash scripts/check_ibgw.sh
# Contexte : voir la mémoire ibgw-login-fix-2026-09-24 (update 10.41->10.51, IBC 3.24.2).
set -uo pipefail
cd "$(dirname "$0")/.."

echo "=== 1) Process IB Gateway (java) ==="
GW=0
for p in $(pgrep -x java 2>/dev/null); do
  tr '\0' ' ' </proc/$p/cmdline 2>/dev/null | grep -q ibgateway && { echo "  ✅ Gateway vivant: PID $p ($(ps -o etimes= -p $p 2>/dev/null | tr -d ' ')s)"; GW=1; }
done
[ $GW -eq 0 ] && echo "  ❌ aucun Gateway (lance: start_ibgw   — UNE seule fois, puis approuve la 2FA)"

echo "=== 2) Port API en écoute ==="
PORT=$(ss -tln 2>/dev/null | grep -oE ':400[0-9]' | sort -u | tr -d ':' | head -1)
if [ -n "$PORT" ]; then echo "  ✅ écoute sur port $PORT"; else echo "  ❌ aucun port 400x (Gateway pas encore loggé)"; PORT=4001; fi

echo "=== 3) Test connexion API (ib_insync) ==="
source .venv/bin/activate 2>/dev/null
for TRY in ${PORT} 4001 4000; do
  timeout 25 python - "$TRY" <<'PY' && break
import sys
from ib_insync import IB
port=int(sys.argv[1]); ib=IB()
try:
    ib.connect('127.0.0.1', port, clientId=91, timeout=12)
    print(f"  ✅ CONNECTÉ sur {port} — comptes={ib.managedAccounts()} serverVersion={ib.client.serverVersion()}")
    ib.disconnect(); sys.exit(0)
except Exception as e:
    print(f"  ❌ {port}: {type(e).__name__}: {e}"); sys.exit(1)
PY
done

echo "=== RAPPEL ==="
echo "  Le bot attend le port 4001. Si l'API répond sur 4000, dis-le à Claude"
echo "  (1 ligne à aligner : jts.ini LocalServerPort ou le port du bot)."
