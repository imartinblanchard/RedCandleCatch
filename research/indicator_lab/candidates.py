#!/usr/bin/env python3
"""Registre des stratégies candidates de la FAMILLE INDICATEURS (combinaisons d'indicateurs),
moteur indicator_lab.engine, univers freq-filtré, 1re heure. Ajouter une candidate = ajouter
une Strategy ici. Lu par research/core/leaderboard_all.py.
⚠️ in-sample 23 j, seuils choisis sur ces données -> forward-test requis (cf indicator-lab-univers-liquide)."""
from research.indicator_lab import engine as E
from research.core.strategy import Strategy

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05)   # 04/11 : 2%->5% (déployé, cf terminator)
HOUR1 = dict(entry_start=570, entry_end=630)        # 1re heure (où l'edge se concentre)


def _strat(name, signal, upd, status='candidate', notes=''):
    P = dict(HOUR1); P.update(upd)
    return Strategy(name=name, family='indic',
                    sim=lambda groups, s=signal, P=P: E.simulate(groups, s, P),
                    stop=0.10, universe='freq-filtré', status=status, notes=notes)


CANDIDATES = [
    _strat('vwap_reclaim rv60 9:30>15:55 tp30', 'vwap_reclaim',
           dict(rvol_gate=60.0, entry_end=955, exit_mode='tp', tp_pct=0.30),
           notes='DÉBRANCHÉ 05/11 : audit = buy-the-open déguisé (62% entrées à 9:30), fragile. Repère.'),
    _strat('vwap_reclaim rvol>=60', 'vwap_reclaim', dict(rvol_gate=60.0, **TRAIL),
           notes='1re heure/trail10/5 ; repère'),
    _strat('vwap_reclaim rvol>=30', 'vwap_reclaim', dict(rvol_gate=30.0, **TRAIL)),
    _strat('bb_breakout macd>=0.03', 'bb_breakout', dict(macd_hist_min=0.03, **TRAIL)),
    _strat('macd_cross rvol>=2', 'macd_cross', dict(rvol_min=2.0, **TRAIL)),
]
