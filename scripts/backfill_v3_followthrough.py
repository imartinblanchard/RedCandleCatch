"""Backfill follow-through POUR LES ENTRÉES v3 (pas le vieux journal)."""
import sys, os
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
import research.live_lab.backtest as bt
import bot.fetch_followthrough as ft
import collections

g, dates = bt.load_groups()
t = bt.simulate(g, bt.LIVE, slip=True)
by = collections.defaultdict(list)
for _, r in t.iterrows():
    by[r.date].append(r.ticker)
for day in sorted(by):
    print(f"\n########## v3 {day} : {by[day]} ##########", flush=True)
    ft.main(day, 0, tickers=sorted(set(by[day])))
print("\n=== backfill v3 follow-through TERMINÉ ===")
