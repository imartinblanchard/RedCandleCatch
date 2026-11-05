#!/usr/bin/env python3
"""Mesure le BIAIS DU SURVIVANT de gappers.json.

Le screener ne prenait que les titres `status=active` -> tous les titres radiés/
faillis entre déc. 2025 et aujourd'hui sont absents. On refait le même screening
sur les titres INACTIFS et on compte combien de gapper-jours manquent."""
import sys, json, time
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import requests
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

ET = ZoneInfo('America/New_York')
H = {'APCA-API-KEY-ID': c.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': c.ALPACA_API_SECRET_KEY}
DATA = 'https://data.alpaca.markets'; TRADE = 'https://paper-api.alpaca.markets'
START, END = '2025-12-26', '2026-08-24'
MIN_GAP, MIN_P, MAX_P = 0.10, 2.0, 20.0

r = requests.get(f'{TRADE}/v2/assets', headers=H,
                 params={'status': 'inactive', 'asset_class': 'us_equity'}, timeout=90)
assets = [a['symbol'] for a in r.json()
          if a.get('exchange') in ('NASDAQ', 'NYSE', 'ARCA', 'AMEX')
          and '.' not in a['symbol'] and '/' not in a['symbol']]
print(f"Titres INACTIFS (radiés) à tester : {len(assets)}", flush=True)

def hourly(symbols):
    out = defaultdict(list); url = f'{DATA}/v2/stocks/bars'
    params = {'symbols': ','.join(symbols), 'timeframe': '1Hour', 'start': START, 'end': END,
              'feed': 'sip', 'adjustment': 'all', 'limit': 10000}
    while True:
        rr = requests.get(url, headers=H, params=params, timeout=90)
        if not rr.ok:
            break
        j = rr.json()
        for sym, bars in (j.get('bars') or {}).items():
            out[sym].extend(bars)
        tok = j.get('next_page_token')
        if not tok:
            break
        params['page_token'] = tok
    return out

manquants = []; B = 150
for k in range(0, len(assets), B):
    data = hourly(assets[k:k + B])
    for sym, bars in data.items():
        byday = defaultdict(list)
        for b in bars:
            t = datetime.fromisoformat(b['t'].replace('Z', '+00:00')).astimezone(ET)
            byday[t.date()].append((t, b))
        days = sorted(byday)
        for di in range(1, len(days)):
            prev = byday[days[di - 1]]; today = byday[days[di]]
            regs = [b['c'] for t, b in prev if 10 <= t.hour <= 15]
            if not regs:
                continue
            pc = regs[-1]
            if pc <= 0:
                continue
            pm = sorted([(t, b) for t, b in today if 4 <= t.hour <= 8], key=lambda x: x[0])
            if not pm:
                continue
            pm_high = max(b['h'] for _, b in pm)
            gap = (pm_high - pc) / pc
            if gap >= MIN_GAP and MIN_P <= pm_high <= MAX_P:
                manquants.append({'ticker': sym, 'date': days[di].isoformat(),
                                  'gap': round(gap * 100, 1), 'pm_high': round(pm_high, 3),
                                  'prev_close': round(pc, 3),
                                  'pm_vol': int(sum(b['v'] for _, b in pm))})
    if (k // B) % 3 == 0:
        print(f"  ...{min(k+B,len(assets))}/{len(assets)}, {len(manquants)} gappers manquants", flush=True)
    time.sleep(0.05)

json.dump(manquants, open('/home/martin/dev/stock-journal-long/research/gappers_manquants.json', 'w'))

exist = json.load(open('/home/martin/dev/stock-journal-long/research/gappers.json'))
def buckets(lst):
    d = {'10-20': 0, '20-50': 0, '50-100': 0, '100+': 0}
    for x in lst:
        g = x['gap']
        d['10-20' if g < 20 else '20-50' if g < 50 else '50-100' if g < 100 else '100+'] += 1
    return d

print("\n" + "=" * 58)
print(f"DANS LE BACKTEST (titres actifs)  : {len(exist)} gapper-jours")
print(f"MANQUANTS (titres radiés)         : {len(manquants)} gapper-jours")
if exist:
    print(f"=> biais : {100*len(manquants)/(len(exist)+len(manquants)):.1f}% de l'univers réel est absent")
be, bm = buckets(exist), buckets(manquants)
print(f"\n{'tranche':10}{'dans test':>12}{'manquants':>12}{'% manquant':>12}")
for k in be:
    tot = be[k] + bm[k]
    print(f"{k:10}{be[k]:>12}{bm[k]:>12}{100*bm[k]/tot if tot else 0:>11.1f}%")
print(f"\n-> research/gappers_manquants.json")
