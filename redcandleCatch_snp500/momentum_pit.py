#!/usr/bin/env python3
"""
Momentum cross-sectional POINT-IN-TIME (sans biais du survivant).

Comme momentum.py mais :
- univers = daily_pit.parquet (609 titres, inclut les sortis du S&P 500 avec leur
  historique jusqu'à leur sortie)
- à chaque rebalance, on ne classe QUE les titres réellement DANS l'indice ce jour-là
  (membership sp500_pit.json, forward-fill)
- un titre racheté/délisté en cours de détention sort naturellement (ses rendements
  deviennent NaN et sont exclus du panier)

Barre honnête : SPY buy&hold = Sharpe 0.79 (CAGR +12.8%).

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/momentum_pit.py
"""
import os, math, json, bisect, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = 50_000.0
COST = 0.001
NS = [10, 20, 50]
LOOKBACKS = [63, 126, 252]
SKIPS = [0, 21]
FREQS = [5, 21]


def load():
    df = pd.read_parquet(os.path.join(HERE, 'data', 'daily_pit.parquet'))
    prices = df.pivot_table(index='date', columns='ticker', values='c').sort_index()
    prices.index = pd.to_datetime(prices.index)
    rets = prices.pct_change()
    pit = json.load(open(os.path.join(HERE, 'data', 'sp500_pit.json')))
    snap_dates = [pd.Timestamp(s['date']) for s in pit]
    snap_sets = [set(s['tickers']) for s in pit]
    return prices, rets, snap_dates, snap_sets


def members_on(d, snap_dates, snap_sets):
    i = bisect.bisect_right(snap_dates, d) - 1
    return snap_sets[max(i, 0)]


def backtest(prices, rets, snap_dates, snap_sets, N, lookback, skip, freq):
    dates = prices.index
    reb_idx = set(range(lookback + skip, len(dates), freq))
    start = lookback + skip
    port_ret = pd.Series(0.0, index=dates)
    basket, prev = [], set()
    turnover_total, nreb = 0.0, 0
    for di in range(start, len(dates)):
        if basket:
            r = rets.iloc[di][basket].mean()          # skipna : les délistés sortent
            if r == r:
                port_ret.iloc[di] += r
        if di in reb_idx:
            d = dates[di]
            elig = members_on(d, snap_dates, snap_sets)
            mom = prices.iloc[di - skip] / prices.iloc[di - lookback] - 1
            mom = mom[[t for t in mom.index if t in elig]].dropna()
            new_basket = list(mom.sort_values(ascending=False).head(N).index)
            new = set(new_basket)
            turn = len(new.symmetric_difference(prev)) / (2 * N) if prev else 1.0
            turnover_total += turn; nreb += 1
            port_ret.iloc[di] -= turn * COST * 2
            prev = new; basket = new_basket
    pr = port_ret.iloc[start:]
    eq = INIT * (1 + pr).cumprod()
    years = len(pr) / 252
    cagr = (eq.iloc[-1] / INIT) ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = pr.mean() / pr.std() * math.sqrt(252) if pr.std() > 0 else 0
    return dict(final=eq.iloc[-1], cagr=cagr, maxdd=dd, sharpe=sharpe, turn=turnover_total / max(nreb, 1))


def main():
    print("Chargement point-in-time...")
    prices, rets, sd, ss = load()
    print(f"{prices.shape[1]} titres (univers PIT), {prices.index.min().date()} -> {prices.index.max().date()}")
    print(f"Barre honnête : SPY buy&hold Sharpe 0.79 (CAGR +12.8%)")
    print("(rappel : version BIAISÉE survivant donnait Sharpe 1.77 / CAGR +99%)\n")

    rows = []
    for N, lb, sk, fq in itertools.product(NS, LOOKBACKS, SKIPS, FREQS):
        m = backtest(prices, rets, sd, ss, N, lb, sk, fq)
        rows.append(((N, lb, sk, fq), m))

    print(f"  {'config':30} {'final$':>11} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'turn':>6}")
    for (N, lb, sk, fq), m in sorted(rows, key=lambda x: -x[1]['sharpe'])[:12]:
        lab = f'top{N} {lb//21}mo skip{sk//21} reb{"W" if fq==5 else "M"}'
        star = '  << bat SPY' if m['sharpe'] > 0.79 else ''
        print(f"  {lab:30} {m['final']:>11,.0f} {m['cagr']*100:>+6.1f}% "
              f"{m['maxdd']*100:>+6.1f}% {m['sharpe']:>7.2f} {m['turn']*100:>5.0f}%{star}")

    best = max(rows, key=lambda r: r[1]['sharpe'])
    (N, lb, sk, fq), m = best
    print(f"\n>> MEILLEUR (Sharpe) POINT-IN-TIME : top{N}, {lb//21}mo, skip{sk//21}mo, reb {'hebdo' if fq==5 else 'mensuel'}")
    print(f"   {INIT:,.0f}$ -> {m['final']:,.0f}$  (CAGR {m['cagr']*100:+.1f}%, maxDD {m['maxdd']*100:.1f}%, Sharpe {m['sharpe']:.2f})")
    print(f"   vs SPY 0.79")


if __name__ == '__main__':
    main()
