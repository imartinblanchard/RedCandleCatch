#!/usr/bin/env python3
"""Replay this morning's session: which entries would the strategy have taken?"""
import logging
logging.getLogger('ib_insync').setLevel(logging.CRITICAL)
from datetime import datetime
from zoneinfo import ZoneInfo
from ib_insync import ScannerSubscription
from execution.ibkr_broker import IBKRBroker
from bot.setups import detect_entry
from bot.indicators import ema

ET = ZoneInfo('America/New_York')
TODAY = datetime.now(ET).date()

def today_session(bars):
    """Keep only today's bars from 04:00 ET onward (this morning's session)."""
    out = []
    for b in bars:
        t = b['t'].astimezone(ET)
        if t.date() == TODAY and t.hour >= 4:
            out.append(b)
    return out

broker = IBKRBroker(allow_live=False)
if not broker.connect():
    print("IBKR indisponible"); raise SystemExit
ib = broker.ib

# --- 1. Candidats du matin : top % gainers $1-$10 ---
sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                          scanCode='TOP_PERC_GAIN')
sub.abovePrice = 1.0; sub.belowPrice = 10.0; sub.aboveVolume = 100000
rows = ib.reqScannerData(sub)
tickers = [r.contractDetails.contract.symbol for r in rows[:15]]
print(f"Candidats du matin ({len(tickers)}): {', '.join(tickers)}\n")

def simulate(bars, sig, entry_i):
    """Walk forward from entry to find the exit (2:1 / stop / trail 9EMA / EOD)."""
    entry, stop = sig['entry'], sig['stop']
    risk = entry - stop
    target = entry + 2 * risk
    closes = [b['c'] for b in bars]
    for j in range(entry_i + 1, len(bars)):
        b = bars[j]
        e9 = ema(closes[:j + 1], 9)[-1]
        if b['l'] <= stop:
            return 'STOP', stop, bars[j]['t'], (stop - entry) / entry * 100
        if b['h'] >= target:
            return 'TP', target, bars[j]['t'], (target - entry) / entry * 100
        if b['c'] > entry and b['c'] < e9:   # trailing once in profit
            return 'TRAIL', b['c'], bars[j]['t'], (b['c'] - entry) / entry * 100
    last = bars[-1]
    return 'EOD', last['c'], last['t'], (last['c'] - entry) / entry * 100

# --- 2. Rejouer detect_entry bougie par bougie ---
trades = []
for tk in tickers:
    raw = broker.intraday_1min(tk, duration='28800 S')  # ~8h ending now
    bars = today_session(raw)                            # <-- ce matin seulement
    if len(bars) < 6:
        continue
    for i in range(5, len(bars)):
        sig = detect_entry(bars[:i + 1], pm_high=None)   # pré-marché: micro-pullback + bull flag
        if sig:
            reason, exit_px, exit_t, pnl_pct = simulate(bars, sig, i)
            risk_pct = (sig['entry'] - sig['stop']) / sig['entry'] * 100
            trades.append((tk, sig['setup'], bars[i]['t'], sig['entry'], sig['stop'],
                           reason, exit_px, pnl_pct, risk_pct))
            break  # une seule position par ticker

# --- 3. Rapport ---
if not trades:
    print("Aucune entrée déclenchée ce matin (pas de setup valide dans le pré-marché).")
else:
    def et(t): return t.astimezone(ET).strftime('%H:%M')
    print(f"{'TICKER':7} {'SETUP':15} {'HEURE(ET)':10} {'ENTRÉE':>8} {'STOP':>7} "
          f"{'RISQUE':>7} {'SORTIE':7} {'PRIX':>8} {'P&L%':>7}")
    print("-" * 92)
    for tk, setup, t, entry, stop, reason, exit_px, pnl, risk_pct in trades:
        print(f"{tk:7} {setup:15} {et(t):10} {entry:8.4f} {stop:7.4f} "
              f"{risk_pct:6.2f}% {reason:7} {exit_px:8.4f} {pnl:+7.2f}")
    wins = sum(1 for t in trades if t[7] > 0)
    print("-" * 92)
    print(f"{len(trades)} trades — {wins} gagnants / {len(trades)-wins} perdants "
          f"— P&L moyen {sum(t[7] for t in trades)/len(trades):+.2f}%")
broker.disconnect()
