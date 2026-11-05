#!/usr/bin/env python3
"""Recherche LARGE de stratégies swing daily (comme pour les gappers) : 13 archétypes × grilles de
params, évalués en FULL + split OOS (train 60% / test 40%), toujours vs BUY & HOLD sur chaque période.
Classé par CAGR OOS. Ticker-générique (défaut nvda) -> prêt pour un univers de titres (boucle).

⚠️ UN seul titre + 3 ans = quasi aucune indépendance stat. Balayer beaucoup de combos sur un titre en
fort trend = sur-ajustement quasi garanti. 'robuste' ici = CAGR>0 sur train ET test ET bat/approche le
B&H sur les DEUX — mais même ça reste fragile. Le vrai juge viendra de l'UNIVERS multi-titres."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.swing_lab import engine as E
from research.swing_lab import signals as S

TRAIN_FRAC = 0.60

# grilles de params par archétype
GRIDS = {
    'sma_cross':         [dict(fast=f, slow=s) for f in (10, 20, 50) for s in (50, 100, 200) if f < s],
    'ema_cross':         [dict(fast=f, slow=s) for f in (5, 10, 20) for s in (20, 50, 100) if f < s],
    'donchian_breakout': [dict(n_in=i, n_out=o) for i in (20, 50, 100) for o in (10, 20, 50) if o <= i],
    'trend_pullback':    [dict(rsi_lo=r, rsi_hi=55, trend=t) for r in (30, 35, 40) for t in (100, 200)],
    'rsi_meanrev':       [dict(rsi_lo=r, rsi_hi=50, trend=t) for r in (25, 30, 35) for t in (None, 200)],
    'momentum':          [dict(n=n) for n in (21, 63, 126, 200)],
    'macd_trend':        [dict(fast=12, slow=26, sig=9), dict(fast=8, slow=21, sig=5)],
    'bollinger_meanrev': [dict(n=n, k=k) for n in (10, 20) for k in (1.5, 2.0, 2.5)],
    'bollinger_breakout':[dict(n=n, k=k) for n in (20, 50) for k in (1.5, 2.0)],
    'keltner_breakout':  [dict(n=n, mult=m) for n in (20, 50) for m in (1.5, 2.0, 3.0)],
    'high_52w':          [dict(win=w, exit_sma=e) for w in (126, 252) for e in (50, 100)],
    'stochastic':        [dict(n=14, lo=lo, hi=80, trend=t) for lo in (15, 20) for t in (None, 200)],
    'supertrend':        [dict(atr_n=a, mult=m) for a in (7, 10, 14) for m in (2.0, 3.0)],
}


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'nvda'
    df = E.load_daily(ticker)
    close = df['c'].to_numpy(float); n = len(close); isp = int(n * TRAIN_FRAC)
    bh_f = E._metrics(np.ones(n), close)
    bh_tr = E._metrics(np.ones(isp), close[:isp]); bh_te = E._metrics(np.ones(n - isp), close[isp:])
    print(f"{ticker.upper()} : {n} séances {df.date.iloc[0]}..{df.date.iloc[-1]} | "
          f"train {isp} / test {n-isp} (split {df.date.iloc[isp]})", flush=True)
    print(f"BUY&HOLD  full CAGR {bh_f['bh_cagr']:+.0f}%  train {bh_tr['bh_cagr']:+.0f}%  "
          f"test {bh_te['bh_cagr']:+.0f}%  (full maxDD {bh_f['bh_maxDD']:.0f}%)\n", flush=True)

    rows = []
    for arch, grid in GRIDS.items():
        fn = S.REGISTRY[arch]
        for P in grid:
            pos = np.asarray(fn(df, P), float)
            f = E._metrics(pos, close); tr = E._metrics(pos[:isp], close[:isp]); te = E._metrics(pos[isp:], close[isp:])
            robust = (tr['cagr'] > 0 and te['cagr'] > 0 and f['sharpe'] > 0.8)
            beats = (te['cagr'] > bh_te['bh_cagr'])          # bat le B&H en OOS
            rows.append(dict(arch=arch, params=str(P), ntr=f['ntr'], expo=round(f['expo']),
                             cagr=round(f['cagr'], 1), maxDD=round(f['maxDD'], 1), sharpe=round(f['sharpe'], 2),
                             cagr_tr=round(tr['cagr'], 1), cagr_te=round(te['cagr'], 1),
                             robust=robust, beats_bh_oos=beats))
    r = pd.DataFrame(rows)
    r.to_csv(os.path.join(os.path.dirname(HERE), 'results', f'strategy_search_{ticker}.csv'), index=False)
    print(f"{len(r)} combos. {int(r.robust.sum())} 'robustes' (CAGR>0 train+test, Sharpe>0.8) | "
          f"{int(r.beats_bh_oos.sum())} battent le B&H en OOS.\n", flush=True)

    cols = ['arch', 'params', 'ntr', 'expo', 'cagr', 'maxDD', 'sharpe', 'cagr_tr', 'cagr_te', 'beats_bh_oos']
    top = r.sort_values('cagr_te', ascending=False).head(15)
    print("TOP 15 par CAGR OOS (test) :")
    print(top[cols].to_string(index=False), flush=True)
    print(f"\nRappel B&H OOS (test) : CAGR {bh_te['bh_cagr']:+.0f}%. "
          f"beats_bh_oos=True => bat le B&H sur la 2e moitié (méfiance : sur-ajustement probable sur 1 titre).")
    print("Prochaine étape = univers MULTI-TITRES : une stratégie qui tient sur BEAUCOUP de noms >> une qui gagne sur NVDA seul.")


if __name__ == '__main__':
    main()
