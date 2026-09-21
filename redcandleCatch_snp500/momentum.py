#!/usr/bin/env python3
"""
Momentum CROSS-SECTIONAL sur le S&P 500 (daily, 5 ans).

À chaque rebalance : classer les titres par rendement passé (lookback, avec skip
optionnel du dernier mois = anti-reversal classique), tenir le TOP N équipondéré
jusqu'au prochain rebalance. Coûts de transaction appliqués sur le turnover.

On balaye N × lookback × skip × fréquence de rebalance, et on compare aux barres :
  SPY buy&hold        : CAGR +12.8%  maxDD -24.5%  Sharpe 0.79
  EW buy&hold (503)   : CAGR +15.4%  maxDD -19.2%  Sharpe 0.92   <- LA vraie barre

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/momentum.py
"""
import os, math, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = 50_000.0
COST = 0.001                 # 10 bps par unité de turnover (par côté)

NS = [10, 20, 50]
LOOKBACKS = [63, 126, 252]   # 3, 6, 12 mois
SKIPS = [0, 21]              # 0 ou skip 1 mois
FREQS = [5, 21]             # rebalance hebdo / mensuel


def backtest(prices, rets, N, lookback, skip, freq):
    dates = prices.index
    reb_idx = list(range(lookback + skip, len(dates), freq))
    if not reb_idx:
        return None
    port_ret = pd.Series(0.0, index=dates)
    prev = set()
    basket = []
    turnover_total = 0.0
    for di in range(reb_idx[0], len(dates)):
        # 1) rendement du JOUR sur le panier de la VEILLE (pas de look-ahead)
        if basket:
            port_ret.iloc[di] += rets.iloc[di][basket].mean()
        # 2) rebalance au close di -> panier effectif à partir de DEMAIN
        if di in reb_idx:
            mom = prices.iloc[di - skip] / prices.iloc[di - lookback] - 1
            mom = mom.dropna()
            new_basket = list(mom.sort_values(ascending=False).head(N).index)
            new = set(new_basket)
            turn = len(new.symmetric_difference(prev)) / (2 * N) if prev else 1.0
            turnover_total += turn
            port_ret.iloc[di] -= turn * COST * 2      # coût appliqué le jour du rebalance
            prev = new
            basket = new_basket
    pr = port_ret.iloc[reb_idx[0]:]
    eq = INIT * (1 + pr).cumprod()
    years = len(pr) / 252
    cagr = (eq.iloc[-1] / INIT) ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sharpe = pr.mean() / pr.std() * math.sqrt(252) if pr.std() > 0 else 0
    return dict(final=eq.iloc[-1], cagr=cagr, maxdd=dd, sharpe=sharpe,
                nreb=len(reb_idx), turn=turnover_total / len(reb_idx))


def main():
    print("Chargement...")
    df = pd.read_parquet(os.path.join(HERE, 'data', 'daily.parquet'))
    prices = df.pivot_table(index='date', columns='ticker', values='c').sort_index()
    prices.index = pd.to_datetime(prices.index)
    rets = prices.pct_change()
    print(f"{prices.shape[1]} titres, {prices.index.min().date()} -> {prices.index.max().date()}")
    print("Barres : SPY Sharpe 0.79 (CAGR 12.8%) | EW buy&hold Sharpe 0.92 (CAGR 15.4%)\n")

    rows = []
    for N, lb, sk, fq in itertools.product(NS, LOOKBACKS, SKIPS, FREQS):
        m = backtest(prices, rets, N, lb, sk, fq)
        if m:
            rows.append(((N, lb, sk, fq), m))

    print(f"  {'config':30} {'final$':>11} {'CAGR':>7} {'maxDD':>7} {'Sharpe':>7} {'turn/reb':>8}")
    for (N, lb, sk, fq), m in sorted(rows, key=lambda x: -x[1]['sharpe'])[:12]:
        lab = f'top{N} {lb//21}mo skip{sk//21} reb{"W" if fq==5 else "M"}'
        star = '  <<' if m['sharpe'] > 0.92 else (' <' if m['sharpe'] > 0.79 else '')
        print(f"  {lab:30} {m['final']:>11,.0f} {m['cagr']*100:>+6.1f}% "
              f"{m['maxdd']*100:>+6.1f}% {m['sharpe']:>7.2f} {m['turn']*100:>7.0f}%{star}")

    best = max(rows, key=lambda r: r[1]['sharpe'])
    (N, lb, sk, fq), m = best
    print(f"\n>> MEILLEUR (Sharpe) : top{N}, {lb//21}mo, skip{sk//21}mo, reb {'hebdo' if fq==5 else 'mensuel'}")
    print(f"   {INIT:,.0f}$ -> {m['final']:,.0f}$  (CAGR {m['cagr']*100:+.1f}%, "
          f"maxDD {m['maxdd']*100:.1f}%, Sharpe {m['sharpe']:.2f})")
    print(f"   vs SPY 0.79 / EW buy&hold 0.92")


if __name__ == '__main__':
    main()
