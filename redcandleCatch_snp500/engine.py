#!/usr/bin/env python3
"""
Moteur de backtest DAILY pour RedCandleCatch (S&P 500).

Point-in-time, une position à la fois par titre. Entrée au CLOSE du jour de signal.
Sortie = max(stop fixe, trailing) touché en INTRADAY (low du jour), sinon backstop après
HOLD jours (sortie au close). Le peak (pour le trailing) ne compte QUE les jours APRÈS
l'entrée (leçon du bug RedCandleCatch 15/09).

Une "stratégie" = une fonction d'entrée check(g, i) -> bool (voir strategies.py).
Les paramètres de sortie (stop, trail, hold) sont passés au moteur -> on peut les balayer
indépendamment de la définition d'entrée.
"""
import numpy as np
import pandas as pd


def load_table(path, vol_lookback=20):
    """Charge le parquet daily et ajoute, PAR TITRE et point-in-time :
       ret1 = rendement close-à-close ; sigma = écart-type glissant de ret1 (décalé de 1)."""
    df = pd.read_parquet(path).sort_values(['ticker', 'date']).reset_index(drop=True)
    g = df.groupby('ticker', sort=False)
    df['ret1'] = g['c'].pct_change()
    # sigma point-in-time : n'utilise que les rendements JUSQU'À i-1
    df['sigma'] = g['ret1'].transform(
        lambda s: s.rolling(vol_lookback, min_periods=max(5, vol_lookback // 2)).std().shift(1))
    return df


def run(df, stop, trail, hold, target=None, slip=0.001, sigcol='sig'):
    """df doit contenir une colonne booléenne `sig` (signal d'entrée, cf strategies.py).
    Entrée au close du jour de signal. Sorties (priorité intraday) :
      - STOP fixe à eraw*(1-stop)
      - TRAIL à peak*(1-trail)   (trail=None -> désactivé)
      - TP  (take-profit) à eraw*(1+target)  (target=None -> désactivé)
      - HOLD : backstop après `hold` jours (sortie au close)
    Renvoie la liste des trades."""
    trades = []
    for tk, g in df.groupby('ticker', sort=False):
        g = g.reset_index(drop=True)
        h = g['h'].values; l = g['l'].values; c = g['c'].values
        sig = g[sigcol].values
        n = len(g); pos = None
        for i in range(n):
            if pos is None:
                if sig[i]:
                    e = float(c[i])
                    pos = {'i0': i, 'eraw': e, 'efill': e * (1 + slip), 'peak': e}
            else:
                held = i - pos['i0']
                pos['peak'] = max(pos['peak'], float(h[i]))     # peak = jours APRÈS l'entrée
                stop_lvl = pos['eraw'] * (1 - stop)
                if trail is not None:
                    stop_lvl = max(stop_lvl, pos['peak'] * (1 - trail))
                if target is not None and h[i] >= pos['eraw'] * (1 + target):   # TP touché en premier
                    _close(trades, tk, g, pos, pos['eraw'] * (1 + target) * (1 - slip), 'TP', i, held)
                    pos = None
                elif l[i] <= stop_lvl:                          # STOP/TRAIL touché en intraday
                    reason = 'TRAIL' if (trail is not None and stop_lvl > pos['eraw'] * (1 - stop)) else 'STOP'
                    _close(trades, tk, g, pos, stop_lvl * (1 - slip), reason, i, held)
                    pos = None
                elif held >= hold:                              # backstop : sortie au close
                    _close(trades, tk, g, pos, float(c[i]) * (1 - slip), 'HOLD', i, held)
                    pos = None
        if pos is not None:
            _close(trades, tk, g, pos, float(c[n - 1]) * (1 - slip), 'EOD', n - 1, n - 1 - pos['i0'])
    return trades


def _close(trades, tk, g, pos, exit_fill, reason, i, held):
    e = pos['efill']
    trades.append({
        'ticker': tk, 'entry_date': g['date'].iloc[pos['i0']], 'exit_date': g['date'].iloc[i],
        'entry': round(pos['eraw'], 4), 'exit': round(exit_fill, 4),
        'pnl_pct': (exit_fill - e) / e * 100, 'reason': reason, 'days': int(held),
        'mfe_pct': (pos['peak'] - pos['eraw']) / pos['eraw'] * 100,
        'sigma': float(g['sigma'].iloc[pos['i0']]) if not np.isnan(g['sigma'].iloc[pos['i0']]) else np.nan,
    })


def metrics(trades):
    if not trades:
        return {'n': 0}
    x = np.array([t['pnl_pct'] for t in trades])
    pf = x[x > 0].sum() / (-x[x < 0].sum() or 1e-9)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
    return {'n': len(x), 'exp': round(x.mean(), 3), 'win': round(100 * (x > 0).mean(), 0),
            'pf': round(pf, 2), 'total': round(x.sum(), 0), 't': round(t, 1),
            'avg_days': round(np.mean([tr['days'] for tr in trades]), 1)}
