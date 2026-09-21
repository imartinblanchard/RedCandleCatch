#!/usr/bin/env python3
"""Gap mesuré au PLUS-HAUT pré-marché (actuel) vs À L'OUVERTURE : impact en P&L de compte.

Config déployée : gap 10-20%, prix 3-20$, PM vol >= 100k, minutes actives >= 60,
dip -5%, stop -10%, activation +5%, trail 2%.

Sortie : expectancy par trade ET courbe de capital (20% du capital par position,
plafond 4 simultanées, commissions IBKR réelles, composé)."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
GMIN, GMAX = 10.0, 20.0
PM_VOL_MIN, PM_MIN_MINUTES = 100_000, 60
CAP0, PCT, MAXPOS = 5000.0, 0.20, 4
CUT = '2026-06-01'
def slip_of(p): return max(0.0015, 0.015 / p)
def commission(sh, px): return min(max(sh * 0.005, 1.00), 0.01 * sh * px)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
meta = {(x['ticker'], x['date']): x for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    m = meta.get((tk, date))
    if m is None:
        continue
    g = g.reset_index(drop=True)
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
            + g['datetime'].str.slice(3, 5).astype(int)).values
    o = g['o'].values; h = g['h'].values; l = g['l'].values
    c = g['c'].values; v = g['v'].values
    pm = (mins >= 240) & (mins < 570)
    rth = (mins >= 570) & (mins < 990)
    if not rth.any() or not pm.any():
        continue
    # --- filtres de liquidité (identiques au live) ---
    pm_vol = float(v[pm].sum())
    pm_minutes = int((v[pm] > 0).sum())
    if pm_vol < PM_VOL_MIN or pm_minutes < PM_MIN_MINUTES:
        continue
    pc = float(g['prev_close'].iloc[0]) if 'prev_close' in g else np.nan
    if not pc or pc <= 0 or np.isnan(pc):
        continue
    # --- les DEUX définitions du gap ---
    gap_high = (h[pm].max() - pc) / pc * 100          # actuel
    at930 = g[mins == 570]
    if len(at930) == 0:
        continue
    gap_open = (float(at930['o'].iloc[0]) - pc) / pc * 100   # à l'ouverture

    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]; eraw = float(c[i]); sl = slip_of(eraw)
    st = eraw * (1 - STOP); ac = eraw * (1 + ACT)
    activ = False; peak = eraw; ex = None; t_out = int(mins[rth][-1])
    for j in range(i + 1, len(g)):
        if not rth[j]:
            continue
        if not activ:
            if l[j] <= st: ex = st; t_out = int(mins[j]); break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; t_out = int(mins[j]); break
            peak = max(peak, h[j])
    if ex is None:
        ex = float(c[rth][-1])
    rows.append(dict(date=date, gap_high=gap_high, gap_open=gap_open,
                     t_in=int(mins[i]), t_out=t_out, entry=eraw,
                     exit_px=ex * (1 - sl), pnl=(ex * (1 - sl) - eraw) / eraw * 100))

L = pd.DataFrame(rows)

def equity(sub):
    sub = sub.sort_values(['date', 't_in'])
    cap = CAP0; pris = 0
    eq = []
    for d, day in sub.groupby('date', sort=True):
        openp = []
        for r in day.itertuples():
            openp = [p for p in openp if p > r.t_in]
            if len(openp) >= MAXPOS:
                continue
            size = cap * PCT; sh = int(size / r.entry)
            if sh < 1 or sh * r.entry > cap:
                continue
            pnl = sh * (r.exit_px - r.entry) - commission(sh, r.entry) - commission(sh, r.exit_px)
            openp.append(r.t_out); cap += pnl; pris += 1
        eq.append((d, cap))
    e = pd.DataFrame(eq, columns=['date', 'cap'])
    dd = (e.cap / e.cap.cummax() - 1).min() * 100
    return cap, pris, dd

print()
for lab, sub in [("ACTUEL  — gap PM-high 10-20%", L[(L.gap_high >= GMIN) & (L.gap_high < GMAX)]),
                 ("PROPOSÉ — gap OUVERTURE 10-20%", L[(L.gap_open >= GMIN) & (L.gap_open < GMAX)])]:
    if len(sub) < 10:
        print(f"{lab}: trop peu de trades ({len(sub)})"); continue
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    t = sub.pnl.mean() / (sub.pnl.std(ddof=1) / np.sqrt(len(sub)))
    te = sub[sub.date >= CUT].pnl.mean()
    fin, pris, dd = equity(sub)
    print(f"{lab}")
    print(f"   n={len(sub):>4}  exp={sub.pnl.mean():+.2f}%/tr  win={100*(sub.pnl>0).mean():>3.0f}%  "
          f"pf={pf:.2f}  test={te:+.2f}  t={t:.2f}")
    print(f"   COMPTE : {CAP0:,.0f}$ -> {fin:,.0f}$  ({100*(fin/CAP0-1):+.0f}%)  "
          f"| {pris} trades pris | DD max {dd:.1f}%")
    print()
