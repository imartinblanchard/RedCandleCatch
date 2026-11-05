#!/usr/bin/env python3
"""PIT rebuild — lecture de la grille (trades_grid.parquet), tout en tranches (propre).

1) grille DIP × TRAILING par phase (PM / post-open), activation déployée.
2) meilleur combo (dip×act×trail) par phase.
3) quel GAP% performe le mieux (PM vs post-open).
4) un gapper éligible plus TARD (post-open) est-il meilleur ?
Une entrée/ticker-jour (1re bougie de dip qualifiante). Point-in-time, sans look-ahead.
"""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
t = pd.read_parquet(os.path.join(DATA, 'trades_grid.parquet'))
TEST_START = '2026-05-01'
DIPS = [1.5, 2, 3, 4, 5, 6]
TRAILS = [1, 2, 3, 4, 6]
ACTS = [5, 10, 15]
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


print(f"grille : {len(t)} dips | dates {t['date'].min()}..{t['date'].max()} | prix 3-20$ | 1 entrée/jour\n")

# 1) DIP × TRAILING par phase (activation déployée : PM=5, post-open=10)
for phase, act in [('PM', 5), ('post-open', 10)]:
    sub = t[t['phase'] == phase]
    print(f"===== {phase} — DIP × TRAILING (act {act}%) : exp% (t) =====")
    print("dip\\trail  " + "".join(f"{tr:>13}%" for tr in TRAILS))
    for dip in DIPS:
        fp = fpd(sub, dip)
        cells = []
        for tr in TRAILS:
            s = st(fp[col(act, tr)])
            cells.append(f"{s['exp']:>+6.2f}({s['t']:>+4.1f})" if s else "      -     ")
        n = len(fp)
        print(f"  {dip:>4}%   " + "".join(f"{c:>14}" for c in cells) + f"   n={n}")
    print()

# 2) meilleur combo par phase (n>=150, trié par exp)
print("===== MEILLEUR COMBO par phase (n>=150) =====")
for phase in ('PM', 'post-open'):
    sub = t[t['phase'] == phase]
    best = []
    for dip in DIPS:
        fp = fpd(sub, dip)
        for a in ACTS:
            for tr in TRAILS:
                s = st(fp[col(a, tr)])
                if s and s['n'] >= 150:
                    best.append((s['exp'], s['t'], s['n'], dip, a, tr))
    best.sort(reverse=True)
    print(f"  {phase} : top 3")
    for exp, tt, n, dip, a, tr in best[:3]:
        print(f"    dip {dip}% act {a}% trail {tr}% -> exp {exp:+.2f}% t={tt:+.2f} n={n}")
    print()

# 3) GAP% — quelle bande performe le mieux (PM vs post-open), au combo déployé
GAPB = [(5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 100), (100, 500)]
print("===== GAP% (run_gap à l'entrée) — PM vs post-open, dip 3% trail 2% =====")
for phase, act in [('PM', 5), ('post-open', 10)]:
    sub = t[t['phase'] == phase]
    fp = fpd(sub, 3.0)
    print(f"  --- {phase} (act {act}%) ---")
    for lo, hi in GAPB:
        s = st(fp[(fp['run_gap'] >= lo) & (fp['run_gap'] < hi)][col(act, 2)])
        if s: print(f"    gap {lo:>3}-{hi:<3}% : n={s['n']:>4} exp={s['exp']:>+6.2f}% "
                    f"win={s['win']:>3.0f}% pf={s['pf']:>4.2f} t={s['t']:>+5.2f}")
    print()

# 4) heure d'éligibilité (post-open) — un gapper plus tardif est-il meilleur ?
print("===== HEURE D'ÉLIGIBILITÉ (post-open, dip 1.5% act 10% trail 2%) =====")
BK = [(570, 585, '09:30-09:45'), (585, 600, '09:45-10:00'), (600, 630, '10:00-10:30'),
      (630, 690, '10:30-11:30'), (690, 780, '11:30-13:00'), (780, 960, '13:00+')]
sub = t[t['phase'] == 'post-open']
fp = fpd(sub, 1.5)
for lo, hi, lab in BK:
    s = st(fp[(fp['elig_min'] >= lo) & (fp['elig_min'] < hi)][col(10, 2)])
    if s: print(f"  éligible {lab:<12} n={s['n']:>4} exp={s['exp']:>+6.2f}% "
                f"win={s['win']:>3.0f}% pf={s['pf']:>4.2f} t={s['t']:>+5.2f}")
