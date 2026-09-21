#!/usr/bin/env python3
"""Le seuil gap>=50% est-il justifié ? On teste les gappers SOUS 50% avec la config
two-phase actuelle (dip -3%, stop -10%, activation +5%, trail 4%, slippage réaliste).

Le seuil 50 venait de la recherche initiale (config trailing 6%, différente)."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.03, 0.10, 0.05, 0.04
CUT = '2026-06-01'                      # split train/test
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    gp = gap.get((tk, date))
    if gp is None:
        continue
    g = g.reset_index(drop=True)
    mins = g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)
    for i in range(len(g)):
        if mins.iat[i] < 570 or mins.iat[i] >= 960:
            continue
        r = g.iloc[i]
        if r.o > 0 and (r.c - r.o) / r.o <= -DIP and r.c >= 3:
            eraw = float(r.c); sl = slip_of(eraw)
            st = eraw * (1 - STOP); ac = eraw * (1 + ACT); activ = False; peak = eraw; ex = None
            for j in range(i + 1, len(g)):
                if mins.iat[j] < 570 or mins.iat[j] >= 990:
                    continue
                rr = g.iloc[j]
                if not activ:
                    if rr.l <= st: ex = st; break
                    peak = max(peak, rr.h)
                    if rr.h >= ac: activ = True
                else:
                    ts = peak * (1 - TRAIL)
                    if rr.l <= ts: ex = ts; break
                    peak = max(peak, rr.h)
            if ex is None:
                ex = float(g['c'][(mins >= 570) & (mins < 990)].iloc[-1])
            rows.append((date, gp, (ex * (1 - sl) - eraw) / eraw * 100))
            break

L = pd.DataFrame(rows, columns=['date', 'gap', 'pnl'])

def stats(sub, label):
    if len(sub) < 1:
        print(f"{label:22} 0 trade"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    tr = sub[sub.date < CUT]; te = sub[sub.date >= CUT]
    print(f"{label:22} n={len(sub):>5}  exp={sub.pnl.mean():+.2f}%/tr  win={100*(sub.pnl>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  | train={tr.pnl.mean() if len(tr) else float('nan'):+.2f}  "
          f"test={te.pnl.mean() if len(te) else float('nan'):+.2f}")

print(f"\n{len(L)} trades au total\n")
print("=== PAR TRANCHE DE GAP ===")
for lo, hi in [(10,20),(20,30),(30,40),(40,50),(50,100),(100,200),(200,1e9)]:
    stats(L[(L.gap >= lo) & (L.gap < hi)], f"gap {lo}-{hi if hi<1e9 else 'inf'}")

print("\n=== SEUILS CUMULÉS (gap >= X) ===")
for x in [10,20,30,40,50,60,80,100]:
    stats(L[L.gap >= x], f"gap >= {x}")
