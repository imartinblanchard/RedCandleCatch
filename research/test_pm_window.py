#!/usr/bin/env python3
"""Le gap mesuré sur 04:00-08:59 (screener) vs 04:00-09:29 (bot live) : ça change quoi ?

Le screener utilise des bougies 1H et s'arrête à 08:59 (la bougie 9h contiendrait le
post-ouverture). Le bot live, lui, mesure jusqu'à 09:30. On recalcule le gap avec la
fenêtre COMPLÈTE depuis les bougies 1-min du parquet, puis on rejoue la stratégie.

⚠️ Limite : on ne peut refiner que les tickers DÉJÀ dans l'univers. Ceux qui n'auraient
qualifié qu'avec la fenêtre étendue sont absents du parquet (non mesurable ici)."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT, TRAIL = 0.05, 0.10, 0.05, 0.02
def slip_of(p): return max(0.0015, 0.015 / p)

df = engine.load_table(os.path.join(R, 'candles.parquet'))
gap_old = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}

rows = []
for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
    go = gap_old.get((tk, date))
    if go is None:
        continue
    g = g.reset_index(drop=True)
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60
            + g['datetime'].str.slice(3, 5).astype(int)).values
    o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
    pc = float(g['prev_close'].iloc[0]) if 'prev_close' in g else np.nan
    if not pc or pc <= 0 or np.isnan(pc):
        continue
    # gap recalculé sur la fenêtre COMPLÈTE 04:00-09:29
    pm_full = (mins >= 240) & (mins < 570)
    if not pm_full.any():
        continue
    gap_new = (h[pm_full].max() - pc) / pc * 100
    # gap sur la fenêtre du screener 04:00-08:59 (contrôle)
    pm_old = (mins >= 240) & (mins < 540)
    gap_ctrl = (h[pm_old].max() - pc) / pc * 100 if pm_old.any() else np.nan

    rth = (mins >= 570) & (mins < 990)
    if not rth.any():
        continue
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    pnl = np.nan
    if len(idx):
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
        pnl = (ex * (1 - sl) - eraw) / eraw * 100
    rows.append((date, go, gap_ctrl, gap_new, pnl))

L = pd.DataFrame(rows, columns=['date', 'gap_json', 'gap_0859', 'gap_0929', 'pnl'])
print(f"\n{len(L)} ticker-jours recalculés\n")

print("=== 1. LE GAP CHANGE-T-IL ? (04:00-08:59 -> 04:00-09:29) ===")
d = (L.gap_0929 - L.gap_0859).dropna()
print(f"  écart moyen : {d.mean():+.2f} pts | médiane {d.median():+.2f} | max {d.max():+.1f}")
print(f"  gap INCHANGÉ (le pic était avant 9h) : {100*(d<0.01).mean():.1f}% des cas")
print(f"  gap AUGMENTÉ de +5 pts ou plus       : {100*(d>=5).mean():.1f}%")

print("\n=== 2. MIGRATION ENTRE TRANCHES ===")
def bucket(x):
    return '10-20' if x < 20 else '20-50' if x < 50 else '50-100' if x < 100 else '100+'
L2 = L.dropna(subset=['gap_0859', 'gap_0929']).copy()
L2['b_old'] = L2.gap_0859.apply(bucket); L2['b_new'] = L2.gap_0929.apply(bucket)
mig = (L2.b_old != L2.b_new).mean()
print(f"  {100*mig:.1f}% des ticker-jours CHANGENT de tranche")
print(pd.crosstab(L2.b_old, L2.b_new).to_string())

print("\n=== 3. LA STRATÉGIE CHANGE-T-ELLE ? (tranche 10-20%, dip -5%, trail 2%) ===")
for col, lab in [('gap_0859', 'fenêtre screener 04:00-08:59'), ('gap_0929', 'fenêtre LIVE 04:00-09:29')]:
    s = L[(L[col] >= 10) & (L[col] < 20)].dropna(subset=['pnl'])
    pf = s.pnl[s.pnl > 0].sum() / (-s.pnl[s.pnl < 0].sum() or 1e-9)
    t = s.pnl.mean() / (s.pnl.std(ddof=1) / np.sqrt(len(s)))
    te = s[s.date >= '2026-06-01'].pnl.mean()
    print(f"  {lab:32} n={len(s):>4} exp={s.pnl.mean():+.2f}% win={100*(s.pnl>0).mean():.0f}% "
          f"pf={pf:.2f} test={te:+.2f} t={t:.2f}")
