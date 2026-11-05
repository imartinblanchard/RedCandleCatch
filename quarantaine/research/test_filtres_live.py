#!/usr/bin/env python3
"""Les filtres du bot LIVE (non validés) aident-ils ou nuisent-ils ?

Le backtest qui donne +1,97%/tr n'utilise que : gap 10-20%, prix>=3, dip -5%.
Le bot live ajoute : PM vol >= 50k, float 0.2-50M, ratings chart/volume.

Le float et les ratings ne sont PAS testables (pas d'historique fondamental), mais
le PM volume est dans gappers.json -> on mesure son effet réel."""
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
    o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
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
    rows.append((date, m['pm_vol'], eraw, (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'pm_vol', 'entry', 'pnl'])
print(f"\n{len(L)} trades (gap 10-20%, dip -5%, trail 2%)\n")

def line(sub, lab):
    if len(sub) < 20:
        print(f"{lab:26} n={len(sub):>4} (trop peu)"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    t = sub.pnl.mean() / (sub.pnl.std(ddof=1) / np.sqrt(len(sub)))
    te = sub[sub.date >= CUT].pnl.mean()
    print(f"{lab:26} n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%  win={100*(sub.pnl>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  test={te:+.2f}  t={t:.2f}")

print("=== EFFET DU FILTRE PM VOLUME ===")
line(L, "AUCUN filtre (backtest)")
for thr in [10_000, 25_000, 50_000, 100_000, 250_000]:
    line(L[L.pm_vol >= thr], f"PM vol >= {thr:,}")

print("\n=== et les trades ÉCARTÉS par le filtre 50k ? ===")
line(L[L.pm_vol < 50_000], "PM vol < 50k (rejetés)")
