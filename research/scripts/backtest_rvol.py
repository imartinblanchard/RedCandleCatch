#!/usr/bin/env python3
"""
Effet du RVOL sur la même règle (repli VWAP, stop -5%, sortie 9:30).
RVOL = volume pré-marché à l'entrée / volume quotidien moyen (20j). Sweep de seuils.
"""
import csv, json, os, sys, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config
from bot.indicators import vwap

ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}
BASE = '/home/martin/dev/stock-journal-long/research'
CACHE = f'{BASE}/bars_cache'
DCACHE = f'{BASE}/daily_cache'; os.makedirs(DCACHE, exist_ok=True)

STOP = 0.05
MIN_PM_VOL = 150_000
VWAP_TOL = 0.003
MIN_ABOVE = 3
RVOL_THRESHOLDS = [0.0, 0.10, 0.25, 0.50, 1.0]

def load_1min(ticker, date_str):
    cf = os.path.join(CACHE, f"{ticker}_{date_str}.json")
    if not os.path.exists(cf):
        return []
    return [{'t': datetime.fromisoformat(b['t']), 'o': b['o'], 'h': b['h'],
             'l': b['l'], 'c': b['c'], 'v': b['v']} for b in json.load(open(cf))]

def avg_daily_vol(ticker, date_str):
    cf = os.path.join(DCACHE, f"{ticker}_{date_str}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    d = datetime.fromisoformat(date_str).date()
    start = (d - timedelta(days=40)).isoformat()
    end = (d - timedelta(days=1)).isoformat()
    try:
        r = requests.get(f"{config.ALPACA_DATA_URL}/v2/stocks/{ticker}/bars", headers=H, timeout=15,
                         params={'timeframe': '1Day', 'start': start, 'end': end,
                                 'feed': 'sip', 'adjustment': 'raw', 'limit': 40})
        vols = [b['v'] for b in (r.json().get('bars') or [])] if r.ok else []
    except Exception:
        vols = []
    avg = sum(vols[-20:]) / len(vols[-20:]) if vols else 0
    json.dump(avg, open(cf, 'w'))
    return avg

def find_entry(bars):
    pm = [b for b in bars if (b['t'].hour, b['t'].minute) < (9, 30)]
    rth = [b for b in bars if (b['t'].hour, b['t'].minute) >= (9, 30)]
    if len(pm) < MIN_ABOVE + 2 or not rth:
        return None
    for i in range(MIN_ABOVE, len(pm)):
        seg = pm[:i + 1]; vw = vwap(seg); last = seg[-1]
        pmvol = sum(b['v'] for b in seg)
        if pmvol < MIN_PM_VOL:
            continue
        above = all(seg[j]['c'] > vwap(seg[:j + 1])[-1] for j in range(i - MIN_ABOVE, i))
        tag = last['l'] <= vw[-1] * (1 + VWAP_TOL)
        bounce = last['c'] >= last['o'] and last['c'] > vw[-1]
        if above and tag and bounce:
            return last['c'], i, pm, rth, pmvol
    return None

def simulate(entry, idx, pm, rth):
    stop = entry * (1 - STOP)
    for b in pm[idx + 1:]:
        if b['l'] <= stop:
            return -STOP * 100
    return (rth[0]['o'] - entry) / entry * 100

rows = list(csv.DictReader(open('/home/martin/dev/stock-journal-long/data/long-checklist.csv')))
setups = []   # (rvol, pnl)
n = 0
for row in rows:
    tk, date = row['Ticker'].strip(), row['Date'].strip()
    bars = load_1min(tk, date)
    if not bars:
        continue
    e = find_entry(bars)
    if not e:
        continue
    entry, idx, pm, rth, pmvol = e
    adv = avg_daily_vol(tk, date)
    rvol = pmvol / adv if adv else 0
    setups.append((rvol, simulate(entry, idx, pm, rth)))
    n += 1
    if n % 50 == 0:
        print(f"  ...{n} entrées traitées")

print(f"\n{'='*60}\nEntrées totales: {len(setups)} | stop -{STOP*100:.0f}%\n")
print(f"{'RVOL>=':>7} {'TRADES':>7} {'WIN%':>6} {'P&L moy':>9} {'TOTAL':>9}")
print("-" * 60)
for thr in RVOL_THRESHOLDS:
    sel = [p for rv, p in setups if rv >= thr]
    if not sel:
        print(f"{thr:>6.2f}  {0:>7}   --")
        continue
    wins = sum(1 for p in sel if p > 0)
    print(f"{thr:>6.2f}  {len(sel):>7} {100*wins//len(sel):>5}% "
          f"{sum(sel)/len(sel):>+8.2f}% {sum(sel):>+8.1f}%")
print("=" * 60)
