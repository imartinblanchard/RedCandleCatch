#!/usr/bin/env python3
"""
Définitions du DIP pour RedCandleCatch (S&P 500, daily).

Chaque fabrique renvoie signal_fn(df) -> np.array booléen (aligné sur df), calculé
PAR TITRE et vectorisé. Le dip est mesuré close-à-close sur les `nbars` derniers jours :
    ret_N = close[i] / close[i-nbars] - 1
- dip_fixed(pct, nbars) : ret_N <= -pct           (même seuil % pour tous les titres)
- dip_vol(k, nbars)     : ret_N <= -k * sigma_N   (seuil PROPRE à chaque titre)
      sigma_N = sigma journalier point-in-time (load_table) * sqrt(nbars)
      -> un titre calme déclenche sur une petite baisse, un volatil sur une grosse.
"""
import numpy as np


def _ret_n(df, nbars):
    return df.groupby('ticker', sort=False)['c'].transform(lambda s: s / s.shift(nbars) - 1)


def dip_fixed(pct, nbars=1):
    def signal(df):
        return (_ret_n(df, nbars) <= -pct).values
    signal.label = f'fixe {pct*100:.1f}%/{nbars}j'
    return signal


def dip_vol(k, nbars=1):
    def signal(df):
        ret_n = _ret_n(df, nbars)
        thr = -k * df['sigma'] * np.sqrt(nbars)
        return (ret_n <= thr).values & df['sigma'].notna().values
    signal.label = f'vol {k:.1f}σ/{nbars}j'
    return signal
