#!/usr/bin/env python3
"""Edge par niveau de FLOAT. Joint float_cache.json au trades_grid, applique la règle
post-open DÉPLOYÉE (phase post-open, gap ENCORE dans 5-10 à l'entrée = recheck, dip 1.5%,
act10/trail2 = colonne a10_t02, 1/jour, prix 3-20), et bucket par float. OOS train/test.
Bonus : PM petits gaps 5-15 par float. ⚠️ float Finviz = actuel, pas historique (approx)."""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
SPLIT = '2026-05-01'
t = pd.read_parquet(os.path.join(DATA, 'trades_grid.parquet'))
cache = json.load(open(os.path.join(DATA, 'float_cache.json')))
fl = {tk: (v['float'] / 1e6 if v.get('float') else None) for tk, v in cache.items()}
t['float_m'] = t['ticker'].map(fl)


def fpd(df, dip=1.5, pmin=3, pmax=20):
    d = df[(df['dip_pct'] <= -dip) & (df['entry_price'].between(pmin, pmax))]
    return d.sort_values('entry_min').groupby(['ticker', 'date'], as_index=False).first()


def st(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0: return None
    exp = a.mean(); tt = exp/(a.std(ddof=1)/np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0
    return dict(n=n, exp=exp, t=tt, win=(a > 0).mean()*100)


def bucket_report(pop, col, buckets, dip):
    fp = fpd(pop, dip)
    print(f"{'float (M actions)':<18} {'n':>5} {'exp%':>7} {'t':>6} {'win%':>5} | {'TEST exp/t/n':>18}")
    for lo, hi, lab in buckets:
        if lab == 'inconnu':
            sub = fp[fp['float_m'].isna()]
        else:
            sub = fp[(fp['float_m'] >= lo) & (fp['float_m'] < hi)]
        s = st(sub[col]); te = st(sub[sub.date >= SPLIT][col])
        if s:
            tv = f"{te['exp']:>+6.2f}/{te['t']:>+4.1f}/{te['n']:>4}" if te else "   -"
            print(f"  {lab:<16} {s['n']:>5} {s['exp']:>+7.2f} {s['t']:>+6.2f} {s['win']:>5.0f} | {tv}")
    # cumul "float < X"
    print("  -- cumul float < seuil --")
    for cap in (5, 10, 20, 50, 100):
        sub = fp[fp['float_m'] < cap]
        s = st(sub[col]); te = st(sub[sub.date >= SPLIT][col])
        if s:
            tv = f"{te['exp']:>+6.2f}/{te['t']:>+4.1f}/{te['n']:>4}" if te else "   -"
            print(f"  float<{cap:<3}M        {s['n']:>5} {s['exp']:>+7.2f} {s['t']:>+6.2f} {s['win']:>5.0f} | {tv}")


BUCKETS = [(0, 5, '<5'), (5, 10, '5-10'), (10, 20, '10-20'), (20, 50, '20-50'),
           (50, 100, '50-100'), (100, 300, '100-300'), (300, 1e9, '>300'), (0, 0, 'inconnu')]

known = t['float_m'].notna().mean()*100
print(f"trades_grid {len(t)} dips | float connu pour {known:.0f}% des lignes | split OOS {SPLIT}\n")

print("=" * 74)
print("POST-OPEN DÉPLOYÉ (gap 5-10 recheck, dip1.5, act10/trail2) — edge par FLOAT")
print("=" * 74)
po = t[(t['phase'] == 'post-open') & (t['run_gap'] >= 5) & (t['run_gap'] <= 10)]
bucket_report(po, 'a10_t02', BUCKETS, 1.5)

print("\n" + "=" * 74)
print("PM petits gaps 5-15 (dip3, act5/trail2) — edge par FLOAT (bonus)")
print("=" * 74)
pm = t[(t['phase'] == 'PM') & (t['run_gap'] >= 5) & (t['run_gap'] <= 15)]
bucket_report(pm, 'a05_t02', BUCKETS, 3.0)
