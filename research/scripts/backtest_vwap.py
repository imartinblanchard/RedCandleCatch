#!/usr/bin/env python3
"""
Backtest — entrée sur repli VWAP (pré-marché), stop -10%, sortie à l'open 9:30.
Universe = checklist historique. Data = bougies 1-min SIP Alpaca.
"""
import csv
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}

# ---- PARAMÈTRES ----
STOP_PCT       = 0.10     # stop fixe -10%
MIN_PM_VOL     = 150_000  # volume pré-marché mini (proxy RVOL)
VWAP_TOL       = 0.003    # "touche" la VWAP si low <= vwap*(1+tol)
MIN_ABOVE      = 3        # nb de bougies au-dessus du VWAP avant le repli (tendance)

def fetch_1min(ticker, date_str):
    start = f"{date_str}T08:00:00Z"   # ~04:00 ET
    end   = f"{date_str}T21:00:00Z"   # ~17:00 ET
    try:
        r = requests.get(f"{config.ALPACA_DATA_URL}/v2/stocks/{ticker}/bars",
                         headers=H, timeout=15, params={
                             'timeframe': '1Min', 'start': start, 'end': end,
                             'feed': 'sip', 'adjustment': 'raw', 'limit': 10000})
        if not r.ok:
            return []
        out = []
        for b in r.json().get('bars') or []:
            t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
            out.append({'t': t, 'o': b['o'], 'h': b['h'], 'l': b['l'], 'c': b['c'], 'v': b['v']})
        return out
    except Exception:
        return []

def backtest_one(bars):
    """Retourne (reason, pnl_pct, entry, entry_time) ou None."""
    pm = [b for b in bars if b['t'].hour < 9 or (b['t'].hour == 9 and b['t'].minute < 30)]
    rth = [b for b in bars if (b['t'].hour, b['t'].minute) >= (9, 30)]
    if len(pm) < MIN_ABOVE + 2 or not rth:
        return None
    pm_vol_cum = 0
    for i in range(MIN_ABOVE, len(pm)):
        seg = pm[:i + 1]
        vw = vwap(seg)
        last = seg[-1]
        pm_vol_cum = sum(b['v'] for b in seg)
        # tendance : les MIN_ABOVE bougies précédentes au-dessus de la VWAP
        above = all(seg[j]['c'] > vwap(seg[:j + 1])[-1] for j in range(i - MIN_ABOVE, i))
        tag_vwap = last['l'] <= vw[-1] * (1 + VWAP_TOL)      # repli qui touche la VWAP
        bounce = last['c'] >= last['o'] and last['c'] > vw[-1]  # rebond vert au-dessus VWAP
        if above and tag_vwap and bounce and pm_vol_cum >= MIN_PM_VOL:
            entry = last['c']
            stop = entry * (1 - STOP_PCT)
            # gérer jusqu'à 9:30
            for b in pm[i + 1:]:
                if b['l'] <= stop:
                    return ('STOP', -STOP_PCT * 100, entry, last['t'])
            open_px = rth[0]['o']                            # sortie à l'open 9:30
            return ('OPEN', (open_px - entry) / entry * 100, entry, last['t'])
    return None

# ---- run ----
rows = list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(rows)
rows = rows[:limit]
print(f"Backtest repli VWAP — {len(rows)} lignes | stop -{STOP_PCT*100:.0f}% | "
      f"sortie 9:30 | vol PM >= {MIN_PM_VOL//1000}k\n")

trades, no_data, no_entry = [], 0, 0
for n, row in enumerate(rows, 1):
    tk, date = row['Ticker'].strip(), row['Date'].strip()
    bars = fetch_1min(tk, date)
    if not bars:
        no_data += 1
    else:
        res = backtest_one(bars)
        if res:
            trades.append((tk, date) + res)
        else:
            no_entry += 1
    if n % 25 == 0:
        print(f"  ...{n}/{len(rows)}  ({len(trades)} entrées jusqu'ici)")

print(f"\n{'='*60}")
print(f"Lignes: {len(rows)} | sans data: {no_data} | sans entrée: {no_entry} | ENTRÉES: {len(trades)}")
if trades:
    wins = [t for t in trades if t[3] > 0]
    reasons = Counter(t[2] for t in trades)
    avg = sum(t[3] for t in trades) / len(trades)
    print(f"Taux de réussite: {len(wins)}/{len(trades)} = {100*len(wins)//len(trades)}%")
    print(f"P&L moyen/trade: {avg:+.2f}%  | total cumulé: {sum(t[3] for t in trades):+.1f}%")
    print(f"Sorties: {dict(reasons)}")
    print(f"\nMeilleurs / pires :")
    for t in sorted(trades, key=lambda x: x[3], reverse=True)[:3]:
        print(f"  +{t[3]:5.1f}%  {t[0]:6} {t[1]} ({t[2]})")
    for t in sorted(trades, key=lambda x: x[3])[:3]:
        print(f"  {t[3]:6.1f}%  {t[0]:6} {t[1]} ({t[2]})")
