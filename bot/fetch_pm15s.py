#!/usr/bin/env python3
"""Bougies 15 SECONDES de la fenêtre PRÉ-MARCHÉ (04:00-10:00 ET) — pour l'étude momentum PM.

IBKR sert le 15s même quelques jours en arrière (backfill OK), donc collectable en direct
ET rétro sur une petite fenêtre. Le PM (19 800 s) dépasse le cap ~14 400 s/requête pour le
sous-minute -> on tire en 2 chunks de 3h (04:00-07:00, 07:00-10:00) puis on fusionne.

Sortie : data/collected_live/pm15s-YYYY-MM-DD.parquet  (ticker,date,datetime HH:MM:SS,o,h,l,c,v)
Résumable (saute les tickers déjà présents). Pacé (sous-minute = quota IBKR strict).

Usage :
  python -m bot.fetch_pm15s --date 2026-09-24 --sample 40      # échantillon (étude)
  python -m bot.fetch_pm15s --date 2026-09-24 --tickers VEEE,KOSS
  python -m bot.fetch_pm15s                                    # jour courant, tout l'univers
"""
import os, sys, json, time, random, argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot.collect_universe as cu

ET = ZoneInfo('America/New_York')
DIR = cu.DIR
SLEEP = 8.0                                        # pacing strict pour le sous-minute


def _fetch_one(ib, ct, day):
    from ib_insync import util
    rows = []
    d = datetime.strptime(day, '%Y-%m-%d').date()
    for end_h in (7, 10):                          # 2 chunks de 3h -> 04:00-10:00
        end = datetime(d.year, d.month, d.day, end_h, 0, 0, tzinfo=ET)
        try:
            bars = ib.reqHistoricalData(ct, end.astimezone(ZoneInfo('UTC')).strftime('%Y%m%d %H:%M:%S') + ' UTC',
                                        '10800 S', '15 secs', 'TRADES', useRTH=False, formatDate=1)
        except Exception as e:
            print(f"    chunk {end_h}h err: {e}"); continue
        for b in bars:
            t = b.date.astimezone(ET) if hasattr(b.date, 'astimezone') else b.date
            if t.date().isoformat() != day:
                continue
            hm = t.hour * 60 + t.minute
            if hm < 4 * 60 or hm >= 10 * 60:       # garde 04:00-10:00
                continue
            rows.append((t.strftime('%H:%M:%S'), float(b.open), float(b.high),
                         float(b.low), float(b.close), float(b.volume) * 100))
        time.sleep(SLEEP)
    return rows


def _band_lo(info):
    try:
        return float(str(info.get('band', '')).split('-')[0])
    except Exception:
        return 0.0


def main(day, tickers=None, sample=None, min_band=None):
    uni = cu.load(day)
    if not uni:
        print(f"[{day}] univers absent (universe-{day}.json)"); return
    syms = tickers or list(uni)
    if min_band is not None:                          # ne garder que les gappers >= min_band%
        syms = [t for t in syms if _band_lo(uni.get(t, {})) >= min_band]
    if sample:
        random.seed(42); syms = random.sample(syms, min(sample, len(syms)))
    from ib_insync import IB, Stock
    barp = os.path.join(DIR, f'pm15s-{day}.parquet')
    done = set(pd.read_parquet(barp, columns=['ticker'])['ticker'].unique()) if os.path.exists(barp) else set()
    todo = [t for t in syms if t not in done]
    print(f"[{day}] cible {len(syms)} | déjà {len(done)} | à faire {len(todo)}", flush=True)
    ib = IB(); ib.connect('127.0.0.1', 4001, clientId=random.randint(3200, 3900), timeout=25)
    chunks = [pd.read_parquet(barp)] if os.path.exists(barp) else []
    for i, tk in enumerate(todo):
        try:
            ct = Stock(tk, 'SMART', 'USD'); ib.qualifyContracts(ct)
            rows = _fetch_one(ib, ct, day)
        except Exception as e:
            print(f"  !! {tk}: {e}", flush=True); rows = []
        if rows:
            df = pd.DataFrame(rows, columns=['datetime', 'o', 'h', 'l', 'c', 'v'])
            df.insert(0, 'date', day); df.insert(0, 'ticker', tk)
            chunks.append(df.drop_duplicates('datetime'))
        if i % 5 == 0 or i == len(todo) - 1:
            if chunks:
                pd.concat(chunks, ignore_index=True).to_parquet(barp)
            print(f"  ...{i+1}/{len(todo)} ({tk}: {len(rows)} barres)", flush=True)
    ib.disconnect()
    if chunks:
        out = pd.concat(chunks, ignore_index=True).drop_duplicates(['ticker', 'datetime'])
        out.to_parquet(barp)
        print(f"\n✅ [{day}] {out['ticker'].nunique()} tickers, {len(out)} barres 15s -> {barp}", flush=True)
    else:
        print(f"[{day}] aucune barre récupérée")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ET).date().isoformat())
    ap.add_argument('--tickers', help='liste CSV (sinon tout l\'univers)')
    ap.add_argument('--sample', type=int, help='échantillon aléatoire de N tickers')
    ap.add_argument('--min-band', type=float, help='ne garder que les gappers dont la bande commence >= X%% (ex: 10)')
    a = ap.parse_args()
    main(a.date, tickers=a.tickers.split(',') if a.tickers else None, sample=a.sample, min_band=a.min_band)
