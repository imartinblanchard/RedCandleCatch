#!/usr/bin/env python3
"""PORTEFEUILLE de swing RSI(2) mean-reversion sur TOUT un univers simultanément — le test décisif.
Chaque instrument n'est en position que ~10% du temps (repli survendu en tendance) ; en combinant
beaucoup d'instruments, le capital reste déployé ET diversifié. Deux sizings :
  - 'concentré'  : equal-weight parmi les actifs en position (plein capital dès qu'au moins 1 signal),
  - 'fixe 1/N'   : chaque position = 1/N du capital (exposition = fraction active, plus prudent).
Comparé au buy&hold equal-weight de l'univers. Causal (signal close j, exéc. j+1). ⚠️ pas de frais."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E, signals as S
from research.swing_lab.universes import UNIVERSES
from research.swing_lab.studies.momentum_rotation import price_matrix, perf

P = dict(rsi_n=2, lo=10, trend=200, exit_sma=5, hi=70)


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else 'vol_etf'
    px = price_matrix(UNIVERSES[uni]); ret = px.pct_change().fillna(0)
    px = px.loc[px.notna().sum(axis=1) >= 10]; ret = ret.loc[px.index]; idx = px.index
    N = px.shape[1]
    # matrice des positions RSI2 (0/1) par instrument
    POS = pd.DataFrame({tk: S.rsi2_meanrev(pd.DataFrame({'c': px[tk].ffill()}), P) for tk in px.columns},
                       index=idx).fillna(0)
    active = POS.sum(axis=1)
    print(f"Univers '{uni}' : {N} instruments, {len(idx)} séances {idx[0].date()}..{idx[-1].date()}")
    print(f"Signaux actifs/jour : moy {active.mean():.1f}, max {int(active.max())} ; "
          f"jours avec >=1 signal : {(active > 0).mean()*100:.0f}%\n")

    # sizings
    W_conc = POS.div(active.replace(0, np.nan), axis=0).fillna(0)      # equal-weight parmi actifs
    W_fix = POS / N                                                    # chacun = 1/N
    eqw_bh = (1 + ret.mean(axis=1)).cumprod()                         # buy&hold equal-weight univers

    def pf(W):
        return (1 + (W.shift(1) * ret).sum(axis=1).fillna(0)).cumprod()

    def row(lbl, eq, expo):
        c, d, s = perf(eq.values, idx)
        print(f"  {lbl:<34} CAGR {c:>5.1f}%  maxDD {d:>6.1f}%  Sharpe {s:>4.2f}  expo {expo:>3.0f}%")

    row('Buy & hold equal-weight', eqw_bh, 100)
    row('Swing RSI2 — concentré', pf(W_conc), (active > 0).mean() * 100)
    row('Swing RSI2 — fixe 1/N', pf(W_fix), (active / N).mean() * 100)
    # version leviérisée du 'concentré' pour viser ~100% d'expo moyenne
    lev = 1.0 / max((active > 0).mean(), 0.01)
    row(f'Swing RSI2 — concentré x{min(lev,3):.1f} (levier)', pf(W_conc * min(lev, 3)), 100)
    print("\nLECTURE : si le swing concentré (surtout leviérisé) bat le buy&hold en CAGR À DRAWDOWN ÉGAL")
    print("  ou mieux en Sharpe, alors le portefeuille de swings mean-reversion est un vrai gagnant.")
    print("⚠️ pas de frais ; vol_etf = ~6 ans (indicatif). Le levier amplifie aussi les pertes.")


if __name__ == '__main__':
    main()
