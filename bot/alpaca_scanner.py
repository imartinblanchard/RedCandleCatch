#!/usr/bin/env python3
"""
Alpaca Scanner - SCAN source for the LONG (Gap & Go) strategy.

Drop-in alternative to the IBKR scan step in scanner.py. It replaces
`scan_ibkr_gainers()` and `fetch_premarket_data()` using Alpaca Market Data:

    - Screener / Market Movers  -> candidate universe (top gainers)
    - Snapshots                 -> price, prev close, day volume  -> gap %
    - Minute bars (SIP)         -> pre-market high / low / volume

It does NOT fetch fundamentals (Float / Inst% / Sector) - Alpaca has none.
Those still come from Finviz via scanner.fetch_finviz_data().

Usage:
    python -m bot.alpaca_scanner                 # scan top gainers ($1-$10)
    python -m bot.alpaca_scanner --ticker BZFD   # snapshot for one ticker
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
except Exception:  # pragma: no cover
    ET = timezone(timedelta(hours=-5))

import requests

from bot import config

# Warrior Trading price band (same as scanner.FilterCriteria)
MIN_PRICE = 1.0
MAX_PRICE = 10.0
MIN_DAY_VOLUME = 100_000
MARKET_OPEN = (9, 30)  # ET


def _headers() -> Dict[str, str]:
    if not config.ALPACA_API_KEY_ID or not config.ALPACA_API_SECRET_KEY:
        raise RuntimeError(
            "Alpaca keys missing. Copy .env.example to .env and fill in "
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY."
        )
    return {
        'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID,
        'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY,
    }


def _get(path: str, params: Optional[Dict] = None) -> Dict:
    url = f"{config.ALPACA_DATA_URL}{path}"
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_bars(path: str, params: Dict) -> Dict:
    """
    GET bars, preferring SIP (best quality) but falling back to IEX when the
    account is denied recent SIP data (403 on bars newer than ~15 min).
    """
    params = dict(params)
    params.setdefault('feed', config.ALPACA_HIST_FEED)
    try:
        return _get(path, params)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 403 \
                and params['feed'] != config.ALPACA_REALTIME_FEED:
            params['feed'] = config.ALPACA_REALTIME_FEED
            return _get(path, params)
        raise


# =============================================================================
# STEP 1 - SCAN: top gainers (replaces scan_ibkr_gainers)
# =============================================================================
def scan_alpaca_gainers(limit: int = 20) -> List[Dict]:
    """
    Return top gaining stocks in the $1-$10 band as [{'ticker', 'price'}, ...].

    Uses the Alpaca screener 'movers' endpoint for the candidate universe,
    then keeps only Warrior-Trading-priced names. Note: the movers gain is
    computed on the regular session; use fetch_snapshot_data() for the precise
    pre-market gap that analyze_stock() actually filters on.
    """
    data = _get('/v1beta1/screener/stocks/movers', {'top': 50})
    gainers = data.get('gainers', [])

    stocks = []
    for item in gainers:
        price = item.get('price')
        symbol = item.get('symbol')
        if price is None or symbol is None:
            continue
        if MIN_PRICE <= price <= MAX_PRICE:
            stocks.append({
                'ticker': symbol,
                'price': price,
                'movers_pct': item.get('percent_change'),
            })
        if len(stocks) >= limit:
            break
    return stocks


# =============================================================================
# STEP 2 - per-ticker data (replaces fetch_premarket_data)
# =============================================================================
def premarket_stats(ticker: str, day: Optional[datetime] = None) -> Dict:
    """
    High / low / volume of the pre-market session (04:00-09:30 ET) for `day`
    (defaults to today). Works for past dates via SIP historical bars, which is
    exactly what the checklist backfill needs.
    """
    day = (day or datetime.now(ET)).astimezone(ET)
    session_open = day.replace(hour=4, minute=0, second=0, microsecond=0)
    open_cut = day.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1],
                           second=0, microsecond=0)
    day_end = day.replace(hour=20, minute=0, second=0, microsecond=0)

    try:
        data = _get_bars(f'/v2/stocks/{ticker}/bars', {
            'timeframe': '1Min',
            'start': session_open.astimezone(timezone.utc).isoformat(),
            'end': day_end.astimezone(timezone.utc).isoformat(),
            'adjustment': 'raw',
            'limit': 1000,
        })
    except requests.HTTPError:
        return {}

    highs, lows, vol = [], [], 0
    for bar in data.get('bars') or []:
        ts = datetime.fromisoformat(bar['t'].replace('Z', '+00:00')).astimezone(ET)
        if not (session_open <= ts < open_cut):  # pre-market only
            continue
        highs.append(bar['h'])
        lows.append(bar['l'])
        vol += bar['v']

    if not highs:
        return {}
    return {'pm_high': max(highs), 'pm_low': min(lows), 'pm_volume': vol}


def fetch_snapshot_data(ticker: str) -> Dict:
    """
    Fetch price, previous close, day volume and pre-market stats for a ticker.

    Shape mirrors scanner.fetch_premarket_data() so analyze_stock() consumes it
    unchanged: {'price', 'prev_close', 'volume', 'pm_high', 'pm_low', 'pm_volume'}.
    """
    # Real-time snapshot must use IEX: this account is denied recent SIP data.
    try:
        snap = _get(f'/v2/stocks/{ticker}/snapshot',
                    {'feed': config.ALPACA_REALTIME_FEED})
    except requests.HTTPError as e:
        print(f"Alpaca snapshot error for {ticker}: {e}")
        return {}

    latest = snap.get('latestTrade') or {}
    daily = snap.get('dailyBar') or {}
    prev = snap.get('prevDailyBar') or {}

    price = latest.get('p') or daily.get('c')
    result = {
        'price': price,
        'prev_close': prev.get('c'),
        'volume': daily.get('v'),
    }
    result.update(premarket_stats(ticker))
    return result


# =============================================================================
# CLI
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description='Alpaca SCAN source (Gap & Go)')
    parser.add_argument('--ticker', type=str, help='Snapshot for one ticker')
    parser.add_argument('--limit', type=int, default=20, help='Max gainers')
    args = parser.parse_args()

    if args.ticker:
        data = fetch_snapshot_data(args.ticker)
        if not data:
            print(f"No data for {args.ticker}")
            sys.exit(1)
        prev = data.get('prev_close')
        price = data.get('price')
        gap = ((price - prev) / prev * 100) if (prev and price) else None
        print(f"\n{args.ticker}")
        print(f"  Price:      ${price}")
        print(f"  Prev close: ${prev}")
        print(f"  Gap:        {f'+{gap:.1f}%' if gap is not None else 'n/a'}")
        print(f"  Day volume: {data.get('volume')}")
        print(f"  PM high:    {data.get('pm_high')}")
        print(f"  PM low:     {data.get('pm_low')}")
        print(f"  PM volume:  {data.get('pm_volume')}")
        return

    print("\nScanning Alpaca top gainers ($1-$10)...\n")
    stocks = scan_alpaca_gainers(limit=args.limit)
    if not stocks:
        print("No candidates found.")
        return
    for s in stocks:
        pct = s.get('movers_pct')
        pct_str = f"+{pct:.1f}%" if pct is not None else "n/a"
        print(f"  {s['ticker']:6}  ${s['price']:<7.2f}  {pct_str}")


if __name__ == '__main__':
    main()
