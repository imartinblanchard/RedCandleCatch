#!/usr/bin/env python3
"""Prouve que le détecteur LIVE (bot.live_signals.rsi_bounce_signal) == le backtest
(research.price_lab rsi_bounce). Pour chaque entrée détectée par le backtest, on rejoue le détecteur
pur à la bougie d'entrée et on compare (minute + prix). Objectif : N/N identiques, comme vwap (101/101)."""
import os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E
from bot.live_signals import rsi_bounce_signal

CFG = dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20)


def bars_of(g, upto_i):
    d = dt.date.fromisoformat(g['date'])
    out = []
    for j in range(upto_i + 1):
        m = int(g['mins'][j])
        out.append(dict(t=dt.datetime(d.year, d.month, d.day, m // 60, m % 60),
                        o=float(g['o'][j]), h=float(g['h'][j]), l=float(g['l'][j]),
                        c=float(g['c'][j]), v=float(g['v'][j])))
    return out


def main():
    groups, dates = bt.load_groups(); liq = E.liquid_groups(groups, thr=0.20)
    ents = E.entries(liq, 'rsi_bounce', CFG)
    ok = diff = none = 0
    for g, ind, i in ents:
        bars = bars_of(g, i)
        sig = rsi_bounce_signal(bars, bars[-1]['t'], pc=g['pc'], gap_min=3, gap_max=10,
                                rsi_lo=20, win=(570, 720))
        if sig is None:
            none += 1
            print(f"  MANQUÉ live: {g['tk']} {g['date']} @ bougie {int(ind['mins'][i])}")
        elif abs(sig[0] - float(ind['c'][i])) < 1e-6:
            ok += 1
        else:
            diff += 1
            print(f"  PRIX DIFF: {g['tk']} {g['date']} live {sig[0]} vs bt {float(ind['c'][i])}")
    tot = len(ents)
    print(f"\nrsi_bounce : {ok}/{tot} identiques (live==backtest) | {diff} prix diff | {none} manqués live")
    print("✅ détecteur fidèle" if ok == tot else "⚠️ ÉCART — à corriger avant tout déploiement")


if __name__ == '__main__':
    main()
