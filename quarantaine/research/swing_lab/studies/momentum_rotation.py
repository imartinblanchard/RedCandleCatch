#!/usr/bin/env python3
"""ROTATION MOMENTUM (force relative) sur le Nasdaq-100 — LA stratégie des swing/position traders.
Chaque fin de mois : classer les titres par rendement des N derniers jours, détenir les K plus forts
(equal-weight), tourner le mois suivant. Causal (décision au close de fin de mois, exécutée le
lendemain). Comparée à : détenir tout l'univers (equal-weight) et détenir QQQ.

Balaye lookback × K × (filtre momentum>0). Split OOS. ⚠️ biais du survivant (membres actuels) →
le momentum en profite un peu (les survivants sont les gagnants) ; lire en RELATIF + rester prudent."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
from research.swing_lab.universes import UNIVERSES
TY = 252


def price_matrix(tickers):
    cols = {}
    for tk in tickers:
        f = os.path.join(E.DATA, f'{tk.lower()}_daily.parquet')
        if os.path.exists(f):
            d = pd.read_parquet(f)
            cols[tk] = pd.Series(d['c'].values, index=pd.to_datetime(d['date']))
    px = pd.DataFrame(cols).sort_index().ffill()
    return px


def perf(eq, idx):
    eq = np.asarray(eq, float); n = len(eq)
    yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = (eq[-1] ** (1 / yrs) - 1) * 100 if eq[-1] > 0 and yrs > 0 else -100
    peak = np.maximum.accumulate(eq); mdd = ((eq - peak) / peak).min() * 100
    r = np.diff(eq) / eq[:-1]
    sharpe = r.mean() / r.std() * np.sqrt(TY) if r.std() > 0 else 0
    return cagr, mdd, sharpe


def rotation(px, ret, lookback, K, mom_pos):
    mom = px / px.shift(lookback) - 1
    rb_dates = px.groupby(px.index.to_period('M')).tail(1).index      # dernier jour de chaque mois
    W = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    for rb in rb_dates:
        m = mom.loc[rb].dropna()
        if mom_pos:
            m = m[m > 0]
        w = pd.Series(0.0, index=px.columns)                         # vecteur de poids COMPLET (zéros inclus)
        if len(m):
            top = m.nlargest(K).index
            w[top] = 1.0 / len(top)                                   # equal-weight, somme = 1 (pas de levier)
        W.loc[rb] = w
    W = W.ffill().fillna(0.0)                                         # tenir le MÊME vecteur jusqu'au prochain rebal
    pr = (W.shift(1) * ret).sum(axis=1)                              # exécuté le LENDEMAIN (causal)
    return (1 + pr.fillna(0)).cumprod()


def main():
    px = price_matrix(UNIVERSES['nasdaq100'])
    ret = px.pct_change()
    # on démarre quand >=30 titres ont de la data (évite le tout début clairsemé)
    valid = px.notna().sum(axis=1)
    start = valid[valid >= 30].index[0]
    px, ret = px.loc[start:], ret.loc[start:]
    idx = px.index
    isp = len(idx) // 2 * 0 + int(len(idx) * 0.6)                     # split OOS 60/40
    split = idx[isp]
    print(f"Nasdaq-100 : {px.shape[1]} titres, {len(idx)} séances {idx[0].date()}..{idx[-1].date()} "
          f"| OOS >= {split.date()}\n", flush=True)

    # Benchmarks
    eqw = (1 + ret.mean(axis=1).fillna(0)).cumprod()                 # equal-weight de l'univers
    qqq = E.load_daily('qqq'); qqq = pd.Series(qqq['c'].values, index=pd.to_datetime(qqq['date'])).reindex(idx).ffill()
    qqq_eq = qqq / qqq.iloc[0]

    def line(lbl, eq):
        c, d, s = perf(eq.values, idx)
        # OOS : rebaser sur le split
        eo = eq.loc[split:] / eq.loc[split:].iloc[0]
        co, do, so = perf(eo.values, eo.index)
        print(f"  {lbl:<34} CAGR {c:>6.1f}%  maxDD {d:>6.1f}%  Sharpe {s:>4.2f}  |  OOS CAGR {co:>6.1f}%  Sharpe {so:>4.2f}")

    print("BENCHMARKS :")
    line('Equal-weight univers (hold)', eqw)
    line('QQQ (hold)', qqq_eq)

    print("\nROTATION MOMENTUM (lookback / K titres / filtre mom>0) :")
    rows = []
    for lb in (63, 126, 252):
        for K in (5, 10, 20):
            for mp in (False, True):
                eq = rotation(px, ret, lb, K, mp)
                c, d, s = perf(eq.values, idx)
                eo = eq.loc[split:] / eq.loc[split:].iloc[0]; co, do, so = perf(eo.values, eo.index)
                lbl = f"lb{lb}/K{K}{'/mom>0' if mp else ''}"
                rows.append(dict(strat=lbl, cagr=round(c, 1), maxDD=round(d, 1), sharpe=round(s, 2),
                                 cagr_oos=round(co, 1), sharpe_oos=round(so, 2)))
    r = pd.DataFrame(rows).sort_values('cagr_oos', ascending=False)
    r.to_csv(os.path.join(os.path.dirname(HERE), 'results', 'momentum_rotation.csv'), index=False)
    for _, x in r.iterrows():
        print(f"  {x.strat:<34} CAGR {x.cagr:>6.1f}%  maxDD {x.maxDD:>6.1f}%  Sharpe {x.sharpe:>4.2f}  "
              f"|  OOS CAGR {x.cagr_oos:>6.1f}%  Sharpe {x.sharpe_oos:>4.2f}")
    bc, bd, bs = perf(eqw.values, idx); qc, qd, qs = perf(qqq_eq.values, idx)
    print(f"\nRéférence : equal-weight CAGR {bc:.0f}% / QQQ CAGR {qc:.0f}%. "
          f"Une rotation qui bat CES DEUX, full ET OOS, = momentum réel (−un peu de biais survivant).")
    print("CSV: research/swing_lab/results/momentum_rotation.csv")


if __name__ == '__main__':
    main()
