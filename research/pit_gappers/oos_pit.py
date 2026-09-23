#!/usr/bin/env python3
"""PIT rebuild — VALIDATION OOS des poches prometteuses (train déc-avr / test mai-août).

On a repéré IN-SAMPLE : post-open gap 5-10% (+1.03%, t=2.87) et PM petits gaps. Comme on a
choisi ces cellules parmi ~14, il faut vérifier qu'elles TIENNENT hors échantillon (sinon =
bruit, cf le +2.19% look-ahead). Split strict par date. 1 entrée/ticker-jour, prix 3-20$.
"""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
t = pd.read_parquet(os.path.join(DATA, 'trades_grid.parquet'))
SPLIT = '2026-05-01'
def col(a, tr): return f"a{a:02d}_t{tr:02d}"


def fpd(df, dip, pmin=3.0, pmax=20.0):
    d = df[(df['dip_pct'] <= -dip) & (df['entry_price'].between(pmin, pmax))]
    return d.sort_values('entry_min').groupby(['ticker', 'date'], as_index=False).first()


def st(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0: return None
    exp = a.mean()
    tt = exp / (a.std(ddof=1) / np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0.0
    pf = a[a > 0].sum() / (-a[a < 0].sum() or 1e-9)
    return dict(n=n, exp=exp, t=tt, win=(a > 0).mean()*100, pf=pf)


def line(tag, fp, cc):
    tr_ = fp[fp['date'] < SPLIT][cc]; te_ = fp[fp['date'] >= SPLIT][cc]
    s1, s2 = st(tr_), st(te_)
    def f(s): return f"n={s['n']:>4} exp={s['exp']:>+6.2f}% t={s['t']:>+5.2f} pf={s['pf']:>4.2f}" if s else "n=0"
    verdict = ""
    if s1 and s2:
        verdict = " ✅ TIENT" if (s1['exp'] > 0 and s2['exp'] > 0 and s2['t'] > 1.5) else \
                  (" ⚠️ fragile" if s2['exp'] > 0 else " ❌ CASSE")
    print(f"  {tag:<20} TRAIN[{f(s1)}]  TEST[{f(s2)}]{verdict}")


GAPB = [(5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 100), (100, 500)]

print(f"OOS split: TRAIN < {SPLIT} <= TEST | prix 3-20$ | 1 entrée/jour\n")

print("===== POST-OPEN par gap%, dip 3% act 10% trail 2% =====")
po = t[t['phase'] == 'post-open']; fp = fpd(po, 3.0)
for lo, hi in GAPB:
    line(f"gap {lo}-{hi}%", fp[(fp['run_gap'] >= lo) & (fp['run_gap'] < hi)], col(10, 2))

print("\n===== POST-OPEN 5-10% — robustesse dip×trail (act 10%) =====")
for dip in (1.5, 2, 3):
    fp = fpd(po, dip); band = fp[(fp['run_gap'] >= 5) & (fp['run_gap'] < 10)]
    for tr in (1, 2, 3):
        line(f"dip{dip} trail{tr}", band, col(10, tr))

print("\n===== PM par gap%, dip 3% act 5% trail 2% =====")
pm = t[t['phase'] == 'PM']; fp = fpd(pm, 3.0)
for lo, hi in GAPB:
    line(f"gap {lo}-{hi}%", fp[(fp['run_gap'] >= lo) & (fp['run_gap'] < hi)], col(5, 2))

print("\n===== PM petits gaps 5-15% — robustesse dip×trail (act 5%) =====")
for dip in (1.5, 3, 5):
    fp = fpd(pm, dip); band = fp[(fp['run_gap'] >= 5) & (fp['run_gap'] < 15)]
    for tr in (1, 2):
        line(f"dip{dip} trail{tr}", band, col(5, tr))
