#!/usr/bin/env python3
"""
Momentum point-in-time + FILTRE DE RÉGIME de marché.

Overlay : chaque jour, on ne détient le panier momentum que si SPY > sa MM200 (la
veille, pour éviter le look-ahead) ; sinon CASH (rendement 0). Objectif : couper les
crashes momentum (2022) et remonter le Sharpe / réduire le drawdown.

Compare au momentum PIT sans filtre (meilleur = Sharpe 1.25) et à SPY (0.79).

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/momentum_regime.py
"""
import os, sys, math, itertools
import numpy as np, pandas as pd, requests
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import momentum_pit as M
from bot import config

INIT = 50_000.0; COST = 0.001
NS = [10, 20, 50]; LOOKBACKS = [126, 252]; SKIPS = [0]; FREQS = [5, 21]


def spy_regime(index):
    """Série booléenne alignée sur index : SPY > MM200 (décalé d'1 jour)."""
    h = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID, 'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}
    r = requests.get(f'{config.ALPACA_DATA_URL}/v2/stocks/SPY/bars', headers=h,
                     params={'timeframe': '1Day', 'start': '2020-09-01', 'end': '2026-09-14',
                             'adjustment': 'all', 'feed': 'sip', 'limit': 10000}, timeout=30)
    b = r.json()['bars']
    spy = pd.Series([x['c'] for x in b], index=pd.to_datetime([x['t'][:10] for x in b]))
    ma = spy.rolling(200).mean()
    reg = (spy > ma).shift(1)                       # régime de la VEILLE
    return reg.reindex(index).ffill().fillna(False)


def backtest(prices, rets, sd, ss, regime, N, lb, skip, freq):
    dates = prices.index
    reb_idx = set(range(lb + skip, len(dates), freq)); start = lb + skip
    pr = pd.Series(0.0, index=dates)
    basket, prev, invested = [], set(), False
    for di in range(start, len(dates)):
        on = bool(regime.iloc[di])
        if basket and on:
            r = rets.iloc[di][basket].mean()
            if r == r:
                pr.iloc[di] += r
        # coût quand on entre/sort du marché (régime bascule)
        if on != invested:
            pr.iloc[di] -= COST
            invested = on
        if di in reb_idx:
            d = dates[di]; elig = M.members_on(d, sd, ss)
            mom = prices.iloc[di - skip] / prices.iloc[di - lb] - 1
            mom = mom[[t for t in mom.index if t in elig]].dropna()
            nb = list(mom.sort_values(ascending=False).head(N).index)
            new = set(nb)
            if on:                                   # coût de turnover seulement si investi
                pr.iloc[di] -= (len(new.symmetric_difference(prev)) / (2 * N) if prev else 1.0) * COST * 2
            prev = new; basket = nb
    p = pr.iloc[start:]
    eq = INIT * (1 + p).cumprod(); years = len(p) / 252
    return dict(final=eq.iloc[-1], cagr=(eq.iloc[-1] / INIT) ** (1 / years) - 1,
                maxdd=(eq / eq.cummax() - 1).min(),
                sharpe=p.mean() / p.std() * math.sqrt(252) if p.std() > 0 else 0,
                pct_in=100 * (regime.iloc[start:].mean()))


def main():
    print("Chargement point-in-time + régime SPY...")
    prices, rets, sd, ss = M.load()
    regime = spy_regime(prices.index)
    print(f"{prices.shape[1]} titres | SPY>MM200 : {100*regime.mean():.0f}% du temps investi")
    print("Barres : SPY 0.79 | momentum PIT sans filtre = Sharpe 1.25 (maxDD -33.7%)\n")

    rows = []
    for N, lb, sk, fq in itertools.product(NS, LOOKBACKS, SKIPS, FREQS):
        m = backtest(prices, rets, sd, ss, regime, N, lb, sk, fq)
        rows.append(((N, lb, sk, fq), m))
    print(f"  {'config':26} {'final$':>11} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'%invest':>7}")
    for (N, lb, sk, fq), m in sorted(rows, key=lambda x: -x[1]['sharpe']):
        lab = f'top{N} {lb//21}mo reb{"W" if fq==5 else "M"}'
        print(f"  {lab:26} {m['final']:>11,.0f} {m['cagr']*100:>+6.1f}% {m['maxdd']*100:>+6.1f}% "
              f"{m['sharpe']:>7.2f} {m['pct_in']:>6.0f}%")
    best = max(rows, key=lambda r: r[1]['sharpe']); (N, lb, sk, fq), m = best
    print(f"\n>> MEILLEUR avec filtre : top{N}, {lb//21}mo, reb {'hebdo' if fq==5 else 'mensuel'}")
    print(f"   {INIT:,.0f}$ -> {m['final']:,.0f}$  (CAGR {m['cagr']*100:+.1f}%, maxDD {m['maxdd']*100:.1f}%, Sharpe {m['sharpe']:.2f})")
    print(f"   vs sans filtre Sharpe 1.25 (maxDD -33.7%) | SPY 0.79")


if __name__ == '__main__':
    main()
