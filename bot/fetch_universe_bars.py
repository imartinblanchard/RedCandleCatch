#!/usr/bin/env python3
"""APRÈS la clôture : tire les bougies 1-min (IBKR) de tout l'univers capté EN DIRECT par le
dashboard (data/collected_live/universe-YYYY-MM-DD.json). 100% IBKR, aucune Alpaca.
Sortie : data/collected_live/bars-YYYY-MM-DD.parquet + meta-YYYY-MM-DD.json (prev_close, band...).
Résumable (saute les tickers déjà dans le parquet). Cadence gérée.

Usage : python -m bot.fetch_universe_bars              (jour courant)
        python -m bot.fetch_universe_bars --date 2026-09-24
"""
import os, sys, json, time, random, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot.collect_universe as cu
import bot.redcandlecatch_scan as wscan          # fetch_fundamentals (float, inst%, mcap)

ET = ZoneInfo('America/New_York')
DIR = cu.DIR
SLEEP = 6.0                                       # pause entre requêtes IBKR (cadence)


def prev_close(ib, ct):
    try:
        d = ib.reqHistoricalData(ct, '', '5 D', '1 day', 'TRADES', useRTH=True, formatDate=1)
        today = datetime.now(ET).date()
        prev = [b for b in d if (b.date.date() if hasattr(b.date, 'hour') else b.date) < today]
        return float(prev[-1].close) if prev else None
    except Exception:
        return None


def main(day):
    uni = cu.load(day)
    if not uni:
        print(f"[{day}] aucun univers capté (data/collected_live/universe-{day}.json absent)"); return
    from ib_insync import IB, Stock
    barp = os.path.join(DIR, f'bars-{day}.parquet')
    metap = os.path.join(DIR, f'meta-{day}.json')
    done = set(pd.read_parquet(barp, columns=['ticker'])['ticker'].unique()) if os.path.exists(barp) else set()
    meta = json.load(open(metap)) if os.path.exists(metap) else {}
    todo = [tk for tk in uni if tk not in done]
    print(f"[{day}] univers {len(uni)} tickers | déjà fait {len(done)} | à faire {len(todo)}", flush=True)

    ib = IB(); ib.connect('127.0.0.1', 4001, clientId=random.randint(3200, 3900), timeout=25)
    chunks = [pd.read_parquet(barp)] if os.path.exists(barp) else []
    for i, tk in enumerate(todo):
        try:
            ct = Stock(tk, 'SMART', 'USD'); ib.qualifyContracts(ct)
            bars = ib.reqHistoricalData(ct, '', '57600 S', '1 min', 'TRADES', useRTH=False, formatDate=1)
        except Exception as e:
            print(f"  !! {tk}: {e}", flush=True); time.sleep(SLEEP); continue
        rows = []
        for b in bars:
            t = b.date.astimezone(ET) if hasattr(b.date, 'astimezone') else b.date
            if t.date().isoformat() != day:
                continue
            rows.append((tk, day, t.strftime('%H:%M'), float(b.open), float(b.high), float(b.low),
                         float(b.close), float(b.volume) * 100))     # IB vol en lots de 100
        if rows:
            chunks.append(pd.DataFrame(rows, columns=['ticker', 'date', 'datetime', 'o', 'h', 'l', 'c', 'v']))
            pc = prev_close(ib, ct)
            fund = wscan.fetch_fundamentals(tk)
            meta[tk] = {**uni[tk], 'prev_close': round(pc, 4) if pc else None,
                        'float_shares': fund.get('float_shares'), 'inst_pct': fund.get('inst_pct'),
                        'market_cap': fund.get('market_cap')}
        if i % 10 == 0 or i == len(todo) - 1:
            if chunks:
                pd.concat(chunks, ignore_index=True).to_parquet(barp)
            json.dump(meta, open(metap, 'w'))
            print(f"  ...{i+1}/{len(todo)} ({tk})", flush=True)
        time.sleep(SLEEP)
    ib.disconnect()
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    if len(df):
        df.to_parquet(barp)
    json.dump(meta, open(metap, 'w'))
    print(f"\n✅ [{day}] {df['ticker'].nunique() if len(df) else 0} tickers, {len(df)} bougies -> {barp}", flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ET).date().isoformat())
    a = ap.parse_args()
    main(a.date)
