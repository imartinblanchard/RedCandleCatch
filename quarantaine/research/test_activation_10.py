#!/usr/bin/env python3
"""Impact d'un passage de l'activation du trail +5% -> +10% sur la config COMPLÈTE
(PM dip -5% + post-open dip -1,5%). Data collectée (sans biais, classé par bougies)
+ historique (N grand). Montre win%, exp, pf, TOTAL et régularité (jours + / -)."""
import os
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC


def sim(g, dip, ACT):
    mins = g['datetime'].map(BC.to_min).values
    o, h, l, c = g['o'].values, g['h'].values, g['l'].values, g['c'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= BC.RTH) & (mins < BC.HARD) & (move <= -dip) & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); sl = BC.slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - BC.STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < BC.RTH or mins[j] >= BC.XE:
            continue
        if mins[j] >= BC.HARD:
            ex = c[j]; break
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - BC.TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        w = c[(mins >= BC.RTH) & (mins < BC.XE)]
        ex = float(w[-1]) if len(w) else e
    return (ex * (1 - sl) - ef) / ef * 100


def line(tag, arr):
    s = BC.stats(arr)
    if not s:
        print(f'{tag:16} n<2'); return
    print(f'{tag:16}{s["n"]:>5}{s["win"]:>5.0f}%{s["exp"]:>+7.2f}%{s["pf"]:>6.2f}{s["t"]:>6.1f}{s["tot"]:>+8.0f}%')


def main():
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    data = [(f[:-8], pd.read_parquet(os.path.join(BC.BARS_DIR, f))) for f in files]

    print('=== DATA COLLECTÉE (sans biais) — config complète, +5% vs +10% ===')
    print(f'{"":16}{"n":>5}{"win%":>6}{"exp/tr":>7}{"pf":>6}{"t":>6}{"TOTAL%":>9}')
    for ACT in [0.05, 0.10]:
        pm, po = [], []
        daily = {}
        for date, df in data:
            for tk, g in df.groupby('ticker', sort=False):
                s = lab.get((date, tk))
                if s not in ('PM', 'post-open'):
                    continue
                dip = 0.05 if s == 'PM' else 0.015
                p = sim(g.reset_index(drop=True), dip, ACT)
                if p is not None:
                    (pm if s == 'PM' else po).append(p)
                    daily[date] = daily.get(date, 0) + p
        print(f'\n  ── activation +{ACT*100:.0f}% ──')
        line('  PM -5%', pm)
        line('  post-open -1,5%', po)
        line('  COMBINÉ', pm + po)
        dv = np.array(list(daily.values()))
        print(f'  régularité : {int((dv>0).sum())}/{len(dv)} jours positifs ({100*(dv>0).mean():.0f}%), '
              f'pire jour {dv.min():+.1f}%, meilleur {dv.max():+.1f}%')


if __name__ == '__main__':
    main()
