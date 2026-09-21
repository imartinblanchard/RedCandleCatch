#!/usr/bin/env python3
"""Liquidité À L'ENTRÉE des trades de nos tests (data collectée, SIP) :
 - $vol CUMULÉ session à l'entrée (la métrique du filtre >= 500K)
 - $vol de la BOUGIE de dip (volume_minute × close) = liquidité instantanée -> slippage
Compare à ce qu'on trade en LIVE (dollar_vol du scanner pour aujourd'hui)."""
import os, json
import numpy as np
import pandas as pd
import research.backtest_collected as BC
import research.reclassify_from_bars as RC


def entry_liq(g, dip):
    """-> (cum_$vol_à_l_entrée, $vol_bougie_dip) pour la 1re bougie de dip."""
    g = g.sort_values('datetime').reset_index(drop=True)
    mins = g['datetime'].map(BC.to_min).values
    o, c, v = g['o'].values, g['c'].values, g['v'].values
    move = np.divide(c - o, o, out=np.zeros_like(c), where=o > 0)
    cand = np.where((mins >= BC.RTH) & (mins < BC.HARD) & (move <= -dip) & (c >= BC.PMIN) & (c <= BC.PMAX))[0]
    if not len(cand):
        return None
    i = cand[0]
    cum = float(np.sum(v[:i + 1] * c[:i + 1]))       # $vol cumulé session jusqu'à l'entrée
    bar = float(v[i] * c[i])                          # $vol de la bougie de dip
    return cum, bar


def main():
    rc = RC.build()
    lab = {(r.date, r.ticker): r.gap_session for r in rc.itertuples()}
    files = [f for f in sorted(os.listdir(BC.BARS_DIR)) if f.endswith('.parquet')]
    cums, bars = [], []
    for f in files:
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BC.BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            s = lab.get((date, tk))
            if s not in ('PM', 'post-open'):
                continue
            dip = 0.05 if s == 'PM' else 0.015
            r = entry_liq(g, dip)
            if r:
                cums.append(r[0]); bars.append(r[1])
    cums = np.array(cums); bars = np.array(bars)

    def pct(a):
        return (f"médiane ${np.median(a)/1e6:.2f}M | p25 ${np.percentile(a,25)/1e6:.2f}M | "
                f"p10 ${np.percentile(a,10)/1e3:.0f}K | min ${a.min()/1e3:.0f}K")
    print(f"TESTS (data collectée, {len(cums)} trades) — liquidité À L'ENTRÉE :")
    print(f"  $vol CUMULÉ session à l'entrée : {pct(cums)}")
    print(f"  $vol de la BOUGIE de dip       : {pct(bars)}")
    print(f"  bougies de dip < $50K (illiquide) : {int((bars<50000).sum())}/{len(bars)} "
          f"({100*(bars<50000).mean():.0f}%)")
    print(f"  bougies de dip < $20K            : {int((bars<20000).sum())}/{len(bars)} "
          f"({100*(bars<20000).mean():.0f}%)")

    # LIVE aujourd'hui : dollar_vol du scanner (volume cumulé × prix) pour les tickers tradés
    print("\nLIVE aujourd'hui (dollar_vol du scanner à l'éligibilité) :")
    e = json.load(open(os.path.join(BC.COLLECTED, '..', 'computed', 'redcandlecatch-eligible-2026-09-18.json')))
    traded = ['BIAF','MEDS','AKAN','FWDI','ABTC','BMNU','TAOX','QMLS','CYPH','BSEM','LGHL','GLOO','DFDV','SLE','AIAI']
    vals = []
    for tk in traded:
        dv = (e.get(tk) or {}).get('dollar_vol')
        vals.append(dv)
        print(f"  {tk:6} dollar_vol = {('$%.2fM'%(dv/1e6)) if dv else '(non renseigné)'}")
    ok = [v for v in vals if v]
    if ok:
        print(f"  -> médiane live ${np.median(ok)/1e6:.2f}M (n={len(ok)})")


if __name__ == '__main__':
    main()
