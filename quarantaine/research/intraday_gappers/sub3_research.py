#!/usr/bin/env python3
"""Gappers SOUS 3$ : notre stratégie dip (jamais testée <3$, PMIN était 3) a-t-elle un edge ?
Compare bande 1-3$ (penny) vs 3-20$ (actuel), split PM / post-open. 8 mois.
⚠️ le backtest ne capture PAS les spreads larges des penny -> résultats ENCORE plus optimistes
qu'à l'habitude (borne très supérieure)."""
import os, json
import numpy as np
import pandas as pd
import backtest_intraday as B

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
STOP, TRAIL = 0.10, 0.02


def sim(g, dip, ACT, pmin, pmax):
    mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
    o, h, l, c = g['o'].values, g['h'].values, g['l'].values, g['c'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= B.ES) & (mins < B.EE) & (move <= -dip) & (c >= pmin) & (c < pmax))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (B.ES <= mins[j] < B.XE): continue
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        w = c[(mins >= B.ES) & (mins < B.XE)]; ex = float(w[-1]) if len(w) else e
    return (ex - e) / e * 100


def stats(a):
    a = np.array(a)
    if len(a) < 2: return None
    w = a[a > 0]; l = a[a < 0]
    rr = (w.mean() / abs(l.mean())) if len(w) and len(l) else float('nan')
    return dict(n=len(a), win=100 * (a > 0).mean(), rr=rr, exp=a.mean(), pf=w.sum() / (-l.sum() or 1e-9), tot=a.sum())


def run(groups, meta, sess_post, dip, ACT, band):
    res = []
    for (tk, date), g in groups:
        m = meta.get(f'{tk}|{date}')
        if not m or bool(m.get('post_open')) != sess_post:
            continue
        p = sim(g, dip, ACT, band[0], band[1])
        if p is not None: res.append(p)
    return res


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    groups = list(df.groupby(['ticker', 'date'], sort=False))
    H = f"{'bande prix':14}{'n':>5}{'win%':>6}{'R/R':>6}{'exp/tr':>8}{'pf':>6}{'TOTAL%':>8}"
    for sess_post, dip, ACT, name in [(True, 0.015, 0.10, 'POST-OPEN (dip -1,5%, act +10%)'),
                                      (False, 0.05, 0.05, 'PM (dip -5%, act +5%)')]:
        print(f"\n=== {name} ===")
        print(H)
        for band, lb in [((1.0, 3.0), 'SOUS 3$ (1-3)'), ((3.0, 20.0), '3-20$ (actuel)')]:
            s = stats(run(groups, meta, sess_post, dip, ACT, band))
            if not s: print(f'{lb:14} n<2'); continue
            flag = ' 🟢' if (s['exp'] > 2 and s['rr'] > 1 and s['n'] >= 30) else ''
            print(f"{lb:14}{s['n']:>5}{s['win']:>5.0f}%{s['rr']:>6.2f}{s['exp']:>+7.2f}%{s['pf']:>6.2f}{s['tot']:>+7.0f}%{flag}")
    print("\n⚠️ backtest = spreads penny NON modélisés -> sous-3$ surestimé. 🟢 = exp>2 & R/R>1 & n>=30.")


if __name__ == '__main__':
    main()
