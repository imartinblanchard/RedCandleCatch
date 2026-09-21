#!/usr/bin/env python3
"""Trailing très serré : jusqu'où ça tient ? (gap 10-20%, dip -5%, stop -10%, act +5%)

Le trailing serré est le paramètre dominant, mais c'est aussi le plus exposé au
réalisme des fills : un TRAIL natif déclenche un ordre AU MARCHÉ, donc le prix
obtenu peut être sous le niveau théorique. Plus le trail est serré, plus ce coût
pèse en proportion du gain.

=> On teste chaque trailing sous 3 hypothèses de coût de sortie : normal, ×2, ×3.
Si l'edge survit à ×3, il est réel. S'il s'évapore, le trailing serré est un artefact."""
import os, json
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

DIP, STOP, ACT = 0.05, 0.10, 0.05
TRAILS = [0.005, 0.010, 0.015, 0.020, 0.025, 0.030, 0.040]
MULTS = [1, 2, 3]
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
    last_close = float(c[rth][-1])
    chg = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    idx = np.where((mins >= 570) & (mins < 960) & (chg <= -DIP) & (c >= 3))[0]
    if len(idx) == 0:
        continue
    i = idx[0]
    eraw = float(c[i]); base_sl = slip_of(eraw)
    js = [j for j in range(i + 1, len(g)) if rth[j]]

    for T in TRAILS:
        st = eraw * (1 - STOP); ac = eraw * (1 + ACT)
        activ = False; peak = eraw; ex = None; how = 'EOD'
        for j in js:
            if not activ:
                if l[j] <= st: ex = st; how = 'STOP'; break
                peak = max(peak, h[j])
                if h[j] >= ac: activ = True
            else:
                ts = peak * (1 - T)
                if l[j] <= ts: ex = ts; how = 'TRAIL'; break
                peak = max(peak, h[j])
        if ex is None:
            ex = last_close
        for m in MULTS:
            rows.append((date, T, m, how, (ex * (1 - base_sl * m) - eraw) / eraw * 100))

L = pd.DataFrame(rows, columns=['date', 'trail', 'mult', 'how', 'pnl'])

print("\n=== TRAILING SERRÉ — sensibilité au coût de sortie ===")
print(f"{'trail':>7} | " + " | ".join(f"{'slip ×'+str(m):>22}" for m in MULTS))
print(f"{'':7} | " + " | ".join(f"{'exp':>7}{'pf':>7}{'test':>8}" for m in MULTS))
for T in TRAILS:
    cells = []
    for m in MULTS:
        s = L[(L.trail == T) & (L.mult == m)]
        pf = s.pnl[s.pnl > 0].sum() / (-s.pnl[s.pnl < 0].sum() or 1e-9)
        te = s[s.date >= CUT].pnl.mean()
        cells.append(f"{s.pnl.mean():>+7.2f}{pf:>7.2f}{te:>+8.2f}")
    print(f"{T*100:>6.1f}% | " + " | ".join(cells))

print("\n=== RÉPARTITION DES SORTIES (slip ×1) ===")
print(f"{'trail':>7}{'n':>6}{'%TRAIL':>9}{'%STOP':>8}{'%EOD':>8}{'win':>7}")
for T in TRAILS:
    s = L[(L.trail == T) & (L.mult == 1)]
    n = len(s)
    print(f"{T*100:>6.1f}%{n:>6}"
          f"{100*(s.how=='TRAIL').mean():>8.0f}%{100*(s.how=='STOP').mean():>7.0f}%"
          f"{100*(s.how=='EOD').mean():>7.0f}%{100*(s.pnl>0).mean():>6.0f}%")

print("\n=== GAIN MOYEN PAR TYPE DE SORTIE (slip ×1) ===")
for T in [0.005, 0.010, 0.020, 0.040]:
    s = L[(L.trail == T) & (L.mult == 1)]
    parts = " ".join(f"{k}={v:+.2f}%" for k, v in s.groupby('how').pnl.mean().items())
    print(f"  trail {T*100:>4.1f}% : {parts}")
