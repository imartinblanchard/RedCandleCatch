#!/usr/bin/env python3
"""Quel seuil de DIP (% de baisse sur une bougie 1-min) selon la taille du gap ?

Le -3% actuel a été optimisé sur les gros gappers (>=50%). Sur des gappers 10-20%,
moins volatils, l'optimum est probablement ailleurs.

Sortie two-phase inchangée : stop -10%, activation +5%, trail 4%, slippage réaliste.
Split train/test au 2026-06-01 pour détecter le sur-ajustement."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

STOP, ACT, TRAIL = 0.10, 0.05, 0.04
DIPS = [0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.050]
CUT = '2026-06-01'
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    gp = gap.get((tk, date))
    if gp is None:
        continue
    g = g.reset_index(drop=True)
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
            + g['datetime'].str.slice(3, 5).astype(int)).values
    o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
    rth = (mins >= 570) & (mins < 990)
    if not rth.any():
        continue
    last_close = c[rth][-1]
    entry_ok = (mins >= 570) & (mins < 960)
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)

    for d in DIPS:
        idx = np.where(entry_ok & (chg <= -d) & (c >= 3))[0]
        if len(idx) == 0:
            continue
        i = idx[0]
        eraw = float(c[i]); sl = slip_of(eraw)
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
            ex = float(last_close)
        rows.append((date, gp, d, (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'gap', 'dip', 'pnl'])

def show(sub, title):
    print(f"\n=== {title} ===")
    print(f"{'dip':>6}{'n':>7}{'exp%/tr':>10}{'win':>6}{'pf':>7}{'total':>9}{'train':>9}{'test':>9}")
    for d in DIPS:
        s = sub[sub.dip == d]
        if len(s) < 20:
            print(f"{d*100:>5.1f}%{len(s):>7}   (trop peu)"); continue
        pf = s.pnl[s.pnl > 0].sum() / (-s.pnl[s.pnl < 0].sum() or 1e-9)
        tr = s[s.date < CUT].pnl.mean(); te = s[s.date >= CUT].pnl.mean()
        print(f"{d*100:>5.1f}%{len(s):>7}{s.pnl.mean():>+10.2f}{100*(s.pnl>0).mean():>5.0f}%"
              f"{pf:>7.2f}{s.pnl.sum():>+9.0f}{tr:>+9.2f}{te:>+9.2f}")

show(L[(L.gap >= 10) & (L.gap < 20)], "GAPPERS 10-20% (candidat)")
show(L[L.gap >= 50], "GAPPERS >=50% (actuel)")
show(L[(L.gap >= 20) & (L.gap < 50)], "GAPPERS 20-50%")
