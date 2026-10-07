#!/usr/bin/env python3
"""APRÈS la clôture : capture la NEWS Yahoo Finance (horodatée) de tout l'univers capté en
direct par le dashboard (data/collected_live/universe-YYYY-MM-DD.json).

⚠️ Yahoo ne renvoie que les ~10 DERNIERS articles par ticker (pas de requête par date) :
donc à lancer LE JOUR MÊME (comme fetch_universe_bars) pour capter la news du jour. La
donnée s'accumule FORWARD (on ne peut pas reconstruire le passé). Couverture partielle des
micro-caps assumée (beaucoup de gaps low-float n'ont aucune news indexée).

Sortie : data/collected_live/news-YYYY-MM-DD.json
  { ticker: [ {time_utc: ISO8601, title: str, source: str}, ... ] }
Le backtest (research/live_lab/backtest.py, load_news) ne garde que les articles réellement
DATÉS du jour et calcule news_before (avant l'heure d'entrée) de façon causale.

Usage : python -m bot.fetch_universe_news              (jour courant)
        python -m bot.fetch_universe_news --date 2026-09-24
"""
import os, sys, json, time, argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot.collect_universe as cu

ET = ZoneInfo('America/New_York')
DIR = cu.DIR
SLEEP = 0.5                                        # pause entre tickers (politesse Yahoo)


def _extract(art):
    """Normalise un article yfinance (formats ancien plat / nouveau 'content')."""
    c = art.get('content', art)
    title = c.get('title') or c.get('headline') or ''
    src = ''
    prov = c.get('provider') or {}
    if isinstance(prov, dict):
        src = prov.get('displayName', '')
    src = src or c.get('publisher') or art.get('publisher') or ''
    ts = c.get('pubDate') or c.get('displayTime') or c.get('providerPublishTime') or art.get('providerPublishTime')
    if isinstance(ts, (int, float)):               # epoch -> ISO UTC
        ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return {'time_utc': ts, 'title': str(title)[:200], 'source': str(src)[:40]}


def main(day):
    uni = cu.load(day)
    if not uni:
        print(f"[{day}] aucun univers capté (universe-{day}.json absent)"); return
    import yfinance as yf
    path = os.path.join(DIR, f'news-{day}.json')
    out = json.load(open(path)) if os.path.exists(path) else {}
    todo = [tk for tk in uni if tk not in out]
    print(f"[{day}] univers {len(uni)} | déjà fait {len(out)} | à faire {len(todo)}", flush=True)
    n_with = 0
    for i, tk in enumerate(todo):
        try:
            # yfinance 1.7.0 : Ticker.news/get_news passent par un POST /v1/finance/search
            # qui renvoie 404 (mort). yf.Search(...).news utilise le GET équivalent, qui marche.
            arts = yf.Search(tk, news_count=10).news or []
            rows = [_extract(a) for a in arts]
            rows = [r for r in rows if r['time_utc'] and r['title']]
        except Exception as e:
            print(f"  !! {tk}: {type(e).__name__} {e}", flush=True); rows = []
        out[tk] = rows
        if rows:
            n_with += 1
        if i % 25 == 0 or i == len(todo) - 1:
            json.dump(out, open(path, 'w'), indent=1)
            print(f"  ...{i+1}/{len(todo)} ({tk}: {len(rows)} art.)", flush=True)
        time.sleep(SLEEP)
    json.dump(out, open(path, 'w'), indent=1)
    tot = sum(len(v) for v in out.values())
    print(f"\n✅ [{day}] {len(out)} tickers, {sum(1 for v in out.values() if v)} avec news, "
          f"{tot} articles -> {path}", flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ET).date().isoformat())
    a = ap.parse_args()
    main(a.date)
