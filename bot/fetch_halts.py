#!/usr/bin/env python3
"""Capture les ARRÊTS DE COTATION (trade halts) Nasdaq du jour — le driver hors-prix n°1
des gros gaps (>=30%). Flux RSS market-wide NasdaqTrader (LULD volatilité + news pending/released
+ halts réglementaires). Un seul appel, pas besoin d'IBKR.

⚠️ Flux GLISSANT (~2-3 derniers jours) : à lancer LE JOUR MÊME (comme fetch_universe_news /
fetch_pm15s). La donnée s'accumule FORWARD — on ne reconstruit PAS le passé (les séances déjà
collectées resteront sans halts, c'est assumé). Idempotent : re-lançable, merge + dédup.

Sortie : data/collected_live/halts-YYYY-MM-DD.json
  { ticker: [ {halt_time, reason, resume_date, resume_quote_time, resume_trade_time,
               market, name, pause_price}, ... ] }
On ne garde QUE les halts dont la HaltDate == le jour cible. Market-wide (pas filtré à notre
univers) : un gappeur halté peut ne pas être dans l'univers capté et rester pertinent ;
le build_features joindra plus tard sur (date, ticker).

Usage : python -m bot.fetch_halts                 (jour courant)
        python -m bot.fetch_halts --date 2026-11-07
"""
import os, sys, json, argparse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot.collect_universe as cu

TZ = ZoneInfo('America/New_York')
DIR = cu.DIR
FEED = 'http://www.nasdaqtrader.com/rss.aspx?feed=tradehalts'
NS = {'ndaq': 'http://www.nasdaqtrader.com/'}


def _txt(item, tag):
    el = item.find(f'ndaq:{tag}', NS)
    return (el.text or '').strip() if el is not None and el.text else ''


def _iso_date(mdy):
    """'11/06/2026' -> '2026-11-06' (ou '' si vide/illisible)."""
    try:
        return datetime.strptime(mdy, '%m/%d/%Y').date().isoformat()
    except ValueError:
        return ''


def fetch_feed():
    req = urllib.request.Request(FEED, headers={'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=30).read()
    root = ET.fromstring(raw)
    return root.findall('.//item')


def main(day):
    items = fetch_feed()
    path = os.path.join(DIR, f'halts-{day}.json')
    out = json.load(open(path)) if os.path.exists(path) else {}
    seen = {(tk, h['halt_time']) for tk, hs in out.items() for h in hs}  # dédup
    added = 0
    for it in items:
        if _iso_date(_txt(it, 'HaltDate')) != day:
            continue
        tk = _txt(it, 'IssueSymbol')
        ht = _txt(it, 'HaltTime')
        if not tk or (tk, ht) in seen:
            continue
        out.setdefault(tk, []).append({
            'halt_time': ht,                                   # HH:MM:SS.mmm ET
            'reason': _txt(it, 'ReasonCode'),                  # T1/T2 news, LUDP volatilité, H10 SEC…
            'resume_date': _iso_date(_txt(it, 'ResumptionDate')),
            'resume_quote_time': _txt(it, 'ResumptionQuoteTime'),
            'resume_trade_time': _txt(it, 'ResumptionTradeTime'),
            'market': _txt(it, 'Market'),
            'name': _txt(it, 'IssueName'),
            'pause_price': _txt(it, 'PauseThresholdPrice'),
        })
        seen.add((tk, ht))
        added += 1
    os.makedirs(DIR, exist_ok=True)
    json.dump(out, open(path, 'w'), indent=1)
    print(f"✅ [{day}] {len(items)} halts dans le flux | {added} nouveaux ce run | "
          f"{len(out)} tickers haltés, {sum(len(v) for v in out.values())} halts -> {path}",
          flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(TZ).date().isoformat())
    a = ap.parse_args()
    main(a.date)
