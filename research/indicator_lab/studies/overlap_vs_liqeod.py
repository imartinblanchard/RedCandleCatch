#!/usr/bin/env python3
"""Les meilleurs archétypes indicateurs (univers freq-filtré, tous gaps, 1re heure) prennent-ils
des tickers DIFFÉRENTS de liq-eod (la stratégie repli déployée) — nouvel alpha ou redondance ?

Overlap = Jaccard des ensembles de trades (ticker-jour). Puis portefeuille combiné liq-eod + le
meilleur archétype complémentaire : CPTE full/OOS vs liq-eod seule (ça ajoute, ou non ?).
⚠️ live only, in-sample 23 j, hypothèses. collected_live uniquement."""
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
# meilleurs archétypes indicateurs : tous gaps, 1re heure (09:30-10:30)
INDIC = {
    'bb_breakout':    dict(entry_start=570, entry_end=630, rvol_min=3.0, **TRAIL),
    'rsi_bounce':     dict(entry_start=570, entry_end=630, **TRAIL),
    'vwap_reclaim':   dict(entry_start=570, entry_end=630, rvol_min=2.0, **TRAIL),
    'macd_cross':     dict(entry_start=570, entry_end=630, rvol_min=2.0, **TRAIL),
    'obv_divergence': dict(entry_start=570, entry_end=630, exit_mode='eod'),
}


def tkset(t):
    return set(zip(t.ticker, t.date))


def jacc(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    liq = E.liquid_groups(groups)
    print(f"{len(dates)} séances, OOS≥{split}. liq-eod sur univers complet, indicateurs sur freq-filtré.\n", flush=True)

    # liq-eod (repli déployé) — univers complet gap 5-50
    Pl = dict(bt.LIVE); Pl.update(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12,
                                  capit_ratio=-1, hod_in_rth=True, exit_mode='eod')
    tl = bt.simulate(groups, Pl, slip=True)
    sets = {'liq-eod': tkset(tl)}
    trades = {'liq-eod': tl[['ticker', 'date', 'entry_min', 'pnl']]}
    print(f"liq-eod : n={len(tl)}  {len(tl)/tl.date.nunique():.1f}/j  exp={tl.pnl.mean():+.2f}%", flush=True)
    for name, upd in INDIC.items():
        t = E.simulate(liq, name, upd)
        sets[name] = tkset(t); trades[name] = t[['ticker', 'date', 'entry_min', 'pnl']]
        print(f"{name:<15}: n={len(t)}  {len(t)/t.date.nunique():.1f}/j  exp={t.pnl.mean():+.2f}%", flush=True)

    print("\n########## OVERLAP DE TICKERS vs liq-eod (% Jaccard, 0=disjoint) ##########")
    for name in INDIC:
        ov = jacc(sets[name], sets['liq-eod']) * 100
        inter = len(sets[name] & sets['liq-eod'])
        print(f"  {name:<15} overlap {ov:4.0f}%   ({inter} trades communs sur {len(sets[name])})", flush=True)

    print("\n########## COMBO liq-eod + archétype (union 1/ticker-jour, sizing 2%) ##########")
    cl, dl = portfolio(tl, 0.02, 0.10); clo, _ = portfolio(tl, 0.02, 0.10, days=tdays)
    print(f"  {'liq-eod seule':<24} {len(tl):>4} tr  CPTE {cl:+6.1f}%  OOS {clo:+6.1f}%  maxDD {dl:+5.1f}%", flush=True)
    for name in INDIC:
        both = pd.concat([trades['liq-eod'], trades[name]], ignore_index=True)
        comb = both.sort_values('entry_min').drop_duplicates(['ticker', 'date'], keep='first')
        cc, dd = portfolio(comb, 0.02, 0.10); cco, _ = portfolio(comb, 0.02, 0.10, days=tdays)
        print(f"  {'+ '+name:<24} {len(comb):>4} tr  CPTE {cc:+6.1f}%  OOS {cco:+6.1f}%  maxDD {dd:+5.1f}%  "
              f"(Δfull {cc-cl:+.1f})", flush=True)
    print("\n  -> overlap bas + CPTE combo > liq-eod seule = vrai nouvel alpha complémentaire.", flush=True)


if __name__ == '__main__':
    main()
