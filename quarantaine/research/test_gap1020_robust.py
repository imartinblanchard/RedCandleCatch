#!/usr/bin/env python3
"""La tranche gap 10-20% tient-elle la route ? Tests de robustesse :
  1. mois par mois (vs gap>=50 actuel)
  2. sous-tranches 10-15 / 15-20 (stabilité interne)
  3. significativité statistique (t-stat + bootstrap IC 95%)
  4. faisabilité pratique (nb de trades/jour = positions simultanées)
Config two-phase : dip -3%, stop -10%, activation +5%, trail 4%, slippage réaliste."""
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
            rows.append((tk, date, gp, eraw, (ex * (1 - sl) - eraw) / eraw * 100))
            break

L = pd.DataFrame(rows, columns=['ticker', 'date', 'gap', 'price', 'pnl'])
L['dt'] = pd.to_datetime(L['date'])
L['mois'] = L['dt'].dt.to_period('M')

A = L[(L.gap >= 10) & (L.gap < 20)]     # candidat
B = L[L.gap >= 50]                       # actuel

def line(sub, label):
    if len(sub) == 0:
        print(f"{label:16} 0"); return
    pf = sub.pnl[sub.pnl > 0].sum() / (-sub.pnl[sub.pnl < 0].sum() or 1e-9)
    print(f"{label:16} n={len(sub):>5} exp={sub.pnl.mean():+.2f}% win={100*(sub.pnl>0).mean():>3.0f}% pf={pf:.2f}")

print("\n=== 1. MOIS PAR MOIS ===")
print(f"{'mois':10}{'GAP 10-20':>26}{'GAP >=50 (actuel)':>28}")
print(f"{'':10}{'n':>6}{'exp':>9}{'total':>11}{'n':>8}{'exp':>9}{'total':>11}")
mois = sorted(set(A.mois) | set(B.mois))
a_pos = b_pos = 0
for m in mois:
    a = A[A.mois == m]; b = B[B.mois == m]
    ae, at = (a.pnl.mean(), a.pnl.sum()) if len(a) else (np.nan, 0)
    be, bt = (b.pnl.mean(), b.pnl.sum()) if len(b) else (np.nan, 0)
    if at > 0: a_pos += 1
    if bt > 0: b_pos += 1
    print(f"{str(m):10}{len(a):>6}{ae:>+9.2f}{at:>+11.0f}{len(b):>8}{be:>+9.2f}{bt:>+11.0f}")
print(f"\nmois gagnants : GAP 10-20 = {a_pos}/{len(mois)}   |   GAP>=50 = {b_pos}/{len(mois)}")

print("\n=== 2. SOUS-TRANCHES (stabilité interne) ===")
for lo, hi in [(10, 13), (13, 16), (16, 20)]:
    line(L[(L.gap >= lo) & (L.gap < hi)], f"gap {lo}-{hi}")

print("\n=== 3. SIGNIFICATIVITÉ ===")
for sub, lab in [(A, 'gap 10-20'), (B, 'gap >=50')]:
    x = sub.pnl.values
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    rng = np.random.default_rng(0)
    boot = np.array([rng.choice(x, len(x), replace=True).mean() for _ in range(2000)])
    lo95, hi95 = np.percentile(boot, [2.5, 97.5])
    print(f"  {lab:10} moyenne={x.mean():+.2f}%  t-stat={t:>5.2f}  "
          f"IC95%=[{lo95:+.2f} ; {hi95:+.2f}]  {'✅ significatif' if lo95 > 0 else '⚠️ NON significatif (IC inclut 0)'}")

print("\n=== 4. FAISABILITÉ (positions simultanées) ===")
for sub, lab in [(A, 'gap 10-20'), (B, 'gap >=50')]:
    par_jour = sub.groupby('date').size()
    print(f"  {lab:10} {len(par_jour)} jours actifs | trades/jour: moyenne={par_jour.mean():.1f} "
          f"médiane={par_jour.median():.0f} max={par_jour.max()}")
