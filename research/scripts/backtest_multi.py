#!/usr/bin/env python3
"""
Backtest multi-stop — entrée repli VWAP (pré-marché), sortie 9:30, stops comparés
en parallèle : -5% / -7% / -10%. Cache disque des bougies -> sweeps ultérieurs instantanés.
"""
import csv, json, os, sys, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}
CACHE = '/home/martin/dev/stock-journal-long/research/bars_cache'
os.makedirs(CACHE, exist_ok=True)

# ---- PARAMÈTRES ----
STOPS      = [0.05, 0.07, 0.10]
MIN_PM_VOL = 150_000
VWAP_TOL   = 0.003
MIN_ABOVE  = 3

def fetch_1min(ticker, date_str):
    cf = os.path.join(CACHE, f"{ticker}_{date_str}.json")
    if os.path.exists(cf):
        raw = json.load(open(cf))
        return [{'t': datetime.fromisoformat(b['t']), 'o': b['o'], 'h': b['h'],
                 'l': b['l'], 'c': b['c'], 'v': b['v']} for b in raw]
    try:
        r = requests.get(f"{config.ALPACA_DATA_URL}/v2/stocks/{ticker}/bars", headers=H, timeout=15,
                         params={'timeframe': '1Min', 'start': f"{date_str}T08:00:00Z",
                                 'end': f"{date_str}T21:00:00Z", 'feed': 'sip',
                                 'adjustment': 'raw', 'limit': 10000})
        bars = r.json().get('bars') or [] if r.ok else []
    except Exception:
        bars = []
    out = []
    for b in bars:
        t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
        out.append({'t': t, 'o': b['o'], 'h': b['h'], 'l': b['l'], 'c': b['c'], 'v': b['v']})
    json.dump([{'t': b['t'].isoformat(), 'o': b['o'], 'h': b['h'], 'l': b['l'],
                'c': b['c'], 'v': b['v']} for b in out], open(cf, 'w'))
    return out

def find_entry(bars):
    """Détecte l'entrée (repli VWAP + rebond + filtre volume). Retourne (entry, idx_pm, pm, rth) ou None."""
    pm = [b for b in bars if (b['t'].hour, b['t'].minute) < (9, 30)]
    rth = [b for b in bars if (b['t'].hour, b['t'].minute) >= (9, 30)]
    if len(pm) < MIN_ABOVE + 2 or not rth:
        return None
    for i in range(MIN_ABOVE, len(pm)):
        seg = pm[:i + 1]
        vw = vwap(seg)
        last = seg[-1]
        if sum(b['v'] for b in seg) < MIN_PM_VOL:
            continue
        above = all(seg[j]['c'] > vwap(seg[:j + 1])[-1] for j in range(i - MIN_ABOVE, i))
        tag = last['l'] <= vw[-1] * (1 + VWAP_TOL)
        bounce = last['c'] >= last['o'] and last['c'] > vw[-1]
        if above and tag and bounce:
            return last['c'], i, pm, rth
    return None

def simulate(entry, idx_pm, pm, rth, stop_pct):
    stop = entry * (1 - stop_pct)
    for b in pm[idx_pm + 1:]:
        if b['l'] <= stop:
            return 'STOP', -stop_pct * 100
    return 'OPEN', (rth[0]['o'] - entry) / entry * 100

# ---- run ----
rows = list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(rows)
rows = rows[:limit]

results = {s: [] for s in STOPS}   # stop -> list of pnl%
reasons = {s: Counter() for s in STOPS}
n_entries = no_data = 0
for n, row in enumerate(rows, 1):
    bars = fetch_1min(row['Ticker'].strip(), row['Date'].strip())
    if not bars:
        no_data += 1; continue
    e = find_entry(bars)
    if not e:
        continue
    n_entries += 1
    entry, idx, pm, rth = e
    for s in STOPS:
        reason, pnl = simulate(entry, idx, pm, rth, s)
        results[s].append(pnl); reasons[s][reason] += 1
    if n % 50 == 0:
        print(f"  ...{n}/{len(rows)}")

print(f"\n{'='*66}")
print(f"Lignes: {len(rows)} | sans data: {no_data} | ENTRÉES (identiques): {n_entries}\n")
print(f"{'STOP':>6} {'TRADES':>7} {'WIN%':>6} {'P&L moy':>9} {'TOTAL':>9} {'#STOP':>6} {'#OPEN':>6}")
print("-" * 66)
for s in STOPS:
    r = results[s]
    if not r: continue
    wins = sum(1 for p in r if p > 0)
    print(f"{-s*100:5.0f}% {len(r):>7} {100*wins//len(r):>5}% {sum(r)/len(r):>+8.2f}% "
          f"{sum(r):>+8.1f}% {reasons[s]['STOP']:>6} {reasons[s]['OPEN']:>6}")
print("=" * 66)
