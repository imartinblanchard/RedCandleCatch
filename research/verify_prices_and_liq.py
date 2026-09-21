#!/usr/bin/env python3
"""(A) VÉRIF prix : le prix capté EN DIRECT (eligibles.csv, as-traded) tombe-t-il dans la
plage des bougies collectées ? Un écart >2x = ajustement rétroactif (reverse split) -> à exclure.
(B) FILTRE liquidité sur la BOUGIE DE DIP : combien de trades on garde, et l'edge tient-il ?
Seulement sur les tickers dont le prix est VÉRIFIÉ."""
import os
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC


def dip_entry(g, dip):
    """-> (idx dip, e, $vol bougie dip) ou None."""
    mins = g['datetime'].map(BC.to_min).values
    o, c, v = g['o'].values, g['c'].values, g['v'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= BC.RTH) & (mins < BC.HARD) & (move <= -dip) & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]
    return i, float(c[i]), float(v[i] * c[i])


def sim_from(g, i, ACT=0.05):
    c = g['c'].values; h = g['h'].values; l = g['l'].values
    mins = g['datetime'].map(BC.to_min).values
    e = float(c[i]); sl = BC.slip_of(e); ef = e * (1 + sl)
    st, ac = e * (1 - BC.STOP), e * (1 + ACT); activ = False; peak = e; ex = None
    for j in range(i + 1, len(c)):
        if mins[j] < BC.RTH or mins[j] >= BC.XE:
            continue
        if mins[j] >= BC.HARD: ex = c[j]; break
        if not activ:
            if l[j] <= st: ex = st; break
            peak = max(peak, h[j])
            if h[j] >= ac: activ = True
        else:
            ts = peak * (1 - BC.TRAIL)
            if l[j] <= ts: ex = ts; break
            peak = max(peak, h[j])
    if ex is None:
        w = c[(mins >= BC.RTH) & (mins < BC.XE)]; ex = float(w[-1]) if len(w) else e
    return (ex * (1 - sl) - ef) / ef * 100


def main():
    elig = pd.read_csv(os.path.join(BC.COLLECTED, 'eligibles.csv'))
    live_price = {(r.date, r.ticker): r.price for r in elig.itertuples() if pd.notna(r.price)}
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]

    trades = []      # (date, tk, sess, dip_idx, e, dvol, pnl, verified)
    mism = []
    for f in files:
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BC.BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            s = lab.get((date, tk))
            if s not in ('PM', 'post-open'):
                continue
            g = g.sort_values('datetime').reset_index(drop=True)
            # (A) vérif prix : live price dans [lo, hi] des bougies ?
            lo, hi = g['l'].min(), g['h'].max()
            lp = live_price.get((date, tk))
            verified = True
            if lp and lp > 0:
                if not (lo * 0.5 <= lp <= hi * 2.0):        # écart > 2x = suspect
                    verified = False
                    mism.append((date, tk, lp, lo, hi))
            dip = 0.05 if s == 'PM' else 0.015
            r = dip_entry(g, dip)
            if not r:
                continue
            i, e, dvol = r
            pnl = sim_from(g, i)
            trades.append((date, tk, s, e, dvol, pnl, verified))

    T = pd.DataFrame(trades, columns=['date', 'tk', 'sess', 'e', 'dvol', 'pnl', 'verified'])
    print(f"(A) VÉRIF PRIX : {len(T)} trades | vérifiés {int(T['verified'].sum())} | "
          f"SUSPECTS (ajustement ?) {int((~T['verified']).sum())}")
    for d, tk, lp, lo, hi in mism:
        print(f"    ⚠️ {d} {tk}: prix live ${lp} hors plage bougies [{lo:.2f}, {hi:.2f}]")

    Tv = T[T['verified']].copy()
    print(f"\n(B) FILTRE LIQUIDITÉ sur la BOUGIE DE DIP (trades vérifiés, n={len(Tv)}) :")
    print(f"  {'seuil $vol dip':16}{'gardés':>8}{'%':>5}{'win%':>6}{'exp/tr':>8}{'pf':>6}{'t':>6}{'TOTAL%':>8}")
    for thr in [0, 20000, 50000, 100000, 200000]:
        sub = Tv[Tv['dvol'] >= thr]['pnl'].values
        s = BC.stats(sub)
        lb = 'aucun' if thr == 0 else f'>= ${thr/1e3:.0f}K'
        if not s:
            print(f"  {lb:16}  n<2"); continue
        print(f"  {lb:16}{s['n']:>8}{100*s['n']/len(Tv):>5.0f}{s['win']:>5.0f}%"
              f"{s['exp']:>+7.2f}%{s['pf']:>6.2f}{s['t']:>6.1f}{s['tot']:>+7.0f}%")


if __name__ == '__main__':
    main()
