#!/usr/bin/env python3
"""Faut-il mesurer le gap au PLUS-HAUT pré-marché (actuel) ou À L'OUVERTURE (9:30) ?

Cas AENT 11/09 : pic à 28,99$ à 04:10 => gap PM-high 426%, mais à 9:30 il n'était
plus qu'à +31,9% -> il n'aurait jamais dû être sélectionné.

On rejoue la two-phase (dip -3%, stop -10%, activation +5%, trail 4%) et on compare
les deux définitions du filtre gap>=50%."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.03, 0.10, 0.05, 0.04
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    gp = gap.get((tk, date))
    if gp is None or gp < 50:          # univers actuel : gap PM-high >= 50
        continue
    g = g.reset_index(drop=True)
    mins = g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)

    # --- gap À L'OUVERTURE : open de la bougie 9:30 vs clôture veille ---
    at930 = g[mins == 570]
    if len(at930) == 0:
        continue
    pc = float(at930['prev_close'].iloc[0])
    if not pc or pc <= 0:
        continue
    gap_open = (float(at930['o'].iloc[0]) - pc) / pc * 100

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
            rows.append((date, gp, gap_open, (ex * (1 - sl) - eraw) / eraw * 100))
            break

L = pd.DataFrame(rows, columns=['date', 'gap_pmhigh', 'gap_open', 'pnl'])

def stats(sub, label):
    if len(sub) == 0:
        print(f"{label:34} 0 trade"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    print(f"{label:34} n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%/tr  "
          f"win={100*(sub.pnl>0).mean():>3.0f}%  pf={pf:.2f}  total={sub.pnl.sum():+.0f}")

print()
stats(L, "ACTUEL  (gap PM-high >= 50)")
stats(L[L.gap_open >= 50], "PROPOSÉ (gap À L'OUVERTURE >= 50)")
print()
print("Les trades ÉCARTÉS par la nouvelle règle (pumpés à 4h puis retombés) :")
stats(L[L.gap_open < 50], "  écartés (gap_open < 50)")
print()
print("Détail des écartés par tranche de gap à l'ouverture :")
for lo, hi in [(-1e9, 0), (0, 20), (20, 35), (35, 50)]:
    stats(L[(L.gap_open >= lo) & (L.gap_open < hi)], f"  gap_open {lo if lo>-1e9 else '<0'}-{hi}")
