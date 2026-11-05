#!/usr/bin/env python3
"""VÉRIFICATION live==backtest pour vwap_reclaim(rvol>=60). Rejoue l'historique bougie-par-bougie
à travers le détecteur PUR du terminator (bot.live_signals.vwap_reclaim_signal) et compare aux
entrées du BACKTEST (indicator_lab.engine). But : garantir que le bot live détectera EXACTEMENT
les mêmes entrées avant de l'activer. Univers = freq-filtré (latepm>=0.20), comme le backtest.

Rapport : accord / entrées du backtest absentes en live / entrées live en trop / minutes différentes.
⚠️ Utilise le volume du parquet (= backtest) ; la justesse du volume LIVE (×100) est validée à part."""
import os, sys
from datetime import datetime, time
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
from research.live_lab import backtest as bt
from research.indicator_lab import engine as E
from bot.live_signals import vwap_reclaim_signal

TRAIL = dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
CFG = dict(entry_start=570, entry_end=630, rvol_gate=60.0, **TRAIL)   # la candidate déployable


def group_to_bars(g):
    """Reconstruit la liste de bougies {'t':datetime,...} d'un groupe (comme le voit le live)."""
    d = datetime.strptime(g['date'], '%Y-%m-%d').date()
    bars = []
    for k in range(len(g['mins'])):
        m = int(g['mins'][k])
        bars.append(dict(t=datetime.combine(d, time(m // 60, m % 60)),
                         o=float(g['o'][k]), h=float(g['h'][k]), l=float(g['l'][k]),
                         c=float(g['c'][k]), v=float(g['v'][k])))
    return bars


def replay_entry(bars):
    """Rejoue bougie-par-bougie (one-shot) : 1re bougie de la fenêtre où le détecteur fire."""
    for i, b in enumerate(bars):
        m = b['t'].hour * 60 + b['t'].minute
        if m < CFG['entry_start'] or m > CFG['entry_end']:
            continue
        sig = vwap_reclaim_signal(bars[:i + 1], b['t'], rvol_min=CFG['rvol_gate'],
                                  win=(CFG['entry_start'], CFG['entry_end']))
        if sig is not None:
            return m, round(sig[0], 4)
    return None


def main():
    groups, dates = bt.load_groups()
    liq = E.liquid_groups(groups)
    print(f"{len(dates)} séances, univers freq-filtré = {len(liq)} ticker-jours.\n", flush=True)

    # (A) entrées du BACKTEST
    tb = E.simulate(liq, 'vwap_reclaim', CFG)
    bt_entries = {(r.ticker, r.date): (r.entry_min, round(r.entry, 4)) for r in tb.itertuples()}

    # (B) entrées du DÉTECTEUR LIVE (replay)
    live_entries = {}
    for g in liq:
        e = replay_entry(group_to_bars(g))
        if e is not None:
            live_entries[(g['tk'], g['date'])] = e

    bk, lv = set(bt_entries), set(live_entries)
    both = bk & lv
    same_min = sum(1 for k in both if bt_entries[k][0] == live_entries[k][0])
    same_all = sum(1 for k in both if bt_entries[k] == live_entries[k])
    print(f"BACKTEST : {len(bk)} entrées | LIVE-détecteur : {len(lv)} entrées | communes : {len(both)}")
    print(f"  même MINUTE d'entrée : {same_min}/{len(both)}   |   même minute ET prix : {same_all}/{len(both)}")
    print(f"  dans backtest mais PAS live : {len(bk - lv)}   |   live en trop (pas backtest) : {len(lv - bk)}")

    def dump(title, keys, src1, src2=None):
        if not keys: return
        print(f"\n  {title} ({len(keys)}) :")
        for k in sorted(keys)[:15]:
            a = src1.get(k); b = src2.get(k) if src2 else None
            print(f"    {k[1]} {k[0]:<6} backtest={a}  live={b}" if src2 else f"    {k[1]} {k[0]:<6} {a}")
    dump("BACKTEST absentes en live", bk - lv, bt_entries)
    dump("LIVE en trop", lv - bk, live_entries)
    dump("MINUTE différente", {k for k in both if bt_entries[k][0] != live_entries[k][0]}, bt_entries, live_entries)
    verdict = "✅ IDENTIQUE" if (bk == lv and same_min == len(both)) else "⚠️ ÉCARTS — à comprendre avant live"
    print(f"\nVERDICT : {verdict}")


if __name__ == '__main__':
    main()
