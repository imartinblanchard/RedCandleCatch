#!/usr/bin/env python3
"""Quel seuil de liquidité pour écarter les titres INTRADABLES sans tuer l'edge ?

Le backtest dit que le faible volume PM est "meilleur", mais son slippage (0,15%)
est irréaliste sur un titre qui échange 6 actions. On cherche le seuil qui retire
les non-tradables en gardant le maximum d'edge.

Deux mesures testées :
  A) volume PRÉ-MARCHÉ (ce qu'on filtrait avant)
  B) volume de la BOUGIE D'ENTRÉE + volume RTH cumulé à l'entrée
     -> mesure directe de "puis-je remplir mon ordre à cet instant"
"""
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
    rth = (mins >= 570) & (mins < 990)
    if not rth.any():
        continue
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]; eraw = float(c[i]); sl = slip_of(eraw)
    vol_bar = float(v[i])                                   # volume de la bougie d'entrée
    vol_rth = float(v[(mins >= 570) & (mins <= mins[i])].sum())   # cumul RTH à l'entrée
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
    rows.append((date, m['pm_vol'], vol_bar, vol_rth, eraw,
                 (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'pm_vol', 'vol_bar', 'vol_rth', 'entry', 'pnl'])
L['dollars_bar'] = L.vol_bar * L.entry
print(f"\n{len(L)} trades (gap 10-20%, dip -5%, trail 2%)\n")

def line(sub, lab):
    if len(sub) < 20:
        print(f"  {lab:24} n={len(sub):>4}   (échantillon trop faible)"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    t = sub.pnl.mean() / (sub.pnl.std(ddof=1) / np.sqrt(len(sub)))
    te = sub[sub.date >= CUT].pnl.mean()
    print(f"  {lab:24} n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%  win={100*(sub.pnl>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  test={te:+.2f}  t={t:.2f}")

print("=== A) seuil sur le VOLUME PRÉ-MARCHÉ ===")
line(L, "aucun (backtest)")
for thr in [500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000]:
    line(L[L.pm_vol >= thr], f"pm_vol >= {thr:,}")

print("\n=== B) seuil sur le VOLUME DE LA BOUGIE D'ENTRÉE (actions) ===")
for thr in [100, 250, 500, 1_000, 2_000, 5_000]:
    line(L[L.vol_bar >= thr], f"bougie >= {thr:,} act.")

print("\n=== C) seuil sur le $ ÉCHANGÉ dans la bougie d'entrée ===")
for thr in [1_000, 2_500, 5_000, 10_000, 25_000, 50_000]:
    line(L[L.dollars_bar >= thr], f"bougie >= {thr:,}$")

print("\n=== D) volume RTH cumulé à l'instant de l'entrée ===")
for thr in [5_000, 10_000, 25_000, 50_000, 100_000]:
    line(L[L.vol_rth >= thr], f"RTH cumulé >= {thr:,}")

print("\n=== Combien de trades sont VRAIMENT intradables ? ===")
for lab, mask in [("bougie < 100 actions", L.vol_bar < 100),
                  ("bougie < 500 actions", L.vol_bar < 500),
                  ("bougie < 1 000 $", L.dollars_bar < 1000),
                  ("bougie < 5 000 $", L.dollars_bar < 5000)]:
    s = L[mask]
    print(f"  {lab:24} {len(s):>4} trades ({100*len(s)/len(L):>4.1f}%)  "
          f"exp={s.pnl.mean() if len(s) else float('nan'):+.2f}%")
