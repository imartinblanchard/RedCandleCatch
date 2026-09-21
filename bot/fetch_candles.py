#!/usr/bin/env python3
"""
Fetch 5-minute candle data for stocks in the checklist.

This script should be run the day AFTER the stocks were added to the checklist.
It fetches historical 5-minute candle data from IBKR and saves to:
- data/long-prices.csv  (absolute OHLC prices)
- data/long-percent.csv (% change from open)

Usage:
    python -m bot.fetch_candles           # Fetch all pending from checklist
    python -m bot.fetch_candles --date 2025-05-28  # Fetch specific date
    python -m bot.fetch_candles --ticker AAPL      # Fetch specific ticker
    python -m bot.fetch_candles --dry-run          # Show what would be fetched
"""
import argparse
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
CHECKLIST_FILE = DATA_DIR / 'long-checklist.csv'
PRICES_FILE = DATA_DIR / 'long-prices.csv'
PERCENT_FILE = DATA_DIR / 'long-percent.csv'

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Try IBKR import
try:
    from ib_insync import IB, Stock
    HAS_IBKR = True
except ImportError:
    HAS_IBKR = False
    logger.warning("ib_insync not installed")


def fetch_candle_data(ticker: str, date_str: str) -> Optional[Dict]:
    """
    Fetch all 5-minute candle data from IBKR for a specific date.
    Returns PM (04:00-09:25), RTH (09:30-16:00), EH (16:00-20:00) candles.
    """
    if not HAS_IBKR:
        logger.error("IBKR not available")
        return None

    logger.info(f"Fetching candle data for {ticker} on {date_str}")

    ib = IB()
    try:
        client_id = random.randint(2000, 2999)
        ib.connect('127.0.0.1', 4001, clientId=client_id)
    except Exception as e:
        logger.error(f"Cannot connect to IBKR: {e}")
        return None

    contract = Stock(ticker, 'SMART', 'USD')
    ib.qualifyContracts(contract)

    date = datetime.strptime(date_str, '%Y-%m-%d')
    end_date = date + timedelta(days=1)
    end_str = end_date.strftime('%Y%m%d 00:00:00')

    # Fetch 5-minute bars with extended hours (04:00-20:00)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime=end_str,
        durationStr='1 D',
        barSizeSetting='5 mins',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1
    )

    # Fetch previous day close for Gap%
    prev_end_str = date.strftime('%Y%m%d 00:00:00')
    prev_bars = ib.reqHistoricalData(
        contract,
        endDateTime=prev_end_str,
        durationStr='1 D',
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )

    ib.disconnect()

    if not bars:
        logger.error(f"No data returned for {ticker}")
        return None

    prev_close = prev_bars[-1].close if prev_bars else None

    # Separate candles by time period
    pm_candles = []   # 04:00 - 09:25
    rth_candles = []  # 09:30 - 15:55
    eh_candles = []   # 16:00 - 19:55

    for bar in bars:
        bar_time = bar.date.strftime('%H:%M')
        candle = {
            'time': bar_time,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume,
        }

        if '04:00' <= bar_time < '09:30':
            pm_candles.append(candle)
        elif '09:30' <= bar_time < '16:00':
            rth_candles.append(candle)
        elif '16:00' <= bar_time < '20:00':
            eh_candles.append(candle)

    if not rth_candles:
        logger.error(f"No RTH candles for {ticker}")
        return None

    # Calculate summary stats
    open_price = rth_candles[0]['open']
    day_high = max(c['high'] for c in rth_candles)
    day_low = min(c['low'] for c in rth_candles)
    close_price = rth_candles[-1]['close']

    pm_high = max(c['high'] for c in pm_candles) if pm_candles else None
    pm_low = min(c['low'] for c in pm_candles) if pm_candles else None

    # Find time of high and low
    time_high = None
    time_low = None
    for c in rth_candles:
        if c['high'] == day_high and not time_high:
            time_high = c['time']
        if c['low'] == day_low and not time_low:
            time_low = c['time']

    # Calculate percentages
    gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close else None
    high_pct = ((day_high - open_price) / open_price) * 100
    low_pct = ((day_low - open_price) / open_price) * 100
    close_vs_open_pct = ((close_price - open_price) / open_price) * 100

    data = {
        'date': date_str,
        'ticker': ticker,
        'prev_close': prev_close,
        'gap_pct': round(gap_pct, 2) if gap_pct else None,
        'open': open_price,
        'high': day_high,
        'low': day_low,
        'close': close_price,
        'high_pct': round(high_pct, 2),
        'low_pct': round(low_pct, 2),
        'close_vs_open_pct': round(close_vs_open_pct, 2),
        'time_high': time_high,
        'time_low': time_low,
        'pm_high': pm_high,
        'pm_low': pm_low,
        'pm_candles': pm_candles,
        'rth_candles': rth_candles,
        'eh_candles': eh_candles,
    }

    logger.info(f"  Open: ${open_price:.2f}, High: {high_pct:.1f}%, Low: {low_pct:.1f}%")
    logger.info(f"  PM: {len(pm_candles)}, RTH: {len(rth_candles)}, EH: {len(eh_candles)} candles")

    return data


def update_prices_csv(data: Dict) -> bool:
    """Update the prices CSV with candle data (absolute OHLC)."""
    logger.info(f"Updating {PRICES_FILE.name}...")

    # Load or create
    if PRICES_FILE.exists():
        df = pd.read_csv(PRICES_FILE)
    else:
        df = pd.DataFrame()

    # Check if already exists
    if len(df) > 0:
        exists = ((df['Date'] == data['date']) & (df['Ticker'] == data['ticker'])).any()
        if exists:
            logger.info(f"  {data['ticker']} already exists for {data['date']}, skipping")
            return False

    # Build new row
    new_row = {
        'Date': data['date'],
        'Ticker': data['ticker'],
        'Gap%': data['gap_pct'] if data['gap_pct'] else '',
        'Open': data['open'],
        'High': data['high'],
        'Low': data['low'],
        'Close': data['close'],
        'TimeHigh': data['time_high'],
        'TimeLow': data['time_low'],
    }

    # Add PM candles (04:00-09:25)
    for candle in data['pm_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'PM_{time_str}_O'] = candle['open']
        new_row[f'PM_{time_str}_H'] = candle['high']
        new_row[f'PM_{time_str}_L'] = candle['low']
        new_row[f'PM_{time_str}_C'] = candle['close']

    # Add RTH candles (09:30-15:55)
    for candle in data['rth_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'{time_str}_O'] = candle['open']
        new_row[f'{time_str}_H'] = candle['high']
        new_row[f'{time_str}_L'] = candle['low']
        new_row[f'{time_str}_C'] = candle['close']

    # Add EH candles (16:00-19:55)
    for candle in data['eh_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'EH_{time_str}_O'] = candle['open']
        new_row[f'EH_{time_str}_H'] = candle['high']
        new_row[f'EH_{time_str}_L'] = candle['low']
        new_row[f'EH_{time_str}_C'] = candle['close']

    # Add row
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values('Date')
    df.to_csv(PRICES_FILE, index=False)

    logger.info(f"  Added to {PRICES_FILE.name}")
    return True


def update_percent_csv(data: Dict) -> bool:
    """Update the percent CSV with candle data (% from open)."""
    logger.info(f"Updating {PERCENT_FILE.name}...")

    # Load or create
    if PERCENT_FILE.exists():
        df = pd.read_csv(PERCENT_FILE)
    else:
        df = pd.DataFrame()

    # Check if already exists
    if len(df) > 0:
        exists = ((df['Date'] == data['date']) & (df['Ticker'] == data['ticker'])).any()
        if exists:
            logger.info(f"  {data['ticker']} already exists for {data['date']}, skipping")
            return False

    open_price = data['open']

    # Build new row
    new_row = {
        'Date': data['date'],
        'Ticker': data['ticker'],
        'Gap%': data['gap_pct'] if data['gap_pct'] else '',
        'High%': data['high_pct'],
        'Low%': data['low_pct'],
        'ClosevsOpen%': data['close_vs_open_pct'],
        'TimeHigh': data['time_high'],
        'TimeLow': data['time_low'],
    }

    # Add PM candles as percentages
    for candle in data['pm_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'PM_{time_str}_O'] = round(((candle['open'] - open_price) / open_price) * 100, 2)
        new_row[f'PM_{time_str}_H'] = round(((candle['high'] - open_price) / open_price) * 100, 2)
        new_row[f'PM_{time_str}_L'] = round(((candle['low'] - open_price) / open_price) * 100, 2)
        new_row[f'PM_{time_str}_C'] = round(((candle['close'] - open_price) / open_price) * 100, 2)

    # Add RTH candles as percentages
    for candle in data['rth_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'{time_str}_O'] = round(((candle['open'] - open_price) / open_price) * 100, 2)
        new_row[f'{time_str}_H'] = round(((candle['high'] - open_price) / open_price) * 100, 2)
        new_row[f'{time_str}_L'] = round(((candle['low'] - open_price) / open_price) * 100, 2)
        new_row[f'{time_str}_C'] = round(((candle['close'] - open_price) / open_price) * 100, 2)

    # Add EH candles as percentages
    for candle in data['eh_candles']:
        time_str = candle['time'].replace(':', '_')
        new_row[f'EH_{time_str}_O'] = round(((candle['open'] - open_price) / open_price) * 100, 2)
        new_row[f'EH_{time_str}_H'] = round(((candle['high'] - open_price) / open_price) * 100, 2)
        new_row[f'EH_{time_str}_L'] = round(((candle['low'] - open_price) / open_price) * 100, 2)
        new_row[f'EH_{time_str}_C'] = round(((candle['close'] - open_price) / open_price) * 100, 2)

    # Add row
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values('Date')
    df.to_csv(PERCENT_FILE, index=False)

    logger.info(f"  Added to {PERCENT_FILE.name}")
    return True


def get_pending_tickers() -> List[Dict]:
    """
    Get tickers from checklist that need candle data fetched.
    Excludes today's date (can only fetch after market close).
    """
    if not CHECKLIST_FILE.exists():
        logger.error(f"Checklist not found: {CHECKLIST_FILE}")
        return []

    checklist_df = pd.read_csv(CHECKLIST_FILE)
    today = datetime.now().strftime('%Y-%m-%d')

    # Exclude today
    checklist_df = checklist_df[checklist_df['Date'] != today]

    if len(checklist_df) == 0:
        logger.info("No tickers to fetch (all are from today)")
        return []

    # Check what's already in prices.csv
    fetched = set()
    if PRICES_FILE.exists():
        prices_df = pd.read_csv(PRICES_FILE)
        for _, row in prices_df.iterrows():
            fetched.add((row['Date'], row['Ticker']))

    # Filter to only pending
    pending = []
    for _, row in checklist_df.iterrows():
        key = (row['Date'], row['Ticker'])
        if key not in fetched:
            pending.append({
                'date': row['Date'],
                'ticker': row['Ticker'],
            })

    return pending


def main():
    parser = argparse.ArgumentParser(description='Fetch 5-min candle data for checklist stocks')
    parser.add_argument('--date', type=str, help='Fetch specific date (YYYY-MM-DD)')
    parser.add_argument('--ticker', type=str, help='Fetch specific ticker')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fetched')
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  LONG - Fetch 5-Min Candle Data")
    print("=" * 60)

    # Get pending tickers
    if args.ticker and args.date:
        # Single ticker/date
        pending = [{'date': args.date, 'ticker': args.ticker.upper()}]
    elif args.date:
        # All tickers for specific date
        pending = get_pending_tickers()
        pending = [p for p in pending if p['date'] == args.date]
    else:
        # All pending
        pending = get_pending_tickers()

    if not pending:
        print("\nNo tickers to fetch.")
        return

    print(f"\nPending: {len(pending)} ticker(s)")
    for p in pending:
        print(f"  {p['date']} - {p['ticker']}")

    if args.dry_run:
        print("\n(Dry run - no data fetched)")
        return

    # Fetch each ticker
    print("\n" + "-" * 60)
    success = 0
    failed = 0

    for p in pending:
        print(f"\n[{success + failed + 1}/{len(pending)}] {p['ticker']} ({p['date']})")

        data = fetch_candle_data(p['ticker'], p['date'])
        if data:
            update_prices_csv(data)
            update_percent_csv(data)
            success += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Done: {success} success, {failed} failed")
    print(f"Prices:  {PRICES_FILE}")
    print(f"Percent: {PERCENT_FILE}")


if __name__ == '__main__':
    main()
