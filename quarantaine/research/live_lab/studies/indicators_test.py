#!/usr/bin/env python3
"""Stage 2 : ajouter des INDICATEURS/filtres aux meilleures bases. Live only.

Pour chaque base (v3, S1 qualité, S2 haute-fréq), on applique UN indicateur à la fois et on
regarde s'il améliore : VWAP (au-dessus/dessous), bougie verte, prix>open séance, HOD en séance,
anti-couteau (max_drop). Colonnes compte incluses. collected_live uniquement.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))  # racine projet (studies/ = +1 niveau)
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
BASES = {
    'v3 (base)':        dict(),
    'S1 qualité':       dict(gap_min=5.0, gap_max=10.0, retrace_pct=0.08, capit_ratio=2.0, **TRAIL),
    'S2 haute-fréq':    dict(gap_min=5.0, gap_max=50.0, entry_start=630, retrace_pct=0.12,
                            capit_ratio=-1, pullback_dvol_min=0, **TRAIL),
}
INDIC = [
    ('—(base)',          dict()),
    ('VWAP au-dessus',   dict(vwap_side='above')),
    ('VWAP en-dessous',  dict(vwap_side='below')),
    ('bougie verte',     dict(require_green=True)),
    ('prix > open',      dict(require_above_open=True)),
    ('HOD en séance',    dict(hod_in_rth=True)),
    ('anti-couteau 15%', dict(max_drop=15.0)),
]


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    print(f"{len(dates)} séances, OOS≥{split} ({len(tdays)}j). Sizing 2%, slip ON.\n")
    for bname, bupd in BASES.items():
        print(f"######## BASE : {bname} ########")
        print(f"{'+ indicateur':<20}{'n':>4}{'tr/j':>6}{'exp/tr':>8}{'t':>6}{'win':>5}{'pf':>6} | {'OOSexp':>7}{'t':>5} | {'CPTE2%':>8}{'OOS':>7}")
        print('-' * 86)
        for iname, iupd in INDIC:
            P = dict(bt.LIVE); P.update(bupd); P.update(iupd)
            t = bt.simulate(groups, P, slip=True)
            if not len(t):
                print(f"{iname:<20}  0 trade"); continue
            s = bt.stat(t.pnl.to_numpy()); trj = len(t) / t.date.nunique()
            so = bt.stat(t[t.date >= split].pnl.to_numpy()) if split else s
            p2, _ = portfolio(t, 0.02, P['stop_pct']); p2o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
            print(f"{iname:<20}{s['n']:>4}{trj:>6.1f}{s['exp']:>+7.2f}%{s['t']:>+6.2f}{s['win']:>4.0f}%{s['pf']:>6.2f}"
                  f" | {so['exp']:>+6.2f}%{so['t']:>+5.2f} | {p2:>+7.1f}%{p2o:>+6.1f}%")
        print()


if __name__ == '__main__':
    main()
