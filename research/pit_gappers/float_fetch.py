#!/usr/bin/env python3
"""Fetch le float (+ inst%, market cap) par ticker du dataset PIT, via Finviz. Caché/résumable.
⚠️ Finviz donne le float ACTUEL, pas celui à la date historique du trade (dilution/splits) ->
approximation d'ordre de grandeur. Sortie : data/float_cache.json"""
import os, sys, json, time
sys.path.insert(0, '/home/martin/dev/stock-journal-long')
import pandas as pd
import bot.redcandlecatch_scan as s

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
CACHE = os.path.join(DATA, 'float_cache.json')

t = pd.read_parquet(os.path.join(DATA, 'trades_grid.parquet'))
tks = sorted(t['ticker'].unique())
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
todo = [tk for tk in tks if tk not in cache]
print(f"{len(tks)} tickers, {len(cache)} déjà en cache, {len(todo)} à fetcher", flush=True)

for i, tk in enumerate(todo):
    try:
        f = s.fetch_fundamentals(tk)
        cache[tk] = {'float': f.get('float_shares'), 'inst': f.get('inst_pct'),
                     'mcap': f.get('market_cap')}
    except Exception as e:
        cache[tk] = {'float': None, 'inst': None, 'mcap': None}
    if i % 100 == 0:
        json.dump(cache, open(CACHE, 'w'))
        got = sum(1 for v in cache.values() if v.get('float'))
        print(f"  ...{i+1}/{len(todo)} | float connu: {got}/{len(cache)}", flush=True)
    time.sleep(0.05)

json.dump(cache, open(CACHE, 'w'))
got = sum(1 for v in cache.values() if v.get('float'))
print(f"\n✅ {len(cache)} tickers, float connu pour {got} ({100*got/len(cache):.0f}%) -> {CACHE}")
