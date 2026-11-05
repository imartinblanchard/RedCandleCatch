#!/usr/bin/env python3
"""
Étape 3 — Backtest du dip sur les gappers INTRADAY. ISOLÉ.
Rejoue la config LIVE (dip -6%, stop -10%, act +5%, trail 2%, prix 3-20, fenêtre RTH)
sur chaque ticker-jour, et COMPARE :
  - post-open runners (le cas raté par le bot)  vs  PM-gappers déjà captés.
Peak calculé uniquement sur les bougies APRÈS l'entrée (leçon RedCandleCatch 15/09).
"""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
DIP, STOP, ACT, TRAIL = 0.06, 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
ES, EE, XE = 570, 960, 990
def slip_of(p): return max(0.0015, 0.015 / p)


def trade(mins, o, h, l, c):
    chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
    idx = np.where((mins >= ES) & (mins < EE) & (chg <= -DIP) & (c >= PMIN) & (c <= PMAX))[0]
    if not len(idx):
        return None
    i = idx[0]; e = float(c[i]); sl = slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (ES <= mins[j] < XE):
            continue
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        win = c[(mins >= ES) & (mins < XE)]
        ex = float(win[-1]) if len(win) else e
    return (ex * (1 - sl) - ef) / ef * 100


def stats(pnls, label):
    if not pnls:
        print(f"  {label:28} aucun trade"); return
    x = np.array(pnls); pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
    print(f"  {label:28} n={len(x):>5} exp={x.mean():+.2f}% win={100*(x>0).mean():>3.0f}% "
          f"pf={pf:.2f} total={x.sum():>+7.0f}% t={t:>5.1f}")


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    print(f"{df.groupby(['ticker','date']).ngroups} ticker-jours, {len(df)} bougies\n")
    post, pm = [], []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
        pnl = trade(mins, g['o'].values, g['h'].values, g['l'].values, g['c'].values)
        if pnl is None:
            continue
        m = meta.get(f"{tk}|{date}")
        (post if m and m['post_open'] else pm).append(pnl)

    print("=== Stratégie dip -6% : POST-OPEN runners vs PM-gappers ===")
    stats(pm, "PM-gappers (déjà captés)")
    stats(post, "POST-OPEN (le cas raté)")
    stats(pm + post, "TOUS (intraday)")
    print("\nRéférence : PM-gappers gap 10-20 dip 6% dans candles.parquet = +2,15%/tr (t=6,4)")


if __name__ == '__main__':
    main()
