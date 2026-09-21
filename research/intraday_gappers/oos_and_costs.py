#!/usr/bin/env python3
"""
Items 3 & 4 (recherche, isolé) sur les post-open runners (dip -2%) :
  ITEM 4 — OOS du seuil d'ACTIVATION du trail (train/test).
  ITEM 3 — expectancy NETTE après COMMISSIONS IBKR selon la taille de position
           (le backtest brut ignore les commissions -> optimiste, surtout à 1 action).

Commissions IBKR (fixed) : 0,005$/action, min 1,00$/ordre, max 1% de la valeur. Par côté.
"""
import os, json, math
import numpy as np, pandas as pd
import backtest_intraday as B

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')


def trade_with_entry(mins, o, h, l, c):
    """Comme B.trade mais renvoie (pnl_pct, entry_price)."""
    chg = np.divide(c - o, o, out=np.full_like(c, 1.0), where=o > 0)
    idx = np.where((mins >= B.ES) & (mins < B.EE) & (chg <= -B.DIP) & (c >= B.PMIN) & (c <= B.PMAX))[0]
    if not len(idx):
        return None
    i = idx[0]; e = float(c[i]); sl = B.slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - B.STOP), e * (1 + B.ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if not (B.ES <= mins[j] < B.XE):
            continue
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - B.TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        win = c[(mins >= B.ES) & (mins < B.XE)]
        ex = float(win[-1]) if len(win) else e
    return (ex * (1 - sl) - ef) / ef * 100, e


def collect(groups, meta, split=None):
    """Renvoie (pnls, entries) pour les post-open runners. split=None -> tout ;
    sinon renvoie (train, test) selon la date."""
    tr_p, tr_e, te_p, te_e = [], [], [], []
    for (tk, date), g in groups:
        m = meta.get(f"{tk}|{date}")
        if not (m and m['post_open']):
            continue
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
        r = trade_with_entry(mins, g['o'].values, g['h'].values, g['l'].values, g['c'].values)
        if r is None:
            continue
        pnl, e = r
        if split is None or date < split:
            tr_p.append(pnl); tr_e.append(e)
        else:
            te_p.append(pnl); te_e.append(e)
    return (tr_p, tr_e, te_p, te_e)


def stat(p):
    x = np.array(p)
    if len(x) < 2:
        return None
    return len(x), x.mean(), 100 * (x > 0).mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def commission_pct(pnls, entries, pos_dollars):
    """Expectancy NETTE (%) après commissions IBKR, pour une position de pos_dollars."""
    nets = []
    for pnl, e in zip(pnls, entries):
        shares = max(1, int(pos_dollars / e))
        val = shares * e
        comm = min(max(1.00, 0.005 * shares), 0.01 * val)      # par côté
        gross = val * pnl / 100
        net = gross - 2 * comm
        nets.append(net / val * 100)
    return np.mean(nets)


def main():
    df = pd.read_parquet(os.path.join(DATA, 'bars_1min.parquet'))
    meta = json.load(open(os.path.join(DATA, 'meta.json')))
    groups = list(df.groupby(['ticker', 'date'], sort=False))
    dates = sorted(df['date'].unique()); split = dates[len(dates) // 2]
    B.DIP = 0.02

    print("=== ITEM 4 — OOS du seuil d'ACTIVATION (post-open, dip -2%) ===")
    print(f"split train/test au {split}")
    print(f"{'activ':>6} | {'TRAIN n/exp/t':>22} | {'TEST n/exp/t':>22}")
    for act in [0.02, 0.05, 0.07, 0.10, 0.12, 0.15]:
        B.ACT = act
        trp, tre, tep, tee = collect(groups, meta, split)
        s1, s2 = stat(trp), stat(tep)
        f = lambda s: f"n={s[0]:>4} {s[1]:+.2f}% t{s[3]:+.1f}" if s else "n<2"
        print(f"{act*100:>5.0f}% | {f(s1):>22} | {f(s2):>22}")

    print("\n=== ITEM 3 — expectancy NETTE après commissions (dip -2%, activ +5% et +10%) ===")
    for act in [0.05, 0.10]:
        B.ACT = act
        allp, alle, _, _ = collect(groups, meta, None)
        gross = np.mean(allp)
        print(f"\n  activation +{act*100:.0f}%  (brut = {gross:+.2f}%/tr, n={len(allp)})")
        print(f"    {'position':>12} {'commission drag':>16} {'exp NETTE':>10}")
        for pos in [500, 1000, 5000, 10000, 25000]:
            net = commission_pct(allp, alle, pos)
            print(f"    {pos:>10,}$ {gross-net:>14.2f}% {net:>+9.2f}%")


if __name__ == '__main__':
    main()
