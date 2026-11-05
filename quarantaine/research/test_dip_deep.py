#!/usr/bin/env python3
"""Jusqu'où le dip profond reste-t-il payant sur les gappers 10-20% ?
On pousse au-delà de -5% et on vérifie la robustesse (mois par mois + train/test)."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

STOP, ACT, TRAIL = 0.10, 0.05, 0.04
DIPS = [0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15]
CUT = '2026-06-01'
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    gp = gap.get((tk, date))
    if gp is None or not (10 <= gp < 20):
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
        rows.append((date, d, (ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'dip', 'pnl'])
L['mois'] = pd.to_datetime(L['date']).dt.to_period('M')

print("\n=== DIP PROFOND sur gappers 10-20% ===")
print(f"{'dip':>6}{'n':>7}{'exp%/tr':>10}{'win':>6}{'pf':>7}{'total':>9}{'train':>9}{'test':>9}{'t-stat':>8}")
for d in DIPS:
    s = L[L.dip == d]
    if len(s) < 30:
        print(f"{d*100:>5.1f}%{len(s):>7}   (échantillon trop faible)"); continue
    pf = s.pnl[s.pnl > 0].sum() / (-s.pnl[s.pnl < 0].sum() or 1e-9)
    tr = s[s.date < CUT].pnl; te = s[s.date >= CUT].pnl
    t = s.pnl.mean() / (s.pnl.std(ddof=1) / np.sqrt(len(s)))
    print(f"{d*100:>5.1f}%{len(s):>7}{s.pnl.mean():>+10.2f}{100*(s.pnl>0).mean():>5.0f}%"
          f"{pf:>7.2f}{s.pnl.sum():>+9.0f}"
          f"{tr.mean() if len(tr) else float('nan'):>+9.2f}{te.mean() if len(te) else float('nan'):>+9.2f}{t:>8.2f}")

print("\n=== COHÉRENCE MENSUELLE (mois gagnants / total) ===")
for d in DIPS:
    s = L[L.dip == d]
    if len(s) < 30:
        continue
    m = s.groupby('mois').pnl.agg(['size', 'mean', 'sum'])
    pos = (m['sum'] > 0).sum()
    print(f"  dip {d*100:>4.1f}% : {pos}/{len(m)} mois gagnants  "
          + " ".join(f"{str(k)[-2:]}:{v:+.1f}" for k, v in m['mean'].items()))
