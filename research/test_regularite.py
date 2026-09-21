#!/usr/bin/env python3
"""Filtrer sur la RÉGULARITÉ du pré-marché plutôt que sur le volume total.

Cas FLWS : 44 170 actions en PM (volume total correct) MAIS volume médian par
bougie = 0 -> plus d'une minute sur deux sans transaction = intradable.
Un seuil sur le volume TOTAL ne détecte pas ça.

Alpaca n'émet pas de bougie quand rien ne trade => le NOMBRE de bougies PM
mesure directement le nombre de minutes réellement actives."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
CUT = '2026-06-01'
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
meta = {(x['ticker'], x['date']): x for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    m = meta.get((tk, date))
    if m is None or not (10 <= m['gap'] < 20):
        continue
    g = g.reset_index(drop=True)
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
            + g['datetime'].str.slice(3, 5).astype(int)).values
    o = g['o'].values; h = g['h'].values; l = g['l'].values
    c = g['c'].values; v = g['v'].values
    pm = (mins >= 240) & (mins < 570)
    n_pm_min = int(pm.sum())                       # minutes PM réellement actives
    med_pm = float(np.median(v[pm])) if n_pm_min else 0.0
    rth = (mins >= 570) & (mins < 990)
    if not rth.any():
        continue
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]; eraw = float(c[i]); sl = slip_of(eraw)
    st = eraw * (1 - STOP); ac = eraw * (1 + ACT)
    activ = False; peak = eraw; ex = None
    for j in range(i + 1, len(g)):
        if not rth[j]:
            continue
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        ex = float(c[rth][-1])
    rows.append((date, m['pm_vol'], n_pm_min, med_pm,
                 (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'pm_vol', 'pm_min', 'pm_med', 'pnl'])
print(f"\n{len(L)} trades\n")

def line(sub, lab):
    if len(sub) < 20:
        print(f"  {lab:30} n={len(sub):>4}   (trop peu)"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    t = sub.pnl.mean() / (sub.pnl.std(ddof=1) / np.sqrt(len(sub)))
    te = sub[sub.date >= CUT].pnl.mean()
    print(f"  {lab:30} n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%  win={100*(sub.pnl>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  test={te:+.2f}  t={t:.2f}")

line(L, "aucun filtre")
print("\n=== A) MINUTES ACTIVES en pré-marché ===")
for thr in [20, 40, 60, 80, 120, 160]:
    line(L[L.pm_min >= thr], f"minutes actives >= {thr}")

print("\n=== B) VOLUME MÉDIAN par bougie PM (régularité) ===")
for thr in [50, 100, 250, 500, 1000]:
    line(L[L.pm_med >= thr], f"médiane/bougie >= {thr}")

print("\n=== C) COMBINÉ : volume total ET régularité ===")
for vthr, mthr in [(1000, 40), (2000, 40), (5000, 60), (10000, 60), (10000, 80), (25000, 80)]:
    line(L[(L.pm_vol >= vthr) & (L.pm_min >= mthr)], f"vol>={vthr:,} & min>={mthr}")

print("\n=== profil des trades ÉCARTÉS par 'minutes actives >= 60' ===")
line(L[L.pm_min < 60], "minutes actives < 60")
print(f"\n  (pour référence : médiane des minutes actives = {L.pm_min.median():.0f})")
