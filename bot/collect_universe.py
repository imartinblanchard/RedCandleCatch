"""Capture LIVE de l'univers des gappers 5-500% (toute la séance), via le scanner IBKR.
On note CHAQUE gapper vu (ticker, bande de %-change, 1re fois vu), en direct, dans un fichier
STICKY par jour -> data/collected_live/universe-YYYY-MM-DD.json. Les BOUGIES 1-min sont tirées
ensuite (après clôture) par bot/fetch_universe_bars.py. But (Martin 23/09) : dataset LIVE fiable
(source IBKR), large (5-500), qu'on filtre à l'analyse. Le TRADING reste à gap 5-10.
"""
import os, json
from datetime import date as _date
from zoneinfo import ZoneInfo
from datetime import datetime

ET = ZoneInfo('America/New_York')
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'collected_live')
# bandes de %-change FINES dans le bas (dense) pour ne rater aucun gapper (top-50/bande sinon écrase)
BANDS = [(5, 7), (7, 10), (10, 14), (14, 20), (20, 30), (30, 50), (50, 100), (100, 500)]
ROWS = 50
PMIN, PMAX = 0.5, 50.0


def _path(day=None):
    d = day or datetime.now(ET).date().isoformat()
    return os.path.join(DIR, f'universe-{d}.json')


def scan_wide(broker):
    """Scans bandés TOP_PERC_GAIN -> {ticker: band} de tous les gappers 5-500%."""
    from ib_insync import ScannerSubscription, TagValue
    out = {}
    for lo, hi in BANDS:
        try:
            sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                                      scanCode='TOP_PERC_GAIN', numberOfRows=ROWS)
            sub.abovePrice = PMIN; sub.belowPrice = PMAX
            filt = [TagValue('changePercAbove', str(lo)), TagValue('changePercBelow', str(hi))]
            rows = broker.ib.reqScannerData(sub, [], filt)
            for r in rows:
                tk = r.contractDetails.contract.symbol
                if '.' in tk or '/' in tk:
                    continue
                out.setdefault(tk, f'{lo}-{hi}')
        except Exception as e:
            print(f"    [univers] scan {lo}-{hi} err: {e}")
    return out


def record(broker, day=None):
    """Scanne + MERGE STICKY dans le fichier univers du jour. Retourne (n_nouveaux, n_total)."""
    try:
        os.makedirs(DIR, exist_ok=True)
        seen = scan_wide(broker)
        p = _path(day)
        d = json.load(open(p)) if os.path.exists(p) else {}
        now = datetime.now(ET).strftime('%H:%M')
        added = 0
        for tk, band in seen.items():
            if tk not in d:
                d[tk] = {'first_seen': now, 'band': band}; added += 1
            else:
                d[tk]['last_seen'] = now      # trace de présence
        if added or not os.path.exists(p):
            json.dump(d, open(p, 'w'), indent=2)
        return added, len(d)
    except Exception as e:
        print(f"    [univers] record err: {e}")
        return 0, 0


def load(day=None):
    p = _path(day)
    return json.load(open(p)) if os.path.exists(p) else {}
