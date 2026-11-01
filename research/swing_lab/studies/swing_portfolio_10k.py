#!/usr/bin/env python3
"""Simulation PORTEFEUILLE RÉALISTE du swing RSI(2) — comme le bot day-trading : capital de départ
10 000 $, positions DISCRÈTES, sizing = part du capital / nb max de positions concurrentes (rotation),
cash géré, compounding, COMMISSIONS. Exécution causale au close du LENDEMAIN du signal.

Entrée : RSI(2) < lo ET prix > SMA200 (repli survendu en tendance). Sortie : prix > SMA5 ou RSI(2)>70.
Quand plus de signaux que de slots -> on prend les plus survendus (RSI2 le plus bas). Compare au
buy&hold equal-weight 10 000 $. Teste plusieurs niveaux de frais (LE point qui décide, gros turnover).
⚠️ vol_etf = ~6 ans (indicatif). close-to-close."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import signals as S
from research.swing_lab.universes import UNIVERSES
from research.swing_lab.studies.momentum_rotation import price_matrix, perf

INIT = 10_000.0
P = dict(rsi_n=2, lo=10, trend=200, exit_sma=5, hi=70)


def signals_matrices(px):
    ent, exi, rsiv = {}, {}, {}
    for tk in px.columns:
        c = px[tk].ffill().to_numpy(float)
        r = S._rsi(c, 2); sma200 = S._sma(c, 200); sma5 = S._sma(c, 5)
        ent[tk] = (r < P['lo']) & (c > sma200)
        exi[tk] = (c > sma5) | (r > P['hi'])
        rsiv[tk] = r
    return (pd.DataFrame(ent, index=px.index), pd.DataFrame(exi, index=px.index),
            pd.DataFrame(rsiv, index=px.index))


def simulate(px, max_pos, cost):
    ent, exi, rsiv = signals_matrices(px)
    idx = px.index; cols = list(px.columns)
    cash = INIT; pos = {}; curve = [INIT]; trades = []
    for t in range(1, len(idx)):
        pxt = px.iloc[t]
        # SORTIES (signal de la veille, exécuté au close d'aujourd'hui)
        for tk in list(pos):
            if bool(exi[tk].iloc[t - 1]) and not np.isnan(pxt[tk]):
                px_out = pxt[tk]; sh, px_in = pos[tk]
                cash += sh * px_out * (1 - cost)
                trades.append(px_out / px_in - 1); del pos[tk]
        # ENTRÉES (signaux de la veille), les plus survendus d'abord, dans la limite des slots/cash
        cands = [tk for tk in cols if bool(ent[tk].iloc[t - 1]) and tk not in pos and not np.isnan(pxt[tk])]
        cands.sort(key=lambda tk: rsiv[tk].iloc[t - 1])
        for tk in cands:
            if len(pos) >= max_pos:
                break
            equity = cash + sum(sh * pxt[tk2] for tk2, (sh, _) in pos.items() if not np.isnan(pxt[tk2]))
            size = equity / max_pos
            if cash >= size and size > 0:
                sh = size / pxt[tk]; cash -= size + size * cost; pos[tk] = (sh, pxt[tk])
        equity = cash + sum(sh * pxt[tk] for tk, (sh, _) in pos.items() if not np.isnan(pxt[tk]))
        curve.append(equity)
    curve = np.array(curve); tr = np.array(trades)
    c, d, s = perf(curve / INIT, idx)                 # normaliser à 1 (perf attend une courbe de croissance)
    return dict(final=curve[-1], cagr=c, maxDD=d, sharpe=s, n=len(tr),
                win=(tr > 0).mean() * 100 if len(tr) else 0, avgtr=tr.mean() * 100 if len(tr) else 0)


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else 'vol_etf'
    px = price_matrix(UNIVERSES[uni]); px = px.loc[px.notna().sum(axis=1) >= 10]
    idx = px.index
    print(f"Univers '{uni}' : {px.shape[1]} ETF, {len(idx)} séances {idx[0].date()}..{idx[-1].date()}")
    print(f"Capital départ {INIT:,.0f} $. Sizing = équité / max_pos (rotation). Exéc. close j+1.\n")

    # buy & hold equal-weight 10k
    ret = px.pct_change().fillna(0); bh = INIT * (1 + ret.mean(axis=1)).cumprod()
    bc, bd, bs = perf(bh.values / INIT, idx)
    print(f"  {'BUY & HOLD equal-weight':<40} final {bh.iloc[-1]:>10,.0f}$  CAGR {bc:>5.1f}%  maxDD {bd:>6.1f}%  Sharpe {bs:>4.2f}")
    print("\n  SWING RSI2 (max_pos / frais par côté) :")
    for mp in (5, 8):
        for cost in (0.0, 0.0005, 0.001, 0.002):
            r = simulate(px, mp, cost)
            print(f"  max{mp} frais {cost*100:>4.2f}% : final {r['final']:>10,.0f}$  CAGR {r['cagr']:>5.1f}%  "
                  f"maxDD {r['maxDD']:>6.1f}%  Sharpe {r['sharpe']:>4.2f}  | {r['n']:>4} trades  win {r['win']:>3.0f}%  /tr {r['avgtr']:>+5.2f}%")
    print("\nLECTURE : si le CAGR tient AVEC frais réalistes (0,05-0,10% par côté pour des ETF) et")
    print("  bat le buy&hold à drawdown moindre, c'est un vrai gagnant exécutable. Sinon les frais mangent l'edge.")


if __name__ == '__main__':
    main()
