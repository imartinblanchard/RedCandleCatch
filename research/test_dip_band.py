#!/usr/bin/env python3
"""
POST-OPEN : SEUIL simple (dip >= 1,5%, n'importe quelle profondeur) vs BANDE (plancher 1,5%
mais PLAFOND sur la profondeur -> on saute les bougies trop violentes, ex DFDV -6,6%).

Data = collectée (SANS biais du survivant). Classement PM/post-open = PAR BOUGIES (gap_session
de reclassify_from_bars), correct même les jours où le dashboard a démarré tard -> tous les
jours utilisables. Sortie 2-phases identique au bot (STOP -10% / +5% / TRAIL 2% / 15:55).
"""
import os
import numpy as np
import pandas as pd

import research.backtest_collected as BC
import research.reclassify_from_bars as RC

FLOOR = 0.015                                  # plancher (inchangé) : au moins -1,5%
CAPS = [1.00, 0.05, 0.04, 0.03, 0.025, 0.02]   # plafond de profondeur (1.00 = pas de plafond = actuel)


def sim_band(g, floor, cap, start_min=BC.RTH):
    """Entrée = 1re bougie CLÔTURÉE dont le dip est DANS la bande [floor, cap]."""
    mins = g['datetime'].map(BC.to_min).values
    o, h, l, c = g['o'].values, g['h'].values, g['l'].values, g['c'].values
    start = max(start_min, BC.RTH)
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    # dip dans la bande : -cap <= move <= -floor  (assez profond MAIS pas trop)
    cand = np.where((mins >= start) & (mins < BC.HARD)
                    & (move <= -floor) & (move >= -cap)
                    & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]; e = float(c[i]); sl = BC.slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - BC.STOP), e * (1 + BC.ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < BC.RTH or mins[j] >= BC.XE:
            continue
        if mins[j] >= BC.HARD:
            ex = c[j]; break
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - BC.TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        w = c[(mins >= BC.RTH) & (mins < BC.XE)]
        ex = float(w[-1]) if len(w) else e
    return (ex * (1 - sl) - ef) / ef * 100


def main():
    rc = RC.build()                             # classement PAR BOUGIES
    po = set((r.date, r.ticker) for r in rc.itertuples() if r.gap_session == 'post-open')
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    data = [(f[:-8], pd.read_parquet(os.path.join(BC.BARS_DIR, f))) for f in files]

    print(f"POST-OPEN (classé par bougies) | data collectée SANS biais | plancher -{FLOOR*100:.1f}%\n")
    print(f"{'plafond':10}{'n':>5}{'tr/j':>6}{'win%':>6}{'gain+':>7}{'perte-':>8}{'exp/tr':>8}{'pf':>6}{'t':>6}{'TOTAL%':>8}")
    ndays = len(data)
    for cap in CAPS:
        res = []
        for date, df in data:
            for tk, g in df.groupby('ticker', sort=False):
                if (date, tk) not in po:
                    continue
                p = sim_band(g.reset_index(drop=True), FLOOR, cap)
                if p is not None:
                    res.append(p)
        s = BC.stats(res)
        lab = 'aucun' if cap >= 1.0 else f'-{cap*100:.1f}%'
        if not s:
            print(f"{lab:10}  n<2 ({len(res)})"); continue
        print(f"{lab:10}{s['n']:>5}{s['n']/ndays:>6.1f}{s['win']:>5.0f}%"
              f"{s['gain']:>+6.1f}%{s['loss']:>+7.1f}%{s['exp']:>+7.2f}%{s['pf']:>6.2f}{s['t']:>6.1f}{s['tot']:>+7.0f}%")
    print("\nplafond 'aucun' = comportement ACTUEL du bot (seuil simple).")
    print("Bande = on saute les bougies plus profondes que le plafond (ex DFDV -6,6%) et on")
    print("attend une bougie dans [plancher, plafond]. Échantillon PETIT -> directionnel.")


if __name__ == '__main__':
    main()
