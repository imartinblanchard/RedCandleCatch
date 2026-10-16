#!/usr/bin/env python3
"""SUIVI ('follow-through') : pour chaque titre eligible d'un jour N, capture les bougies 1-min
du jour N (after-hours INCLUS, jusqu'a 20:00) ET de TOUTE la journee suivante N+1 (1-min aussi).
But : etudier le maintien d'une position AU-DELA de la cloture (after-hours + overnight -> lendemain).

Doit tourner le SOIR de N+1 (apres l'after-hours, ~20:15+) : il lit l'univers du jour N (le plus
recent univers STRICTEMENT avant aujourd'hui), tire ~3 jours de 1-min (useRTH=False) et garde N et N+1.
Resumable (saute les tickers deja faits). Horodatage complet 'YYYY-MM-DD HH:MM' (couvre 2 jours).

Sortie : data/collected_live/followthrough-<N>.parquet  (ticker,date,datetime,o,h,l,c,v)
Usage : python -m bot.fetch_followthrough                 (jour N = jour de bourse precedent)
        python -m bot.fetch_followthrough --date 2026-10-14   (force le jour N)
        python -m bot.fetch_followthrough --limit 3           (test rapide)
"""
import os, sys, json, glob, time, random, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot.collect_universe as cu

ET = ZoneInfo('America/New_York')
DIR = cu.DIR
SLEEP = 6.0


def prev_trading_day():
    """Date du univers le plus recent STRICTEMENT avant aujourd'hui (= jour N a suivre)."""
    today = datetime.now(ET).date().isoformat()
    days = sorted(os.path.basename(f)[9:19] for f in glob.glob(os.path.join(DIR, 'universe-*.json')))
    before = [d for d in days if d < today]
    return before[-1] if before else None


def main(day, limit, tickers=None):
    if not day:
        print("[follow-through] aucun jour de bourse precedent trouve"); return
    uni = cu.load(day) or {}
    src = tickers if tickers else list(uni)
    if not src:
        print(f"[{day}] aucun ticker (univers absent et pas de liste fournie)"); return
    # N+1 = jour OUVRE suivant (deterministe : marche aussi pour les vieux jours sans univers)
    from datetime import timedelta
    nd = datetime.fromisoformat(day).date() + timedelta(days=1)
    while nd.weekday() >= 5:                 # saute samedi/dimanche
        nd += timedelta(days=1)
    nxt = nd.isoformat()
    keep = {day, nxt}
    # fin de fenetre = N+1 a 20:00 ET (fin de l'after-hours), borne a 'maintenant' si N+1 = aujourd'hui
    from datetime import time as _time
    nxt_d = datetime.fromisoformat(nxt).date()
    end_dt = datetime.combine(nxt_d, _time(20, 0), tzinfo=ET)
    now = datetime.now(ET)
    if end_dt > now:
        end_dt = now
    from ib_insync import IB, Stock
    outp = os.path.join(DIR, f'followthrough-{day}.parquet')
    done = set(pd.read_parquet(outp, columns=['ticker'])['ticker'].unique()) if os.path.exists(outp) else set()
    todo = [tk for tk in src if tk not in done]
    if limit:
        todo = todo[:limit]
    print(f"[follow-through N={day} / N+1={nxt}] univers {len(uni)} | deja fait {len(done)} | a faire {len(todo)}", flush=True)

    ib = IB(); ib.connect('127.0.0.1', 4001, clientId=random.randint(3200, 3900), timeout=25)
    chunks = [pd.read_parquet(outp)] if os.path.exists(outp) else []
    for i, tk in enumerate(todo):
        try:
            ct = Stock(tk, 'SMART', 'USD'); ib.qualifyContracts(ct)
            bars = ib.reqHistoricalData(ct, end_dt, '3 D', '1 min', 'TRADES', useRTH=False, formatDate=1)
        except Exception as e:
            print(f"  !! {tk}: {e}", flush=True); time.sleep(SLEEP); continue
        rows = []
        for b in bars:
            t = b.date.astimezone(ET) if hasattr(b.date, 'astimezone') else b.date
            d = t.date().isoformat()
            if d not in keep:
                continue
            rows.append((tk, d, t.strftime('%Y-%m-%d %H:%M'), float(b.open), float(b.high),
                         float(b.low), float(b.close), float(b.volume) * 100))   # IB vol en lots de 100
        if rows:
            chunks.append(pd.DataFrame(rows, columns=['ticker', 'date', 'datetime', 'o', 'h', 'l', 'c', 'v']))
        if i % 10 == 0 or i == len(todo) - 1:
            if chunks:
                pd.concat(chunks, ignore_index=True).to_parquet(outp)
            print(f"  ...{i+1}/{len(todo)} ({tk})", flush=True)
        time.sleep(SLEEP)
    ib.disconnect()
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    if len(df):
        df.to_parquet(outp)
    print(f"\n[OK] [{day}] {df['ticker'].nunique() if len(df) else 0} tickers, {len(df)} bougies "
          f"(jours {sorted(keep)}) -> {outp}", flush=True)


def from_journal(limit):
    """Backfill : follow-through de TOUS les titres reellement tradés (journal), par date."""
    import csv
    jp = os.path.join(os.path.dirname(DIR), 'computed', 'redcandlecatch-journal.csv')
    by_day = {}
    for r in csv.DictReader(open(jp)):
        by_day.setdefault(r['date'], set()).add(r['ticker'])
    today = datetime.now(ET).date().isoformat()
    for day in sorted(by_day):
        if day >= today:
            continue                       # besoin du lendemain complet
        print(f"\n########## {day} : {sorted(by_day[day])} ##########", flush=True)
        main(day, limit, tickers=sorted(by_day[day]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None, help="jour N (defaut: jour de bourse precedent)")
    ap.add_argument('--limit', type=int, default=0, help="limite le nb de tickers (test)")
    ap.add_argument('--from-journal', action='store_true', help="backfill tous les titres tradés (journal)")
    a = ap.parse_args()
    if a.from_journal:
        from_journal(a.limit)
    else:
        main(a.date or prev_trading_day(), a.limit)
