#!/usr/bin/env python3
"""Registre des stratégies candidates de la FAMILLE REPLI (repli-depuis-HOD), moteur
live_lab.backtest, univers complet. Mirroir des étoiles de leaderboard.variants().
Ajouter une candidate = ajouter une Strategy ici (pas un nouveau script). Lu par
research/core/leaderboard_all.py.  ⚠️ validation LIVE only ; plusieurs sont in-sample."""
from research.live_lab import backtest as bt
from research.core.strategy import Strategy

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)


def _sim(upd):
    P = dict(bt.LIVE); P.update(upd)
    return lambda groups, P=P: bt.simulate(groups, P, slip=True), P['stop_pct']


def _strat(name, upd, status='candidate', notes=''):
    sim, stop = _sim(upd)
    return Strategy(name=name, family='repli', sim=sim, stop=stop,
                    universe='complet', status=status, notes=notes)


CANDIDATES = [
    _strat('liq-eod 5-50/10:00/r12/hodRTH/eod',
           dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
                hod_in_rth=True, exit_mode='eod'),
           status='deployed', notes='config live (cf deploy-liq-eod-live)'),
    _strat('F3 5-50/10:00/r12/hodRTH/trail',
           dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
                hod_in_rth=True, **TRAIL)),
    _strat('F1 5-50/10:30/r8/hodRTH+green/trail',
           dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.08, capit_ratio=-1,
                hod_in_rth=True, require_green=True, **TRAIL)),
    _strat('S1+HOD 5-10/capit2/hodRTH/trail',
           dict(gap_min=5, gap_max=10, retrace_pct=0.08, capit_ratio=2.0, hod_in_rth=True, **TRAIL)),
    _strat('S2+HOD 5-50/10:30/noCapit/hodRTH/trail',
           dict(gap_min=5, gap_max=50, entry_start=630, retrace_pct=0.12, capit_ratio=-1,
                pullback_dvol_min=0, hod_in_rth=True, **TRAIL)),
    _strat('c 3-10/9:30/r8/cap1.6/hodRTH/trail',
           dict(gap_min=3, gap_max=10, entry_start=570, retrace_pct=0.08, capit_ratio=1.6,
                hod_in_rth=True, **TRAIL)),
]
