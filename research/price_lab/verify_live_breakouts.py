#!/usr/bin/env python3
"""Prouve que les détecteurs LIVE bb_breakout_signal / higher_high_signal (bot.live_signals)
== le backtest (research.price_lab bb_breakout / higher_high_momentum). Pour chaque entrée du
backtest, on rejoue le détecteur pur à la bougie d'entrée et on compare (minute + prix).
Objectif : N/N identiques. À lancer AVANT tout déploiement live."""
import os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E
from bot.live_signals import bb_breakout_signal, higher_high_signal

GAP = dict(gap_min=10, gap_max=20, entry_start=570, entry_end=720)


def bars_of(g, upto_i):
    d = dt.date.fromisoformat(g['date'])
    return [dict(t=dt.datetime(d.year, d.month, d.day, int(g['mins'][j]) // 60, int(g['mins'][j]) % 60),
                 o=float(g['o'][j]), h=float(g['h'][j]), l=float(g['l'][j]),
                 c=float(g['c'][j]), v=float(g['v'][j])) for j in range(upto_i + 1)]


def check(name, detector, liq, **kw):
    ents = E.entries(liq, name, {**GAP, **kw})
    ok = diff = none = 0
    for g, ind, i in ents:
        bars = bars_of(g, i)
        sig = detector(bars, bars[-1]['t'], pc=g['pc'], gap_min=10, gap_max=20, win=(570, 720), **kw)
        if sig is None:
            none += 1; print(f"  MANQUÉ live: {g['tk']} {g['date']} @ {int(ind['mins'][i])}")
        elif abs(sig[0] - float(ind['c'][i])) < 1e-6:
            ok += 1
        else:
            diff += 1; print(f"  PRIX DIFF: {g['tk']} {g['date']} live {sig[0]} vs bt {float(ind['c'][i])}")
    tot = len(ents)
    print(f"{name} : {ok}/{tot} identiques | {diff} prix diff | {none} manqués live  "
          f"{'✅' if ok == tot else '⚠️ ÉCART'}")
    return ok == tot


def main():
    groups, dates = bt.load_groups(); liq = E.liquid_groups(groups, thr=0.35)
    a = check('bb_breakout', bb_breakout_signal, liq, squeeze_bw=0.04)
    b = check('higher_high_momentum', higher_high_signal, liq, hh_win=3)
    print("\n✅ détecteurs fidèles" if a and b else "\n⚠️ ÉCART — corriger avant déploiement")


if __name__ == '__main__':
    main()
