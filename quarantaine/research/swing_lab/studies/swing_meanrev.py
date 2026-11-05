#!/usr/bin/env python3
"""SWING mean-reversion court-terme RSI(2) style Connors — LE classique swing à edge documenté.
Teste sur SPY (yfinance long ~21 ans) + l'univers ETF volatils, vs buy&hold. Montre les stats
PAR TRADE (c'est un swing : peu de temps en marché, plein de petits trades rapides) + le profil
rendement/risque + l'exposition. Balaye le seuil RSI(2) et le filtre de tendance.

Clé swing : en marché seulement ~15-35% du temps -> même si le CAGR < buy&hold, l'edge PAR TRADE +
la faible exposition = capital-efficace (déployable sur PLUSIEURS instruments / leviérisable).
⚠️ close-to-close, pas de frais. ETF volatils = Alpaca ~6 ans (indicatif) ; SPY = 21 ans (robuste)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E, signals as S
from research.swing_lab.universes import UNIVERSES


def load_spy_long():
    f = os.path.join(E.DATA, 'spy_yf.parquet')
    if os.path.exists(f):
        s = pd.read_parquet(f); return pd.DataFrame({'c': s['c'].values}, index=pd.to_datetime(s['date']))
    import yfinance as yf
    d = yf.download('SPY', start='2000-01-01', progress=False, auto_adjust=True)
    cl = d['Close']; cl = cl.iloc[:, 0] if isinstance(cl, pd.DataFrame) else cl
    pd.DataFrame({'date': pd.to_datetime(cl.index).strftime('%Y-%m-%d'), 'c': cl.values}).to_parquet(f, index=False)
    return pd.DataFrame({'c': cl.values}, index=pd.to_datetime(cl.index))


def line(lbl, df, P):
    pos = S.rsi2_meanrev(df, P)
    m = E._metrics(np.asarray(pos, float), df['c'].to_numpy(float))
    bh_cagr, bh_dd = m['bh_cagr'], m['bh_maxDD']
    print(f"  {lbl:<22} n={m['ntr']:>4} exp={m['expo']:>4.0f}%  /tr={m['avgtr']:>+5.2f}% win={m['win']:>3.0f}%  "
          f"CAGR {m['cagr']:>5.1f}%  maxDD {m['maxDD']:>6.1f}%  Sharpe {m['sharpe']:>4.2f}  "
          f"| B&H {bh_cagr:>5.1f}%/{bh_dd:>5.0f}%")


def main():
    print("=" * 100)
    print("SPY (21 ans) — RSI(2) mean-reversion, variantes :")
    spy = load_spy_long()
    for lbl, P in [('RSI2<10 +trend200', dict(rsi_n=2, lo=10, trend=200, exit_sma=5, hi=70)),
                   ('RSI2<5 +trend200',  dict(rsi_n=2, lo=5, trend=200, exit_sma=5, hi=70)),
                   ('RSI2<10 nu',        dict(rsi_n=2, lo=10, exit_sma=5, hi=70)),
                   ('RSI2<5 exit SMA10', dict(rsi_n=2, lo=5, trend=200, exit_sma=10, hi=70))]:
        line(lbl, spy, P)

    print("\n" + "=" * 100)
    print("ETF VOLATILS (RSI2<10 +trend200) — par instrument + agrégat :")
    best = dict(rsi_n=2, lo=10, trend=200, exit_sma=5, hi=70)
    exps, trs, cagrs, dds, sharpes, bhs = [], [], [], [], [], []
    for tk in UNIVERSES['vol_etf']:
        f = os.path.join(E.DATA, f'{tk.lower()}_daily.parquet')
        if not os.path.exists(f):
            continue
        df = pd.read_parquet(f); df = pd.DataFrame({'c': df['c'].values}, index=pd.to_datetime(df['date']))
        m = E._metrics(np.asarray(S.rsi2_meanrev(df, best), float), df['c'].to_numpy(float))
        exps.append(m['expo']); trs.append(m['avgtr']); cagrs.append(m['cagr'])
        dds.append(m['maxDD']); sharpes.append(m['sharpe']); bhs.append(m['bh_cagr'])
    print(f"  {len(cagrs)} ETF | moy : exp={np.mean(exps):.0f}%  /tr={np.mean(trs):+.2f}%  "
          f"CAGR {np.mean(cagrs):.1f}% (B&H {np.mean(bhs):.1f}%)  maxDD {np.mean(dds):.1f}%  Sharpe {np.mean(sharpes):.2f}")
    print(f"  Sharpe strat > Sharpe B&H sur {sum(np.array(sharpes) > 0.44)}/{len(sharpes)} ETF  "
          f"(B&H vol_etf Sharpe≈0.44) ; /tr positif sur {sum(np.array(trs) > 0)}/{len(trs)}")
    print("\nLECTURE : swing = beaucoup de trades courts, en marché une FRACTION du temps. L'edge est")
    print("  /tr (par trade) + win% + Sharpe + faible exposition (capital-efficace), PAS le CAGR brut.")


if __name__ == '__main__':
    main()
