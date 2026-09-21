#!/usr/bin/env python3
"""
RedCandleCatch — même test PORTEFEUILLE mais en filtrant l'univers par VOLATILITÉ.
Hypothèse : le mean-reversion (acheter le dip) a plus d'edge sur les titres volatils.

Pour chaque tranche de volatilité (tout / top 50% / top 25% / top 10% les plus volatils) :
  - backtest portefeuille (2 sizings)
  - benchmark : buy-and-hold équipondéré des MÊMES titres (isole l'apport du timing)
Référence marché : SPY buy&hold = CAGR +12,8%, maxDD -24,5%, Sharpe 0,79.

⚠️ Le tri par volatilité utilise la vol sur toute la période (léger look-ahead) — test
exploratoire pour voir S'IL Y A un signal, pas une stratégie déployable telle quelle.

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/portfolio_volfilter.py
"""
import os, math
import numpy as np, pandas as pd
import engine, strategies as st
import portfolio as P

HERE = os.path.dirname(os.path.abspath(__file__))
SPY = "SPY b&h : CAGR +12.8%  maxDD -24.5%  Sharpe 0.79"


def ew_buyhold(df):
    """Buy-and-hold équipondéré : index = moyenne des prix normalisés (1$ par titre)."""
    piv = df.pivot_table(index='date', columns='ticker', values='c').sort_index()
    norm = piv / piv.apply(lambda s: s.loc[s.first_valid_index()])
    idx = norm.mean(axis=1)
    idx.index = pd.to_datetime(idx.index)
    ret = idx.pct_change().dropna(); years = len(idx) / 252
    return dict(cagr=(idx.iloc[-1] / idx.iloc[0]) ** (1 / years) - 1,
                maxdd=(idx / idx.cummax() - 1).min(),
                sharpe=ret.mean() / ret.std() * math.sqrt(252) if ret.std() > 0 else 0)


def main():
    print("Chargement...")
    df = engine.load_table(os.path.join(HERE, 'data', 'daily.parquet'))
    vol = df.groupby('ticker')['c'].apply(lambda s: s.pct_change().std() * math.sqrt(252))
    print(f"{df.ticker.nunique()} titres | vol annualisée : médiane {vol.median()*100:.0f}%, "
          f"min {vol.min()*100:.0f}%, max {vol.max()*100:.0f}%")
    print(f"Réf : {SPY}\n")

    for cut, lab in [(0.0, 'TOUT (503)'), (0.50, 'TOP 50% volatils'),
                     (0.75, 'TOP 25% volatils'), (0.90, 'TOP 10% volatils')]:
        keep = vol[vol >= vol.quantile(cut)].index
        sub = df[df.ticker.isin(keep)].copy()
        bars, sig_by_date, dates, didx = P.build(sub)
        bh = ew_buyhold(sub)
        print(f"########## {lab} — {len(keep)} titres "
              f"(vol médiane {vol[keep].median()*100:.0f}%) ##########")
        print(f"  buy&hold équipondéré : CAGR {bh['cagr']*100:+.1f}%  maxDD {bh['maxdd']*100:.1f}%  Sharpe {bh['sharpe']:.2f}")
        for frac, mp in [(0.20, 20), (0.10, 50)]:
            eq, nt, expo = P.simulate(bars, sig_by_date, dates, didx, frac, mp)
            s = P.stats(eq, nt, expo)
            print(f"  RCC {frac*100:.0f}%/pos max{mp:<3} : CAGR {s['cagr']*100:+5.1f}%  "
                  f"maxDD {s['maxdd']*100:5.1f}%  Sharpe {s['sharpe']:.2f}  "
                  f"final {s['final']:,.0f}$  ({nt} trades)")
        print()


if __name__ == '__main__':
    main()
