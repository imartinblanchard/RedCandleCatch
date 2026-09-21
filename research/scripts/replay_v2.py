#!/usr/bin/env python3
"""Replay v2 — règle SIMPLE : pullback vers consolidation + stop/TP fixes + filtre volume."""
import logging
logging.getLogger('ib_insync').setLevel(logging.CRITICAL)
from datetime import datetime
from zoneinfo import ZoneInfo
from ib_insync import ScannerSubscription
from execution.ibkr_broker import IBKRBroker
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
TODAY = datetime.now(ET).date()

# ---- PARAMÈTRES (à régler ensemble) ----
BASE_LEN       = 4       # nb de bougies de consolidation
MAX_BASE_RANGE = 0.03    # consolidation "serrée" : amplitude < 3%
MIN_PRIOR_MOVE = 0.02    # il faut une poussée >= +2% avant la consolidation
MIN_5MIN_VOL   = 100_000 # volume mini sur les 5 dernières bougies (sinon trop illiquide)
STOP_PCT       = 0.03    # stop fixe -3%
TP_PCT         = 0.06    # TP fixe +6%  (2:1)

def today_session(bars):
    return [b for b in bars if b['t'].astimezone(ET).date() == TODAY
            and b['t'].astimezone(ET).hour >= 4]

def recent_vol(bars, n=5):
    return sum(b['v'] for b in bars[-n:])

def detect_pullback(bars):
    """Poussée -> consolidation serrée -> reprise au-dessus du haut de la base."""
    if len(bars) < BASE_LEN + 3:
        return None
    last = bars[-1]
    base = bars[-(BASE_LEN + 1):-1]              # bougies de consolidation
    base_high = max(b['h'] for b in base)
    base_low = min(b['l'] for b in base)
    if base_low <= 0:
        return None
    if (base_high - base_low) / base_low > MAX_BASE_RANGE:   # base pas assez serrée
        return None
    pre = bars[-(BASE_LEN + 3):-(BASE_LEN + 1)]  # bougies avant la base
    if pre:
        pre_low = min(b['l'] for b in pre)
        if (base_high - pre_low) / pre_low < MIN_PRIOR_MOVE:  # pas de vraie poussée avant
            return None
    if last['c'] <= vwap(bars)[-1]:              # filtre tendance : au-dessus du VWAP
        return None
    if recent_vol(bars) < MIN_5MIN_VOL:          # filtre volume
        return None
    if last['c'] > base_high:                    # reprise -> entrée
        return {'entry': last['c'], 'base_low': base_low}
    return None

def simulate(bars, entry, entry_i):
    stop = entry * (1 - STOP_PCT)
    tp = entry * (1 + TP_PCT)
    for j in range(entry_i + 1, len(bars)):
        b = bars[j]
        if b['l'] <= stop:
            return 'STOP', stop, (stop - entry) / entry * 100
        if b['h'] >= tp:
            return 'TP', tp, (tp - entry) / entry * 100
    last = bars[-1]
    return 'EOD', last['c'], (last['c'] - entry) / entry * 100

# ---- run ----
broker = IBKRBroker(allow_live=False)
if not broker.connect():
    print("IBKR indisponible"); raise SystemExit
ib = broker.ib
sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR', scanCode='TOP_PERC_GAIN')
sub.abovePrice = 1.0; sub.belowPrice = 10.0; sub.aboveVolume = 100000
rows = ib.reqScannerData(sub)
tickers = [r.contractDetails.contract.symbol for r in rows[:15]]
print(f"Candidats ({len(tickers)}): {', '.join(tickers)}")
print(f"Params: base={BASE_LEN} range<{MAX_BASE_RANGE*100:.0f}% poussée>{MIN_PRIOR_MOVE*100:.0f}% "
      f"vol5min>{MIN_5MIN_VOL//1000}k stop-{STOP_PCT*100:.0f}% tp+{TP_PCT*100:.0f}%\n")

trades = []
for tk in tickers:
    bars = today_session(broker.intraday_1min(tk, duration='28800 S'))
    if len(bars) < BASE_LEN + 4:
        continue
    for i in range(BASE_LEN + 3, len(bars)):
        sig = detect_pullback(bars[:i + 1])
        if sig:
            reason, exit_px, pnl = simulate(bars, sig['entry'], i)
            v5 = recent_vol(bars[:i + 1])
            trades.append((tk, bars[i]['t'], sig['entry'], reason, exit_px, pnl, v5))
            break

if not trades:
    print("Aucune entrée (aucun stock ne passe les filtres ce matin).")
else:
    print(f"{'TICKER':7} {'HEURE(ET)':10} {'ENTRÉE':>8} {'VOL5min':>9} {'SORTIE':7} {'PRIX':>8} {'P&L%':>7}")
    print("-" * 72)
    for tk, t, entry, reason, exit_px, pnl, v5 in trades:
        print(f"{tk:7} {t.astimezone(ET).strftime('%H:%M'):10} {entry:8.4f} "
              f"{int(v5):>9} {reason:7} {exit_px:8.4f} {pnl:+7.2f}")
    wins = sum(1 for t in trades if t[5] > 0)
    print("-" * 72)
    print(f"{len(trades)} trades — {wins} gagnants / {len(trades)-wins} perdants "
          f"— P&L moyen {sum(t[5] for t in trades)/len(trades):+.2f}%")
broker.disconnect()
