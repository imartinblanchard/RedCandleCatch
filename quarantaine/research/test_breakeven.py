#!/usr/bin/env python3
"""(1) trades/jour dans le backtest vs aujourd'hui. (2) Règle STOP -> BREAKEVEN (0%) :
à +BE% de profit, on remonte le stop de -10% à l'entrée (zéro perte). Testé combiné avec
l'activation du trail. Data collectée (sans biais, classé par bougies)."""
import os
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC


def sim(g, dip, ACT, BE=None):
    """BE = seuil (ex 0.02) pour remonter le stop à l'entrée ; None = pas de breakeven."""
    mins = g['datetime'].map(BC.to_min).values
    o, h, l, c = g['o'].values, g['h'].values, g['l'].values, g['c'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= BC.RTH) & (mins < BC.HARD) & (move <= -dip) & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); sl = BC.slip_of(e); ef = e * (1 + sl)
    st = e * (1 - BC.STOP); ac = e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < BC.RTH or mins[j] >= BC.XE:
            continue
        if mins[j] >= BC.HARD:
            ex = c[j]; break
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if BE is not None and peak >= e * (1 + BE):
                st = max(st, e)                    # remonte le stop à l'entrée (breakeven)
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - BC.TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        w = c[(mins >= BC.RTH) & (mins < BC.XE)]
        ex = float(w[-1]) if len(w) else e
    return (ex * (1 - sl) - ef) / ef * 100


def rr(arr):
    x = np.array(arr); w = x[x > 0]; ls = x[x < 0]
    return (w.mean() / abs(ls.mean())) if len(w) and len(ls) else float('nan')


def main():
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    data = [(f[:-8], pd.read_parquet(os.path.join(BC.BARS_DIR, f))) for f in files]

    # (1) trades/jour
    perday = {}
    for date, df in data:
        n = 0
        for tk, g in df.groupby('ticker', sort=False):
            s = lab.get((date, tk))
            if s not in ('PM', 'post-open'):
                continue
            dip = 0.05 if s == 'PM' else 0.015
            if sim(g.reset_index(drop=True), dip, 0.05) is not None:
                n += 1
        perday[date] = n
    vals = np.array(list(perday.values()))
    print('(1) TRADES/JOUR dans le backtest (1 entrée/ticker, PAS de ré-entrée) :')
    for d, n in perday.items():
        print(f'    {d}: {n}')
    print(f'    -> moyenne {vals.mean():.1f}/j, max {vals.max()}  | AUJOURD HUI = 17 entrées (dont ré-entrées post-restart)\n')

    # (2) breakeven sweep, combiné, à ACT +5% et +10%
    def run(ACT, BE):
        res = []
        for date, df in data:
            for tk, g in df.groupby('ticker', sort=False):
                s = lab.get((date, tk))
                if s not in ('PM', 'post-open'):
                    continue
                dip = 0.05 if s == 'PM' else 0.015
                p = sim(g.reset_index(drop=True), dip, ACT, BE)
                if p is not None:
                    res.append(p)
        return res

    print('(2) STOP -> BREAKEVEN : à +BE% on remonte le stop à 0% (zéro perte). Combiné PM+post-open.')
    for ACT in [0.05, 0.10]:
        print(f'\n  ══ activation trail +{ACT*100:.0f}% ══')
        print(f'  {"breakeven":12}{"n":>5}{"win%":>6}{"gain+":>7}{"perte-":>8}{"R/R":>6}{"exp/tr":>8}{"pf":>6}{"TOTAL%":>8}')
        for BE in [None, 0.01, 0.02, 0.03]:
            s = BC.stats(run(ACT, BE))
            lb = 'aucun' if BE is None else f'+{BE*100:.0f}%'
            if not s:
                print(f'  {lb:12} n<2'); continue
            print(f'  {lb:12}{s["n"]:>5}{s["win"]:>5.0f}%{s["gain"]:>+6.1f}%{s["loss"]:>+7.1f}%'
                  f'{rr(run(ACT,BE)):>6.2f}{s["exp"]:>+7.2f}%{s["pf"]:>6.2f}{s["tot"]:>+7.0f}%')


if __name__ == '__main__':
    main()
