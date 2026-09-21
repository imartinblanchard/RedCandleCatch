#!/usr/bin/env python3
"""Portefeuille $10k, event-driven, sur la data collectée (sans biais, classé bougies),
filtre dip-candle $vol >= 200K. Sizing en % d'équité, positions concurrentes, compounding,
commissions IBKR. Sort : rendement du compte + MENSUEL moyen."""
import os
from datetime import datetime
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC

MIN_DVOL = 200_000
ACT = 0.05                    # activation actuelle du bot (+5%)
COMM_PER_SIDE = 0.0035        # ~0,35%/côté (IBKR micro-ordres, borne prudente)


def trade(g, dip):
    """-> (entry_dt, exit_dt, pnl_frac, dvol) ou None."""
    g = g.sort_values('datetime').reset_index(drop=True)
    mins = g['datetime'].map(BC.to_min).values
    o, h, l, c, v = g['o'].values, g['h'].values, g['l'].values, g['c'].values, g['v'].values
    dt = g['datetime'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= BC.RTH) & (mins < BC.HARD) & (move <= -dip) & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); dvol = float(v[i] * c[i])
    sl = BC.slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - BC.STOP), e * (1 + ACT); activ = False; peak = e; ex = None; xi = len(c) - 1
    for j in range(i + 1, len(c)):
        if mins[j] < BC.RTH or mins[j] >= BC.XE:
            continue
        if mins[j] >= BC.HARD: ex = c[j]; xi = j; break
        if not activ:
            if l[j] <= st: ex = st; xi = j; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - BC.TRAIL)
            if l[j] <= ts: ex = ts; xi = j; break
            peak = max(peak, h[j])
    if ex is None:
        ex = float(c[-1])
    pnl = (ex * (1 - sl) - ef) / ef          # fraction (avant commission)
    return dt[i], dt[xi], pnl, dvol


def portfolio(trades, frac, maxpos, start=10000.0):
    """trades = [(entry_dt, exit_dt, pnl_frac)] triés. Sizing frac*équité, cap maxpos."""
    events = []
    for k, (ein, xout, pnl) in enumerate(trades):
        events.append((ein, 'in', k)); events.append((xout, 'out', k))
    events.sort(key=lambda z: (z[0], 0 if z[1] == 'out' else 1))   # sorties avant entrées à t égal
    cash = start; equity = start; open_pos = {}; size = {}
    curve = [start]                                                # équité après chaque événement
    for t, typ, k in events:
        if typ == 'out':
            if k in open_pos:
                notional = size[k]
                pnl = trades[k][2]
                gross = notional * (1 + pnl)
                comm = notional * COMM_PER_SIDE + gross * COMM_PER_SIDE
                cash += gross - comm
                del open_pos[k]; del size[k]
        else:
            if len(open_pos) < maxpos:
                notional = min(frac * (cash + sum(size.values())), cash)
                if notional > 1:
                    cash -= notional
                    open_pos[k] = t; size[k] = notional
        equity = cash + sum(size.values())
        curve.append(equity)
    final = cash + sum(size.values())
    # max drawdown (pic -> creux) sur la courbe d'équité
    arr = np.array(curve); peak = np.maximum.accumulate(arr)
    maxdd = float(((arr - peak) / peak).min())
    return final, maxdd


def main():
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    trades = []
    for f in files:
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BC.BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            s = lab.get((date, tk))
            if s not in ('PM', 'post-open'):
                continue
            r = trade(g, 0.05 if s == 'PM' else 0.015)
            if r and r[3] >= MIN_DVOL:
                trades.append((datetime.strptime(f'{date} {r[0]}', '%Y-%m-%d %H:%M'),
                               datetime.strptime(f'{date} {r[1]}', '%Y-%m-%d %H:%M'), r[2]))
    trades.sort(key=lambda z: z[0])
    ndays = len({t[0].date() for t in trades})
    print(f"Portefeuille $10k | filtre dip-candle >= ${MIN_DVOL/1e3:.0f}K | activation +{ACT*100:.0f}%")
    print(f"{len(trades)} trades sur {ndays} jours de bourse | commission {COMM_PER_SIDE*100:.2f}%/côté\n")
    print(f"{'sizing':22}{'final $':>12}{'rendement':>11}{'maxDD':>8}{'/mois (x21j)':>14}{'rendt/DD':>10}")
    for frac, maxpos in [(0.10, 10), (0.20, 5), (0.33, 3), (0.50, 2), (1.00, 1)]:
        final, maxdd = portfolio(trades, frac, maxpos)
        ret = final / 10000 - 1
        dpr = (final / 10000) ** (1 / ndays) - 1
        monthly = (1 + dpr) ** 21 - 1
        rdd = ret / abs(maxdd) if maxdd < 0 else float('inf')
        print(f"{f'{int(frac*100)}%/pos max{maxpos}':22}{final:>12,.0f}{ret*100:>+10.0f}%"
              f"{maxdd*100:>+7.0f}%{monthly*100:>+13.0f}%{rdd:>10.1f}")
    print(f"\n⚠️ {len(trades)} trades / {ndays} jours = ÉCHANTILLON MINUSCULE. Le mensuel est une")
    print("EXTRAPOLATION (x21 jours) d'à peine ~1,5 semaine de data -> incertitude ÉNORME.")


if __name__ == '__main__':
    main()
