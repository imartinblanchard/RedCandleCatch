#!/usr/bin/env python3
"""MOMENTUM × INDICATEURS : le momentum SÉLECTIONNE les titres forts, les indicateurs FILTRENT/timent
(comme un vrai swing trader). Base = rotation lb63/top-10. Overlays :
  - trend par titre : ne garder un top-momentum que si clôture > SMA(n) (évite les 'forts' qui cassent),
  - régime marché   : tout en cash quand QQQ < sa SMA200 (remède aux krachs de momentum).
Comparé à la base + aux benchmarks (equal-weight, QQQ). Full + OOS. Causal (décision close, exéc. j+1).
⚠️ biais du survivant (membres actuels) -> magnitude gonflée ; lire le SENS + le profil risque."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
from research.swing_lab.universes import UNIVERSES
from research.swing_lab.studies.momentum_rotation import price_matrix, perf


def rotation(px, ret, lb, K, trend_n=None, regime_sma=None, qqq=None):
    mom = px / px.shift(lb) - 1
    sma = px.rolling(trend_n).mean() if trend_n else None
    rb_dates = px.groupby(px.index.to_period('M')).tail(1).index
    W = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    for rb in rb_dates:
        m = mom.loc[rb].dropna(); m = m[m > 0]
        if trend_n is not None:
            above = (px.loc[rb] > sma.loc[rb]).reindex(m.index).fillna(False)
            m = m[above]
        w = pd.Series(0.0, index=px.columns)
        if len(m):
            top = m.nlargest(K).index; w[top] = 1.0 / len(top)
        W.loc[rb] = w
    W = W.ffill().fillna(0.0)
    if regime_sma and qqq is not None:                               # filtre de régime -> cash si risk-off
        on = (qqq > qqq.rolling(regime_sma).mean()).reindex(W.index).ffill().fillna(False).astype(float)
        W = W.mul(on, axis=0)
    pr = (W.shift(1) * ret).sum(axis=1)
    return (1 + pr.fillna(0)).cumprod()


def main():
    px = price_matrix(UNIVERSES['nasdaq100']); ret = px.pct_change()
    valid = px.notna().sum(axis=1); px = px.loc[valid[valid >= 30].index[0]:]; ret = ret.loc[px.index]
    idx = px.index; split = idx[int(len(idx) * 0.6)]
    qqq = E.load_daily('qqq'); qqq = pd.Series(qqq['c'].values, index=pd.to_datetime(qqq['date'])).reindex(idx).ffill()
    print(f"Nasdaq-100 : {px.shape[1]} titres, {len(idx)} séances {idx[0].date()}..{idx[-1].date()} | OOS >= {split.date()}\n", flush=True)

    def row(lbl, eq):
        c, d, s = perf(eq.values, idx)
        eo = eq.loc[split:] / eq.loc[split:].iloc[0]; co, do, so = perf(eo.values, eo.index)
        print(f"  {lbl:<40} CAGR {c:>6.1f}%  maxDD {d:>6.1f}%  Sharpe {s:>4.2f}  |  OOS CAGR {co:>6.1f}%  maxDD {do:>6.1f}%  Sharpe {so:>4.2f}")

    eqw = (1 + ret.mean(axis=1).fillna(0)).cumprod()
    print("BENCHMARKS :"); row('Equal-weight univers (hold)', eqw); row('QQQ (hold)', qqq / qqq.iloc[0])
    print("\nMOMENTUM lb63/top-10 — base vs + overlays :")
    row('base (momentum seul)', rotation(px, ret, 63, 10))
    row('+ trend/titre SMA100', rotation(px, ret, 63, 10, trend_n=100))
    row('+ trend/titre SMA200', rotation(px, ret, 63, 10, trend_n=200))
    row('+ régime QQQ>SMA200', rotation(px, ret, 63, 10, regime_sma=200, qqq=qqq))
    row('+ trend SMA200 + régime QQQ200', rotation(px, ret, 63, 10, trend_n=200, regime_sma=200, qqq=qqq))
    row('+ trend SMA100 + régime QQQ200', rotation(px, ret, 63, 10, trend_n=100, regime_sma=200, qqq=qqq))
    print("\n-> on cherche : garder ~le rendement de la base en RÉDUISANT le maxDD (krachs momentum) => Sharpe ↑.")
    print("⚠️ magnitude gonflée par le biais du survivant ; le SENS (momentum+filtre) est l'enseignement.")


if __name__ == '__main__':
    main()
