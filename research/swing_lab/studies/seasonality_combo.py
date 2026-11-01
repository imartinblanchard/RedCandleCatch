#!/usr/bin/env python3
"""TEST des POSSIBILITÉS saisonnières, combinées :
(A) Stratégies calendaires SEULES sur le S&P 500 long (^GSPC 1950→, 77 ans) : buy&hold vs TOM-only
    vs Nov-Avr-only vs hybride (plein en Nov-Avr, TOM-only en Mai-Oct). Profil rendement/risque.
(B) MOMENTUM × CALENDRIER sur le Nasdaq-100 (Alpaca ~6 ans) : rotation lb63/K10 de base vs masquée
    TOM vs masquée Nov-Avr. Le calendrier améliore-t-il le momentum ?
(C) Cross-check saisonnalité sur le Nasdaq long (^IXIC) : l'effet Nov-Avr / TOM tient-il aussi ?
⚠️ (A)(C) = 77/55 ans = robuste ; (B) = 6 ans = indicatif. Masquer = cash les jours hors fenêtre."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
from research.swing_lab.universes import UNIVERSES
from research.swing_lab.studies.momentum_rotation import price_matrix, perf


def load_yf(symbol, cache):
    f = os.path.join(E.DATA, cache)
    if os.path.exists(f):
        s = pd.read_parquet(f); return pd.Series(s['c'].values, index=pd.to_datetime(s['date']))
    import yfinance as yf
    d = yf.download(symbol, start='1950-01-01', progress=False, auto_adjust=True)
    cl = d['Close']; cl = cl.iloc[:, 0] if isinstance(cl, pd.DataFrame) else cl
    cl.index = pd.to_datetime(cl.index)
    pd.DataFrame({'date': cl.index.strftime('%Y-%m-%d'), 'c': cl.values}).to_parquet(f, index=False)
    return cl


def tom_mask(idx):
    g = pd.Series(0, index=idx).groupby([idx.year, idx.month])
    return pd.Series((g.cumcount() <= 2).values | (g.cumcount(ascending=False) == 0).values, index=idx)


def season_mask(idx):
    return pd.Series(pd.DatetimeIndex(idx).month.isin([11, 12, 1, 2, 3, 4]), index=idx)


def eq_from(dret, mask):
    return (1 + (dret * mask.astype(float))).cumprod()


def show(lbl, eq, idx, expo):
    c, d, s = perf(eq.values, idx)
    print(f"  {lbl:<34} CAGR {c:>6.1f}%  maxDD {d:>6.1f}%  Sharpe {s:>4.2f}  expo {expo*100:>3.0f}%")


def part_index(name, c):
    dret = c.pct_change().fillna(0); idx = c.index
    tom = tom_mask(idx); sea = season_mask(idx)
    hybrid = sea | (~sea & tom)                         # plein en Nov-Avr, TOM-only en Mai-Oct
    print(f"\n{name} : {idx[0].date()}..{idx[-1].date()} (~{(idx[-1]-idx[0]).days/365.25:.0f} ans)")
    show('Buy & Hold', (1 + dret).cumprod(), idx, 1.0)
    show('TOM-only (cash sinon)', eq_from(dret, tom), idx, tom.mean())
    show('Nov-Avr-only', eq_from(dret, sea), idx, sea.mean())
    show('Hybride (NovAvr plein + TOM en été)', eq_from(dret, hybrid), idx, hybrid.mean())


def main():
    # (A) S&P 500 long
    part_index("(A) S&P 500 (^GSPC)", load_yf('^GSPC', 'gspc_daily.parquet'))
    # (C) Nasdaq long
    part_index("(C) Nasdaq Composite (^IXIC)", load_yf('^IXIC', 'ixic_daily.parquet'))

    # (B) Momentum Nasdaq-100 × calendrier
    px = price_matrix(UNIVERSES['nasdaq100']); ret = px.pct_change()
    valid = px.notna().sum(axis=1); px = px.loc[valid[valid >= 30].index[0]:]; ret = ret.loc[px.index]
    idx = px.index
    mom = px / px.shift(63) - 1
    rb = px.groupby(px.index.to_period('M')).tail(1).index
    W = pd.DataFrame(np.nan, index=idx, columns=px.columns)
    for d in rb:
        m = mom.loc[d].dropna(); m = m[m > 0]; w = pd.Series(0.0, index=px.columns)
        if len(m): w[m.nlargest(10).index] = 0.1
        W.loc[d] = w
    W = W.ffill().fillna(0.0)
    pr = (W.shift(1) * ret).sum(axis=1).fillna(0)       # rendement quotidien du momentum de base
    tom = tom_mask(idx); sea = season_mask(idx)
    print(f"\n(B) MOMENTUM Nasdaq-100 lb63/K10 × calendrier ({idx[0].date()}..{idx[-1].date()}, ~6 ans) :")
    show('momentum base', (1 + pr).cumprod(), idx, (W.sum(axis=1) > 0).mean())
    show('momentum × TOM-only', (1 + pr * tom.astype(float)).cumprod(), idx, tom.mean())
    show('momentum × Nov-Avr', (1 + pr * sea.astype(float)).cumprod(), idx, sea.mean())
    print("\n-> on cherche : garder ~le rendement en RÉDUISANT le risque/l'exposition (capital-efficace).")
    print("⚠️ (A)(C) robustes (longue histoire) ; (B) = 6 ans, indicatif. Aucun coût de transaction modélisé.")


if __name__ == '__main__':
    main()
