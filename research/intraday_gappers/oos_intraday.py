#!/usr/bin/env python3
"""
Étape 4 — Validation OUT-OF-SAMPLE du dip sur les post-open runners.
Split par DATE : train = 1re moitié, test = 2e moitié. Si l'edge du dip -2/-3% tient
sur le test (données non vues), c'est du vrai ; sinon c'était du sur-ajustement.
"""
import os, json
import numpy as np, pandas as pd
import backtest_intraday as B

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')


def stat(pnls):
    if len(pnls) < 2:
        return None
    x = np.array(pnls); pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return len(x), x.mean(), 100 * (x > 0).mean(), pf, t


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    dates = sorted(df['date'].unique())
    split = dates[len(dates) // 2]
    print(f"Période {dates[0]} -> {dates[-1]} | split au {split}")
    print(f"TRAIN < {split}  |  TEST >= {split}  (post-open runners uniquement)\n")

    groups = list(df.groupby(['ticker', 'date'], sort=False))
    print(f"{'dip':>4} | {'TRAIN n/exp/pf/t':>28} | {'TEST n/exp/pf/t':>28}")
    for dip in [0.02, 0.03, 0.04, 0.05]:
        B.DIP = dip
        tr, te = [], []
        for (tk, date), g in groups:
            m = meta.get(f"{tk}|{date}")
            if not (m and m['post_open']):
                continue
            mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
            p = B.trade(mins, g['o'].values, g['h'].values, g['l'].values, g['c'].values)
            if p is None:
                continue
            (tr if date < split else te).append(p)
        s1, s2 = stat(tr), stat(te)
        f = lambda s: f"n={s[0]:>4} {s[1]:+.2f}% pf{s[2 if False else 3]:.2f} t{s[4]:+.1f}" if s else "n<2"
        print(f"{dip*100:>3.0f}% | {f(s1):>28} | {f(s2):>28}")

    print("\n(edge confirmé OOS si le TEST reste positif avec t>=2)")


if __name__ == '__main__':
    main()
