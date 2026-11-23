#!/usr/bin/env python3
"""RÉCONCILIATION nightly : trades ATTENDUS (rejeu des détecteurs déployés sur les bars du jour,
point-in-time, gatés à `added` + PM-liq, comme le terminator) vs trades RÉELS du journal.
Flagge les RATÉS (attendu mais pas pris) et les inattendus -> attrape les bugs (bot planté/déco)
et quantifie l'écart réel-vs-backtest. Un raté est souvent LÉGITIME (volume temps réel < EOD),
mais le signaler permet de trancher via signals-DATE.csv / terminator-DATE.log.

Usage : python -m research.live_lab.reconcile_live [--date YYYY-MM-DD]
Sortie : print + append research/live_lab/results/reconcile-history.csv
"""
import os, sys, json, argparse
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from bot.live_signals import rsi30_bblo_signal, oversold_roc_signal

ROOT = os.path.dirname(os.path.dirname(HERE))
COLLECTED = os.path.join(ROOT, 'data', 'collected_live')
COMPUTED = os.path.join(ROOT, 'data', 'computed')
HIST = os.path.join(HERE, 'results', 'reconcile-history.csv')
PM_LO, PM_HI, PM_LIQ_MIN = 480, 570, 0.35

# détecteurs déployés, dans l'ORDRE du terminator (④ d'abord), == config live
DETECTORS = [
    ('rsi30_bblo', rsi30_bblo_signal, dict(gap_min=14.0, gap_max=9999.0, win=(570, 720), price=(3.0, 20.0), tp=0.20)),
    ('oversold_roc', oversold_roc_signal, dict(gap_min=30.0, gap_max=9999.0, win=(570, 720), price=(3.0, 20.0), tp=0.15)),
]


def _amin(a):
    return int(a[:2]) * 60 + int(a[3:5]) if a and ':' in str(a) else 0


def _bars(df_day, tk):
    g = df_day[df_day.ticker == tk].drop_duplicates(['ticker', 'date', 'datetime']).sort_values('datetime')
    out = []
    for _, r in g.iterrows():
        hh, mm = str(r['datetime']).split(':')[:2]
        out.append(dict(t=dtime(int(hh), int(mm)), o=r['o'], h=r['h'], l=r['l'], c=r['c'], v=r['v']))
    return out


def _pm_frac(bars):
    pm = [b for b in bars if PM_LO <= b['t'].hour * 60 + b['t'].minute < PM_HI and (b['v'] or 0) > 0]
    return len(pm) / (PM_HI - PM_LO)


def expected(day):
    """Trades que ④/n°3 AURAIENT dû prendre sur les bars du jour (point-in-time, comme le terminator)."""
    barp = os.path.join(COLLECTED, f'bars-{day}.parquet')
    trp = os.path.join(COMPUTED, f'tradable-{day}.json')
    metap = os.path.join(COLLECTED, f'meta-{day}.json')
    if not (os.path.exists(barp) and os.path.exists(trp)):
        return None
    df = pd.read_parquet(barp)
    tradable = json.load(open(trp))
    meta = json.load(open(metap)) if os.path.exists(metap) else {}
    exp = {}
    for tk, info in tradable.items():
        bars = _bars(df, tk)
        if len(bars) < 5:
            continue
        pc = meta.get(tk, {}).get('prev_close')
        if not pc:
            continue
        if _pm_frac(bars) < PM_LIQ_MIN:                 # même gate univers que le terminator
            continue
        amin = _amin(info.get('added'))
        for k in range(len(bars)):
            if bars[k]['t'].hour * 60 + bars[k]['t'].minute < amin:
                continue
            for name, fn, P in DETECTORS:               # ④ d'abord (priorité terminator)
                sig = fn(bars, bars[k]['t'], pc, **P)
                if sig:
                    exp[tk] = dict(strat=name, entry_min=bars[k]['t'].hour * 60 + bars[k]['t'].minute,
                                   entry=round(sig[0], 4))
                    break
            if tk in exp:
                break
    return exp


def actual(day):
    jp = os.path.join(COMPUTED, 'redcandlecatch-journal.csv')
    if not os.path.exists(jp):
        return {}
    df = pd.read_csv(jp); df.columns = [c.strip() for c in df.columns]
    d = df[(df['date'] == day) & (df['strat'].isin(['rsi30_bblo', 'oversold_roc']))]
    return {r['ticker']: dict(strat=r['strat'], entry=r['entry']) for _, r in d.iterrows()}


def main(day):
    exp = expected(day)
    if exp is None:
        print(f"[{day}] bars/tradable absents -> réconciliation impossible (jour férié / fetch non fait)")
        return
    act = actual(day)
    misses = sorted(set(exp) - set(act))        # attendu mais PAS pris
    unexp = sorted(set(act) - set(exp))         # pris mais PAS attendu
    matched = sorted(set(exp) & set(act))
    print(f"=== RÉCONCILIATION {day} (④ rsi30_bblo + n°3 oversold_roc) ===")
    print(f"attendus (bars EOD) : {len(exp)} | réels (journal) : {len(act)} | "
          f"concordants : {len(matched)} | RATÉS : {len(misses)} | inattendus : {len(unexp)}")
    for tk in misses:
        e = exp[tk]
        print(f"  RATÉ   {tk:6} {e['strat']:12} attendu @ {e['entry_min']//60:02d}:{e['entry_min']%60:02d} "
              f"prix {e['entry']} -> à vérifier (signals-{day}.csv / terminator-{day}.log : légitime ou bug ?)")
    for tk in unexp:
        print(f"  INATTENDU {tk:6} {act[tk]['strat']} (pris mais pas attendu sur bars EOD)")
    if not misses and not unexp:
        print("  ✅ aucun écart — le terminator a pris exactement ce qui était attendu.")
    row = dict(date=day, attendus=len(exp), reels=len(act), concordants=len(matched),
               rates=len(misses), inattendus=len(unexp),
               tickers_rates=';'.join(misses), tickers_inattendus=';'.join(unexp))
    hist = pd.read_csv(HIST) if os.path.exists(HIST) else pd.DataFrame()
    hist = hist[hist.date != day] if len(hist) else hist                 # idempotent
    pd.concat([hist, pd.DataFrame([row])], ignore_index=True).to_csv(HIST, index=False)
    print(f"-> historique {HIST}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ZoneInfo('America/New_York')).date().isoformat())
    a = ap.parse_args()
    main(a.date)
