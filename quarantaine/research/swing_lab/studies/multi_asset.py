#!/usr/bin/env python3
"""TREND-FOLLOWING / MOMENTUM MULTI-ACTIFS (le vrai edge documenté) sur ~20 ans (yfinance).
Univers diversifié : actions US/intl/émergentes/small, obligations, or, matières premières, REITs.
L'edge du trend/momentum = 'crisis alpha' : il faut d'AUTRES actifs où se réfugier pendant les krachs.

Stratégies : (A) GTAA Faber (chaque actif détenu si > SMA 10 mois, sinon cash, equal-weight) ;
(B) Dual Momentum (top-K par momentum 12 mois, mais seulement si momentum absolu > 0, sinon cash).
Benchmarks : SPY buy&hold, 60/40 (SPY/IEF). Inclut 2008, 2020, 2022. Causal (signal fin de mois, exéc. j+1).
⚠️ ETF = sans biais du survivant. Mais ~10 actifs = sélection possible ; lire DD + Sharpe, pas que le CAGR."""
import os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
TY = 252
ASSETS = ['SPY', 'QQQ', 'EFA', 'EEM', 'IWM', 'TLT', 'IEF', 'GLD', 'DBC', 'VNQ']


def load_yf(sym):
    f = os.path.join(E.DATA, f'{sym.lower()}_yf.parquet')
    if os.path.exists(f):
        s = pd.read_parquet(f); return pd.Series(s['c'].values, index=pd.to_datetime(s['date']))
    import yfinance as yf
    d = yf.download(sym, start='2000-01-01', progress=False, auto_adjust=True)
    cl = d['Close']; cl = cl.iloc[:, 0] if isinstance(cl, pd.DataFrame) else cl
    cl.index = pd.to_datetime(cl.index)
    pd.DataFrame({'date': cl.index.strftime('%Y-%m-%d'), 'c': cl.values}).to_parquet(f, index=False)
    time.sleep(0.3); return cl


def perf(eq, idx):
    eq = np.asarray(eq, float); yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = (eq[-1] ** (1 / yrs) - 1) * 100 if eq[-1] > 0 else -100
    peak = np.maximum.accumulate(eq); mdd = ((eq - peak) / peak).min() * 100
    r = np.diff(eq) / eq[:-1]; sh = r.mean() / r.std() * np.sqrt(TY) if r.std() > 0 else 0
    return cagr, mdd, sh


def bt(W, ret):                 # W = poids cibles (fin de mois) ; exécuté le lendemain
    return (1 + (W.ffill().fillna(0).shift(1) * ret).sum(axis=1).fillna(0)).cumprod()


def main():
    px = pd.DataFrame({a: load_yf(a) for a in ASSETS}).sort_index().ffill()
    px = px.loc[px.notna().all(axis=1)]          # commence quand TOUS les actifs ont de la data
    ret = px.pct_change().fillna(0.0); idx = px.index
    rb = px.groupby(px.index.to_period('M')).tail(1).index
    print(f"Multi-actifs : {len(ASSETS)} ETF, {len(idx)} séances {idx[0].date()}..{idx[-1].date()} "
          f"(~{(idx[-1]-idx[0]).days/365.25:.0f} ans, inclut 2008/2020/2022)\n", flush=True)

    sma10 = px.rolling(200).mean()               # ~10 mois
    mom12 = px / px.shift(252) - 1
    W_gtaa = pd.DataFrame(np.nan, index=idx, columns=px.columns)
    W_dm = pd.DataFrame(np.nan, index=idx, columns=px.columns)
    for d in rb:
        above = px.loc[d] > sma10.loc[d]                         # GTAA : au-dessus SMA10mois
        w = pd.Series(0.0, index=px.columns)
        if above.sum() > 0: w[above] = 1.0 / len(px.columns)     # equal-weight, cash pour le reste
        W_gtaa.loc[d] = w
        m = mom12.loc[d].dropna(); m = m[m > 0]                  # dual mom : momentum absolu > 0
        w2 = pd.Series(0.0, index=px.columns)
        if len(m): w2[m.nlargest(3).index] = 1.0 / min(3, len(m))
        W_dm.loc[d] = w2

    def row(lbl, eq):
        c, d, s = perf(eq.values, idx); print(f"  {lbl:<28} CAGR {c:>5.1f}%  maxDD {d:>6.1f}%  Sharpe {s:>4.2f}")

    print("BENCHMARKS :")
    row('SPY buy & hold', (1 + ret['SPY']).cumprod())
    w6040 = pd.DataFrame(np.nan, index=idx, columns=px.columns)
    for d in rb:
        w = pd.Series(0.0, index=px.columns); w['SPY'] = 0.6; w['IEF'] = 0.4; w6040.loc[d] = w
    row('60/40 (SPY/IEF)', bt(w6040, ret))
    print("\nSTRATÉGIES TREND/MOMENTUM MULTI-ACTIFS :")
    row('GTAA Faber (SMA 10 mois)', bt(W_gtaa, ret))
    row('Dual Momentum (top-3, abs>0)', bt(W_dm, ret))
    print("\n-> on cherche : rendement proche des actions MAIS drawdown bien plus bas (crisis alpha).")
    print("   C'est là que l'actif gagne vraiment vs le buy&hold actions — pas sur un seul type d'actif.")


if __name__ == '__main__':
    main()
