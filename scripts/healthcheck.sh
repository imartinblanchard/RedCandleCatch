#!/usr/bin/env bash
# Vérifie l'état de tout le système RedCandleCatch. Lancer : ./scripts/healthcheck.sh
cd "$(dirname "$0")/.."
PY=.venv/bin/python
ok(){ echo "  ✅ $1"; }
warn(){ echo "  ⚠️  $1"; }
bad(){ echo "  ❌ $1"; }
TODAY=$(TZ=America/New_York date +%Y-%m-%d)

echo "══════════════════════════════════════════════════════════"
echo " HEALTHCHECK RedCandleCatch — $(TZ=America/New_York date '+%Y-%m-%d %H:%M ET')"
echo "══════════════════════════════════════════════════════════"

echo "▸ 1. IB Gateway (port 4001)"
if ss -tlnp 2>/dev/null | grep -q ":4001"; then ok "4001 en écoute"; else bad "4001 PAS en écoute (Gateway down/bloquée)"; fi

echo "▸ 2. Process du bot"
pgrep -f "redcandlecatch_dashboard" >/dev/null && ok "dashboard tourne (PID $(pgrep -f redcandlecatch_dashboard|head -1))" || warn "dashboard ARRÊTÉ"
pgrep -f "redcandlecatch_terminator" >/dev/null && ok "terminator tourne (PID $(pgrep -f redcandlecatch_terminator|head -1))" || warn "terminator ARRÊTÉ"

echo "▸ 3. Modules Python (imports)"
$PY -c "import bot.redcandlecatch_terminator, bot.redcandlecatch_scan, bot.redcandlecatch_dashboard, bot.eligible, bot.collect_eligibles" 2>/dev/null && ok "tous les modules importent" || bad "ERREUR d'import (voir: $PY -c 'import bot.redcandlecatch_terminator')"

echo "▸ 4. Config live (constantes)"
$PY - <<'PY' 2>/dev/null
import bot.redcandlecatch_terminator as t, bot.redcandlecatch_scan as s
print(f"  • univers     : {'POST-OPEN seulement' if not t.TRADE_PM else 'PM + post-open'} (TRADE_PM={t.TRADE_PM})")
print(f"  • gap / prix  : {s.GAP_MIN:.0f}-{s.GAP_MAX:.0f}% / {s.PRICE_MIN:.0f}-{s.PRICE_MAX:.0f}$")
print(f"  • liq scanner : {'ON '+str(s.MIN_DOLLAR_VOL) if s.ENABLE_LIQUIDITY else 'OFF (désactivé)'}")
print(f"  • dip         : PM -{t.DIP*100:.0f}% / post-open -{t.DIP_LIQUID*100:.1f}%")
print(f"  • liq bougie  : >= ${t.MIN_DIP_DOLLAR_VOL/1e3:.0f}K")
print(f"  • activation  : PM +{t.ACTIVATE_PM*100:.0f}% / post-open +{t.ACTIVATE_POST*100:.0f}%")
print(f"  • stop/trail  : -{t.STOP*100:.0f}% / {t.TRAIL*100:.0f}% | {t.SHARES} action(s) | sortie {t.HARD_EXIT[0]}:{t.HARD_EXIT[1]:02d}")
PY

echo "▸ 5. Fichiers de données"
[ -f data/computed/redcandlecatch-journal.csv ] && ok "journal ($(($(wc -l < data/computed/redcandlecatch-journal.csv)-1)) trades)" || bad "journal ABSENT"
[ -f data/collected/eligibles.csv ] && ok "eligibles.csv ($(($(wc -l < data/collected/eligibles.csv)-1)) ticker-jours)" || warn "eligibles.csv absent"
POS=$($PY -c "import json;print(len(json.load(open('data/computed/redcandlecatch-open.json'))))" 2>/dev/null || echo "?")
echo "  • positions ouvertes : $POS"
if [ -f "data/computed/redcandlecatch-eligible-$TODAY.json" ]; then
  ok "signal du jour présent ($($PY -c "import json;print(len(json.load(open('data/computed/redcandlecatch-eligible-$TODAY.json'))))" 2>/dev/null) tickers)"
else warn "pas de signal pour aujourd'hui ($TODAY) — dashboard pas encore lancé ce jour ?"; fi

echo "▸ 6. Cron de collecte quotidienne"
crontab -l 2>/dev/null | grep -q "collect_daily.sh" && ok "cron collecte installé" || warn "cron collecte ABSENT"

echo "══════════════════════════════════════════════════════════"
echo " Résumé : ✅ = ok | ⚠️ = à surveiller | ❌ = à corriger"
echo "══════════════════════════════════════════════════════════"
