#!/usr/bin/env python3
"""Sweep du dip sur les POST-OPEN runners, détaillé (win%, trades/j, total%) en OOS."""
import os, json
import numpy as np, pandas as pd
import backtest_intraday as B

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
DIPS = [0.01, 0.015, 0.02, 0.025]


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    groups = list(df.groupby(['ticker', 'date'], sort=False))
    dates = sorted(df['date'].unique()); split = dates[len(dates) // 2]
    test_days = len([d for d in dates if d >= split])
    print(f"POST-OPEN runners | OOS split {split} | {test_days} jours TEST\n")
    print(f"{'dip':6}{'n':>6}{'tr/j':>6}{'win%':>6}{'gain+':>7}{'perte-':>8}{'exp/tr':>8}{'pf':>6}{'t':>5}{'TOTAL%':>8}")
    for dip in DIPS:
        B.DIP = dip
        te = []
        for (tk, date), g in groups:
            m = meta.get(f"{tk}|{date}")
            if not (m and m['post_open']) or date < split:
                continue
            mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
            p = B.trade(mins, g['o'].values, g['h'].values, g['l'].values, g['c'].values)
            if p is not None:
                te.append(p)
        x = np.array(te)
        if len(x) < 2:
            print(f"-{dip*100:.1f}%  n<2"); continue
        wins = x[x > 0]; losses = x[x < 0]
        pf = wins.sum() / (-losses.sum() or 1e-9)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        print(f"-{dip*100:>4.1f}%{len(x):>6}{len(x)/test_days:>6.1f}{100*(x>0).mean():>5.0f}%"
              f"{wins.mean():>+6.1f}%{losses.mean():>+7.1f}%{x.mean():>+7.2f}%{pf:>6.2f}{t:>5.1f}{x.sum():>+7.0f}%")
    print("\n(TEST out-of-sample seul ; tr/j = trades/jour ; TOTAL% = somme mise fixe)")


if __name__ == '__main__':
    main()
