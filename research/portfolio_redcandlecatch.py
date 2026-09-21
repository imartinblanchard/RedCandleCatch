#!/usr/bin/env python3
"""
Backtest PORTEFEUILLE de la stratégie RedCandleCatch (gappers PM, gap 10-20), compte 10 000$.
Event-driven intraday : gère le cash, les positions SIMULTANÉES (par heure entrée/sortie),
le sizing (% de l'équité/position), commissions IBKR. Rendement composé réel.
Compare dip -4% vs -5%, en balayant sizing × nb max de positions.

Lancer : source .venv/bin/activate && python research/portfolio_redcandlecatch.py
"""
import os, json, itertools
import numpy as np, pandas as pd
import engine
R = os.path.dirname(__file__)

STOP, ACT, TRAIL = 0.10, 0.05, 0.02
PMIN, PMAX = 3.0, 20.0
ES, HARD, XE = 570, 955, 960
INIT = 10_000.0
COMM_SH, COMM_MIN = 0.005, 1.0     # IBKR : 0,005$/action, min 1$/ordre
def slip_of(p): return max(0.0015, 0.015 / p)

DIPS = [0.04, 0.05]
FRACS = [0.10, 0.20, 0.33]         # part de l'équité par position
MAXPOS = [3, 5, 10]


def gen_trades(df, gap, DIP):
    """Renvoie [(entry_dt, exit_dt, entry_price, pnl%)] pour chaque ticker-jour éligible."""
    trades = []
    for (tk, date), g in df.groupby(['ticker', 'date'], sort=False):
        gp = gap.get((tk, date))
        if gp is None or not (10 <= gp < 20):
            continue
        g = g.reset_index(drop=True)
        mins = (g['datetime'].str.slice(0, 2).astype(int) * 60 + g['datetime'].str.slice(3, 5).astype(int)).values
        o = g['o'].values; h = g['h'].values; l = g['l'].values; c = g['c'].values
        dt = g['datetime'].values
        move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
        i0 = -1
        for i in range(len(c)):
            if ES <= mins[i] < HARD and o[i] > 0 and move[i] <= -DIP and PMIN <= c[i] <= PMAX:
                i0 = i; break
        if i0 < 0:
            continue
        e = float(c[i0]); sl = slip_of(e); ef = e * (1 + sl)
        st, ac = e * (1 - STOP), e * (1 + ACT); activ = False; peak = e; ex = None; jx = len(c) - 1
        for j in range(i0 + 1, len(c)):
            if mins[j] < ES or mins[j] >= XE:
                continue
            if mins[j] >= HARD:
                ex = c[j]; jx = j; break
            if not activ:
                if l[j] <= st: ex = st; jx = j; break
                peak = max(peak, h[j])
                if h[j] >= ac: activ = True
            else:
                ts = peak * (1 - TRAIL)
                if l[j] <= ts: ex = ts; jx = j; break
                peak = max(peak, h[j])
        if ex is None:
            ex = float(c[jx])
        pnl = (ex * (1 - sl) - ef) / ef * 100
        edt = pd.Timestamp(f"{date} {dt[i0]}"); xdt = pd.Timestamp(f"{date} {dt[jx]}")
        trades.append((edt, xdt, e, pnl))
    return trades


def simulate(trades, FRAC, MAXPOS_):
    events = []
    for idx, (edt, xdt, ep, pnl) in enumerate(trades):
        events.append((edt, 1, idx))   # 1 = entrée
        events.append((xdt, 0, idx))   # 0 = sortie (traitée avant les entrées de même heure)
    events.sort(key=lambda e: (e[0], e[1]))
    cash = INIT; openp = {}; peak = INIT; maxdd = 0.0; nt = 0
    for time, typ, idx in events:
        if typ == 0:
            if idx in openp:
                sh, ep = openp.pop(idx)
                pnl = trades[idx][3]
                cash += sh * ep * (1 + pnl / 100) - max(COMM_MIN, COMM_SH * sh)
        else:
            if len(openp) >= MAXPOS_:
                continue
            ep = trades[idx][2]
            equity = cash + sum(s * p for s, p in openp.values())
            alloc = min(equity * FRAC, cash)
            sh = int(alloc / ep)
            if sh < 1:
                continue
            cash -= sh * ep + max(COMM_MIN, COMM_SH * sh)
            openp[idx] = (sh, ep); nt += 1
        equity = cash + sum(s * p for s, p in openp.values())
        peak = max(peak, equity); maxdd = min(maxdd, equity / peak - 1)
    final = cash + sum(s * p for s, p in openp.values())
    return final, maxdd, nt


def main():
    df = engine.load_table(os.path.join(R, 'candles.parquet'))
    gap = {(x['ticker'], x['date']): x['gap'] for x in json.load(open(os.path.join(R, 'gappers.json')))}
    print(f"Compte départ : {INIT:,.0f}$ | commissions IBKR incluses\n")
    for DIP in DIPS:
        trades = gen_trades(df, gap, DIP)
        days = len({t[0].date() for t in trades})
        years = days / 252
        print(f"===== DIP -{DIP*100:.0f}% ({len(trades)} trades, {days} jours) =====")
        print(f"  {'sizing':20}{'final$':>12}{'rend':>8}{'CAGR':>8}{'maxDD':>8}{'trades':>8}")
        for FRAC, MP in itertools.product(FRACS, MAXPOS):
            final, maxdd, nt = simulate(trades, FRAC, MP)
            cagr = (final / INIT) ** (1 / years) - 1 if years > 0 else 0
            print(f"  {f'{FRAC*100:.0f}%/pos max{MP}':20}{final:>12,.0f}{(final/INIT-1)*100:>+7.0f}%"
                  f"{cagr*100:>+7.0f}%{maxdd*100:>+7.0f}%{nt:>8}")
        print()


if __name__ == '__main__':
    main()
