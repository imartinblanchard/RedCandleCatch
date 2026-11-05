#!/usr/bin/env python3
"""SAISONNALITÉ sur l'indice S&P 500 (^GSPC via yfinance, 1950→, ~76 ans = vrai échantillon).
Les ETF/Nasdaq Alpaca (~6 ans) sont trop courts pour ça (6 obs/mois = bruit). Ici ~76 obs/mois.

Tests : (1) rendement moyen par MOIS calendaire (+ t-stat), (2) 'Best 6 months' Nov-Avr vs Mai-Oct
(+ stratégie investie seulement Nov-Avr vs buy&hold), (3) TURN-OF-MONTH (3 premiers jours + dernier
jour du mois), (4) JOUR DE LA SEMAINE. Robustesse : 1re moitié vs 2e moitié (les anomalies décaient
souvent après découverte). t = mean/(std/sqrt(n)) ; |t|>2 ≈ significatif."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
CACHE = os.path.join(E.DATA, 'gspc_daily.parquet')
MONTHS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']


def load_gspc():
    if os.path.exists(CACHE):
        s = pd.read_parquet(CACHE); return pd.Series(s['c'].values, index=pd.to_datetime(s['date']))
    import yfinance as yf
    d = yf.download('^GSPC', start='1950-01-01', progress=False, auto_adjust=True)
    close = d['Close']; close = close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close
    close.index = pd.to_datetime(close.index)
    os.makedirs(E.DATA, exist_ok=True)
    pd.DataFrame({'date': close.index.strftime('%Y-%m-%d'), 'c': close.values}).to_parquet(CACHE, index=False)
    return close


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 and x.std() > 0 else 0.0


def perf(eq, idx):
    eq = np.asarray(eq, float); yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = (eq[-1] ** (1 / yrs) - 1) * 100 if eq[-1] > 0 else -100
    peak = np.maximum.accumulate(eq); mdd = ((eq - peak) / peak).min() * 100
    r = np.diff(eq) / eq[:-1]; sh = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
    return cagr, mdd, sh


def main():
    c = load_gspc(); dret = c.pct_change().fillna(0); idx = c.index
    print(f"S&P 500 : {len(c)} séances {idx[0].date()}..{idx[-1].date()} (~{(idx[-1]-idx[0]).days/365.25:.0f} ans)\n")
    mret = c.resample('ME').last().pct_change().dropna()

    print("(1) RENDEMENT MOYEN PAR MOIS (rendements mensuels, n≈76 chacun) :")
    print(f"    {'mois':>5}{'moy%':>8}{'t':>6}{'win%':>6}    | 2e moitié (robustesse)")
    half = mret.index[len(mret) // 2]
    for mo in range(1, 13):
        x = mret[mret.index.month == mo]; x2 = x[x.index >= half]
        print(f"    {MONTHS[mo-1]:>5}{x.mean()*100:>7.2f}{tstat(x):>6.1f}{(x>0).mean()*100:>5.0f}%    "
              f"{x2.mean()*100:>6.2f}% (n={len(x2)})")

    print("\n(2) BEST 6 MONTHS (Nov-Avr) vs (Mai-Oct) :")
    season = idx.month.isin([11, 12, 1, 2, 3, 4])
    for lbl, mask in [('Nov-Avr', mret.index.month.isin([11, 12, 1, 2, 3, 4])),
                      ('Mai-Oct', mret.index.month.isin([5, 6, 7, 8, 9, 10]))]:
        x = mret[mask]; print(f"    {lbl} : moy {x.mean()*100:+.2f}%/mois  t={tstat(x):.1f}  win={(x>0).mean()*100:.0f}%  (n={len(x)})")
    bh = (1 + dret).cumprod(); seas = (1 + dret.where(season, 0)).cumprod()
    bc, bd, bs = perf(bh.values, idx); sc, sd, ss = perf(seas.values, idx)
    print(f"    -> Buy&Hold       : CAGR {bc:+.1f}%  maxDD {bd:.0f}%  Sharpe {bs:.2f}")
    print(f"    -> Investi Nov-Avr: CAGR {sc:+.1f}%  maxDD {sd:.0f}%  Sharpe {ss:.2f}  (cash Mai-Oct)")

    print("\n(3) TURN-OF-MONTH (3 premiers jours + dernier jour du mois) :")
    g = dret.groupby([idx.year, idx.month]); first = g.cumcount(); last = g.cumcount(ascending=False)
    tom = (first <= 2).values | (last == 0).values
    print(f"    TOM     : moy/jour {dret[tom].mean()*100:+.3f}%  t={tstat(dret[tom]):.1f}  (n={tom.sum()})")
    print(f"    hors TOM: moy/jour {dret[~tom].mean()*100:+.3f}%  t={tstat(dret[~tom]):.1f}  (n={(~tom).sum()})")
    print(f"    -> part des ~{tom.mean()*100:.0f}% de jours 'TOM' dans le rendement total : "
          f"{dret[tom].sum()/dret.sum()*100:.0f}%")

    print("\n(4) JOUR DE LA SEMAINE :")
    for wd, nm in enumerate(['Lun', 'Mar', 'Mer', 'Jeu', 'Ven']):
        x = dret[idx.dayofweek == wd]
        print(f"    {nm} : moy/jour {x.mean()*100:+.3f}%  t={tstat(x):.1f}  win={(x>0).mean()*100:.0f}%")
    print("\n⚠️ Même sur 76 ans : beaucoup d'effets saisonniers ont DÉCLINÉ après leur publication. "
          "Regarde la colonne '2e moitié' — si l'effet n'y est plus, c'est périmé.")


if __name__ == '__main__':
    main()
