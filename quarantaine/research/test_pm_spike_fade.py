#!/usr/bin/env python3
"""HYPOTHÈSE MARTIN (22/09) : les titres qui SPIKENT > 20% en pré-marché puis
REDESCENDENT dans la bande 10-20% à l'ouverture (9:30) — jamais testés, car notre
sélection par PLUS-HAUT PM les exclut (gap = max high 04:00->midi > 20 => hors bande).

DCOY-like : gros gap PM, fade dans la bande à l'open. Est-ce tradable ?

On calcule TOUT depuis candles.parquet (prev_close par ligne) — pas de dépendance à
gappers.json. Populations comparées, même moteur de sortie que le bot déployé
(STOP -10%, activation adaptative, TRAIL 2%). Slippage modélisé comme test_gap_at_open."""
import os
import numpy as np, pandas as pd

R = os.path.dirname(__file__)
PMIN = 3.0
LIQ = 200_000            # $ dollar-vol min sur la bougie de dip (0 = off) — surchargé plus bas

def slip_of(p): return max(0.0015, 0.015 / p)

df = pd.read_parquet(os.path.join(R, 'candles.parquet'),
                     columns=['ticker','date','o','h','l','c','v','datetime','prev_close'])
df['min'] = df['datetime'].str.slice(0,2).astype(int)*60 + df['datetime'].str.slice(3,5).astype(int)

def simulate(g, mins, i0, DIP, STOP, ACT, TRAIL):
    """Cherche le 1er dip -DIP à partir de i0, rejoue stop/activation/trail. Renvoie pnl% ou None."""
    N = len(mins)
    for i in range(i0, N):
        if mins[i] < 570 or mins[i] >= 955:   # entrées 9:30 -> 15:55
            continue
        o, c = g['o'][i], g['c'][i]
        if o > 0 and (c - o)/o <= -DIP and c >= PMIN:
            if LIQ and g['v'][i]*c < LIQ:      # bougie de dip trop fine -> skip (réalisme)
                continue
            eraw = float(c); sl = slip_of(eraw)
            st = eraw*(1-STOP); ac = eraw*(1+ACT); activ = False; peak = eraw; ex = None
            for j in range(i+1, N):
                if mins[j] < 570 or mins[j] >= 985:
                    continue
                lo, hi = g['l'][j], g['h'][j]
                if not activ:
                    if lo <= st: ex = st; break
                    peak = max(peak, hi)
                    if hi >= ac: activ = True
                else:
                    ts = peak*(1-TRAIL)
                    if lo <= ts: ex = ts; break
                    peak = max(peak, hi)
            if ex is None:
                tail = [g['c'][k] for k in range(i+1, N) if 570 <= mins[k] < 985]
                ex = float(tail[-1]) if tail else eraw
            return (ex*(1-sl) - eraw)/eraw*100
    return None

def classify_and_run(DIP, ACT, TRAIL, STOP=0.10):
    """Renvoie dict population -> liste de pnl%."""
    pops = {'NEW pm>20 & open10-20': [], 'baseline pm10-20': [], 'open10-20 (tout PM)': []}
    for (tk, date), grp in df.groupby(['ticker','date'], sort=False):
        grp = grp.sort_values('min')
        mins = grp['min'].to_numpy()
        g = {k: grp[k].to_numpy() for k in ('o','h','l','c','v')}
        pc = float(grp['prev_close'].iloc[0])
        if not pc or pc <= 0:
            continue
        pm = mins < 570
        if not pm.any():
            continue
        pm_high = float(g['h'][pm].max())
        pm_gap = (pm_high - pc)/pc*100
        at930 = np.where(mins == 570)[0]
        if len(at930) == 0:
            continue
        open_px = float(g['o'][at930[0]])
        open_gap = (open_px - pc)/pc*100
        i930 = int(at930[0])

        in_new = pm_gap > 20 and 10 <= open_gap <= 20
        in_base = 10 <= pm_gap <= 20
        in_open = 10 <= open_gap <= 20
        if not (in_new or in_base or in_open):
            continue
        pnl = simulate(g, mins, i930, DIP, STOP, ACT, TRAIL)
        if pnl is None:
            continue
        if in_new:  pops['NEW pm>20 & open10-20'].append(pnl)
        if in_base: pops['baseline pm10-20'].append(pnl)
        if in_open: pops['open10-20 (tout PM)'].append(pnl)
    return pops

def stats(pnls):
    a = np.array(pnls, float)
    n = len(a)
    if n == 0: return None
    wins = a[a > 0]; losses = a[a < 0]
    exp = a.mean()
    win_rate = len(wins)/n*100
    avg_w = wins.mean() if len(wins) else 0
    avg_l = losses.mean() if len(losses) else 0
    rr = (avg_w/abs(avg_l)) if len(losses) and avg_l != 0 else float('inf')
    pf = (wins.sum()/abs(losses.sum())) if losses.sum() != 0 else float('inf')
    t = exp/(a.std(ddof=1)/np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0
    return dict(n=n, exp=exp, win=win_rate, rr=rr, pf=pf, t=t, avg_w=avg_w, avg_l=avg_l)

CONFIGS = [
    ('post-open (dip1.5/act10/tr2)', 0.015, 0.10, 0.02),
    ('PM-style   (dip5/act5/tr2)',   0.05,  0.05, 0.02),
    ('dip3/act5/tr2',                0.03,  0.05, 0.02),
]
print(f"candles.parquet: {df['date'].min()} -> {df['date'].max()}\n")
for liq in (0, 200_000):
    LIQ = liq
    print(f"############ FILTRE LIQUIDITÉ BOUGIE = ${liq:,} ############\n")
    for name, DIP, ACT, TRAIL in CONFIGS:
        print(f"=== CONFIG {name} ===")
        pops = classify_and_run(DIP, ACT, TRAIL)
        print(f"{'population':<26} {'n':>4} {'exp%':>7} {'win%':>6} {'R/R':>5} {'pf':>5} {'t':>6} {'avgW':>6} {'avgL':>6}")
        for pop, pnls in pops.items():
            s = stats(pnls)
            if s is None:
                print(f"{pop:<26}  (0 trades)"); continue
            print(f"{pop:<26} {s['n']:>4} {s['exp']:>7.2f} {s['win']:>6.1f} {s['rr']:>5.2f} "
                  f"{s['pf']:>5.2f} {s['t']:>6.2f} {s['avg_w']:>6.2f} {s['avg_l']:>6.2f}")
        print()
