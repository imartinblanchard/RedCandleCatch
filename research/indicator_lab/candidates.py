#!/usr/bin/env python3
"""Registre des stratégies candidates de la FAMILLE INDICATEURS (combinaisons d'indicateurs),
moteur indicator_lab.engine, univers freq-filtré, 1re heure. Ajouter une candidate = ajouter
une Strategy ici. Lu par research/core/leaderboard_all.py.
⚠️ in-sample 23 j, seuils choisis sur ces données -> forward-test requis (cf indicator-lab-univers-liquide)."""
from research.indicator_lab import engine as E
from research.core.strategy import Strategy

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
HOUR1 = dict(entry_start=570, entry_end=630)        # 1re heure (où l'edge se concentre)


def _strat(name, signal, upd, status='candidate', notes=''):
    P = dict(HOUR1); P.update(upd)
    return Strategy(name=name, family='indic',
                    sim=lambda groups, s=signal, P=P: E.simulate(groups, s, P),
                    stop=0.10, universe='freq-filtré', status=status, notes=notes)


CANDIDATES = [
    _strat('vwap_reclaim rvol>=60', 'vwap_reclaim', dict(rvol_gate=60.0, **TRAIL),
           notes='candidate n°1 : 4,6 tr/j, +3,53%/tr, CPTE +95%'),
    _strat('vwap_reclaim rvol>=30', 'vwap_reclaim', dict(rvol_gate=30.0, **TRAIL)),
    _strat('bb_breakout macd>=0.03', 'bb_breakout', dict(macd_hist_min=0.03, **TRAIL)),
    _strat('macd_cross rvol>=2', 'macd_cross', dict(rvol_min=2.0, **TRAIL)),
]
