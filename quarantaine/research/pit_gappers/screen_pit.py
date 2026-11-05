#!/usr/bin/env python3
"""PIT rebuild — Phase 1 : SCREEN daily (jette le filet, ne classe pas).

Balaie tout l'univers actif Alpaca en bougies 1Day et flagge les ticker-jours candidats.
Le screen ne fait QUE repérer « ce jour-là ce ticker a atteint >= 5% au-dessus de la
clôture veille » — l'heure exacte du gap (PM / post-open, multi-épisodes) est résolue en
Phase 3 sur le 1-min. Donc le daily suffit ici, et c'est ~100x plus léger que le 1H.

Critère (gap UP seulement) :
  open_gap = (open - prev_close)/prev_close   -> gap overnight/PM tenu à l'ouverture
  high_gap = (high - prev_close)/prev_close   -> runner intraday (capte l'ouvre-plat-puis-court)
  candidat si (open_gap >= GAP_MIN OU high_gap >= GAP_MIN) ET high_gap <= GAP_MAX
            ET PMIN <= prev_close <= PMAX  ET day_$vol >= DVOL_MIN

Aucun plafond de BANDE (pas de <=20%) -> on garde les runaways (fin du Défaut 2).
Sortie : data/candidates.json
"""
import os, sys, json, time
import requests
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
from bot import config as c

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
os.makedirs(DATA, exist_ok=True)
OUT = os.path.join(DATA, 'candidates.json')

H = {'APCA-API-KEY-ID': c.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': c.ALPACA_API_SECRET_KEY}
TRADE = 'https://paper-api.alpaca.markets'
BARS = 'https://data.alpaca.markets/v2/stocks/bars'
START, END = '2025-12-26', '2026-08-25'       # fenêtre = candles.parquet (comparable)

GAP_MIN, GAP_MAX = 0.05, 5.00                 # 5% plancher, 500% garde-fou anti-split
PMIN, PMAX = 0.50, 50.0                        # bande de prix LARGE (filtrage fin à l'analyse)
DVOL_MIN = 1_000_000                           # filtre d'efficacité (0 = littéralement tout)
BATCH = 200


def universe():
    r = requests.get(f'{TRADE}/v2/assets', headers=H,
                     params={'status': 'active', 'asset_class': 'us_equity'}, timeout=60)
    r.raise_for_status()
    return [a['symbol'] for a in r.json() if a.get('tradable')
            and a.get('exchange') in ('NASDAQ', 'NYSE', 'ARCA', 'AMEX')
            and '.' not in a['symbol'] and '/' not in a['symbol']]


def daily_bars(symbols):
    """{symbol: [bars]} pour un lot, paginé."""
    out = {}
    token = None
    while True:
        params = {'symbols': ','.join(symbols), 'timeframe': '1Day', 'start': START, 'end': END,
                  'feed': 'sip', 'adjustment': 'all', 'limit': 10000}
        if token:
            params['page_token'] = token
        r = requests.get(BARS, headers=H, params=params, timeout=90)
        if r.status_code == 429:
            time.sleep(2); continue
        r.raise_for_status(); j = r.json()
        for sym, bars in (j.get('bars') or {}).items():
            out.setdefault(sym, []).extend(bars)
        token = j.get('next_page_token')
        if not token:
            break
    return out


def main():
    syms = universe()
    print(f"Univers actif : {len(syms)} symboles. Screen daily {START} -> {END}", flush=True)
    rows = []
    n_open = n_high_only = 0
    for k in range(0, len(syms), BATCH):
        data = daily_bars(syms[k:k + BATCH])
        for sym, bars in data.items():
            bars = sorted(bars, key=lambda b: b['t'])          # par date croissante
            for i in range(1, len(bars)):
                pc = bars[i - 1]['c']                            # clôture de la veille
                if not pc or pc <= 0 or not (PMIN <= pc <= PMAX):
                    continue
                b = bars[i]
                og = (b['o'] - pc) / pc
                hg = (b['h'] - pc) / pc
                if hg > GAP_MAX:                                 # garde-fou split/print
                    continue
                if not (og >= GAP_MIN or hg >= GAP_MIN):         # gap UP >= plancher
                    continue
                dvol = b['v'] * b.get('vw', b['c'])              # dollar-volume approx
                if DVOL_MIN and dvol < DVOL_MIN:
                    continue
                rows.append({'ticker': sym, 'date': b['t'][:10],
                             'prev_close': round(pc, 4),
                             'o': b['o'], 'h': b['h'], 'l': b['l'], 'close': b['c'], 'v': b['v'],
                             'open_gap': round(og * 100, 1), 'high_gap': round(hg * 100, 1),
                             'day_dvol': int(dvol)})
                if og >= GAP_MIN:
                    n_open += 1
                elif hg >= GAP_MIN:
                    n_high_only += 1
        if (k // BATCH) % 5 == 0:
            print(f"  ...{k + BATCH}/{len(syms)} symboles, {len(rows)} candidats", flush=True)

    json.dump(rows, open(OUT, 'w'))
    dates = sorted(set(x['date'] for x in rows))
    print(f"\n✅ {len(rows)} ticker-jours candidats sur {len(dates)} dates, "
          f"{len(set(x['ticker'] for x in rows))} tickers")
    print(f"   dont gappés à l'OUVERTURE (open_gap>=5%) : {n_open}")
    print(f"   dont runners intraday seulement (high_gap>=5%, open<5%) : {n_high_only}")
    print(f"   filtre day_$vol >= ${DVOL_MIN:,} | prix {PMIN}-{PMAX}$ | gap {GAP_MIN*100:.0f}-{GAP_MAX*100:.0f}%")
    print(f"-> {OUT}")
    print(f"\n⚠️ Phase 2 (fetch 1-min) portera sur ces {len(rows)} ticker-jours. Vérifie le compte avant.")


if __name__ == '__main__':
    main()
