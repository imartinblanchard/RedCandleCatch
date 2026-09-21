#!/usr/bin/env python3
"""La stratégie two-phase est-elle gagnante sur les gros gappers 'pumpés' que le
filtre anti-pump (rel-vol) exclurait ? Découpage par tranche de gap + par rvol d'entrée.

Two-phase : dip -3% (entrée), stop -10%, activation +5%, puis trailing 4% depuis le
sommet. Slippage réaliste. RTH 9:30-16:30. gap>=50 (sans plafond)."""
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
    if gp is None or gp < 50:
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
            entry_rvol = float(r.rvol) if not pd.isna(r.rvol) else np.nan
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
            pnl = (ex * (1 - sl) - eraw) / eraw * 100
            rows.append((date, gp, entry_rvol, pnl))
            break

L = pd.DataFrame(rows, columns=['date', 'gap', 'rvol', 'pnl'])
print(f"\nTOTAL : {len(L)} trades | expectancy {L.pnl.mean():+.2f}%/tr | "
      f"win {100*(L.pnl>0).mean():.0f}% | pf {L.pnl[L.pnl>0].sum()/-L.pnl[L.pnl<0].sum():.2f}\n")

def block(sub, label):
    if len(sub) == 0:
        print(f"{label:16} 0 trade"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    print(f"{label:16} n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%/tr  "
          f"win={100*(sub.pnl>0).mean():>3.0f}%  pf={pf:.2f}  tot={sub.pnl.sum():+.0f}")

print("=== PAR TRANCHE DE GAP (les extrêmes = ceux que l'anti-pump exclurait) ===")
for lo, hi in [(50,100),(100,200),(200,300),(300,1e9)]:
    block(L[(L.gap >= lo) & (L.gap < hi)], f"gap {lo}-{hi if hi<1e9 else '∞'}")

print("\n=== PAR RVOL D'ENTRÉE (proxy 'pump' intraday) ===")
Lr = L.dropna(subset=['rvol'])
for lo, hi in [(0,5),(5,15),(15,50),(50,1e9)]:
    block(Lr[(Lr.rvol >= lo) & (Lr.rvol < hi)], f"rvol {lo}-{hi if hi<1e9 else '∞'}")
