#!/usr/bin/env python3
"""Peut-on RÉ-INCLURE les gappers PM (post_open=False) de façon rentable ?
Baseline connue (dip -5%, act +5%) = faible : exp +0,69%, R/R 0,55. On cherche un SOUS-ENSEMBLE
tradeable : par profondeur de dip, sous-fourchette de gap, liquidité de la bougie. 8 mois.
Objectif : exp > ~2% (battre les commissions), R/R > 1, n suffisant."""
import os, json
import numpy as np
import pandas as pd
import backtest_intraday as B
import validate_8mois as V

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def load():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    return list(df.groupby(['ticker', 'date'], sort=False)), meta


def pm_trades(groups, meta, dip, ACT=0.05):
    """-> liste de (pnl, dvol, gap) pour les PM (post_open=False)."""
    out = []
    for (tk, date), g in groups:
        m = meta.get(f'{tk}|{date}')
        if not m or m.get('post_open'):        # PM seulement
            continue
        r = V.sim(g, dip, ACT)                 # (pnl, dvol)
        if r:
            out.append((r[0], r[1], m.get('morning_gap', 0)))
    return out


def stats(rows, thr=0, gaprange=None):
    x = [(p, d, gp) for p, d, gp in rows if d >= thr and (gaprange is None or gaprange[0] <= gp < gaprange[1])]
    a = np.array([p for p, _, _ in x])
    if len(a) < 2:
        return None
    w = a[a > 0]; l = a[a < 0]
    rr = (w.mean() / abs(l.mean())) if len(w) and len(l) else float('nan')
    pf = w.sum() / (-l.sum() or 1e-9)
    return dict(n=len(a), win=100 * (a > 0).mean(), rr=rr, exp=a.mean(), pf=pf, tot=a.sum())


def line(tag, s):
    if not s:
        print(f'{tag:22} n<2'); return
    flag = ' 🟢' if (s['exp'] > 2 and s['rr'] > 1 and s['n'] >= 30) else ''
    print(f"{tag:22}{s['n']:>5}{s['win']:>5.0f}%{s['rr']:>6.2f}{s['exp']:>+7.2f}%{s['pf']:>6.2f}{s['tot']:>+7.0f}%{flag}")


def main():
    groups, meta = load()
    H = f"{'':22}{'n':>5}{'win%':>6}{'R/R':>6}{'exp/tr':>8}{'pf':>6}{'TOTAL%':>8}"

    print("=== PM — PROFONDEUR DE DIP (act +5%, tout PM) ===")
    print(H)
    for dip in [0.05, 0.06, 0.07, 0.08, 0.10]:
        line(f'dip -{dip*100:.0f}%', stats(pm_trades(groups, meta, dip)))

    print("\n=== PM — dip -6%, par SOUS-FOURCHETTE de gap ===")
    print(H)
    rows6 = pm_trades(groups, meta, 0.06)
    for lo, hi in [(10, 13), (13, 16), (16, 20)]:
        line(f'gap {lo}-{hi}%', stats(rows6, gaprange=(lo, hi)))

    print("\n=== PM — dip -6% + FILTRE liquidité bougie ===")
    print(H)
    for thr in [0, 100000, 200000, 500000]:
        line(f'dip-vol >= ${thr/1e3:.0f}K', stats(rows6, thr=thr))

    print("\n=== PM — meilleur combo candidat : dip -6/-7 + gap bas + liq ===")
    print(H)
    for dip in [0.06, 0.07]:
        r = pm_trades(groups, meta, dip)
        line(f'dip -{dip*100:.0f}% gap10-13 200K', stats(r, thr=200000, gaprange=(10, 13)))
    print("\n🟢 = candidat tradeable (exp>2% & R/R>1 & n>=30). Rappel : commissions ~2% A/R.")


if __name__ == '__main__':
    main()
