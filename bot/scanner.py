#!/usr/bin/env python3
"""
Stock Scanner - LONG Strategy (Gap & Go)

Based on Warrior Trading criteria:
1. SCAN    - Fetch IBKR Top % Gainers
2. FILTER  - Apply criteria (price, gap, float, volume)
3. ANALYZE - Score and rank opportunities
4. OUTPUT  - Recommendations with sizing

Criteria (Warrior Trading):
- Gap: +4% to +50% (gapping UP)
- Price: $1 to $10 (small caps)
- Float: < 20M ideal, max 100M
- Relative Volume: 2x+ (3x ideal)
- PM Volume: > 500K
- News/Catalyst: Preferred

Usage:
    python -m bot.scanner                    # Full scan
    python -m bot.scanner --ticker BZFD      # Single ticker analysis
    python -m bot.scanner --no-ibkr          # Manual input mode
"""
import argparse
import logging
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np

# Suppress IBKR debug output
logging.getLogger('ib_insync').setLevel(logging.CRITICAL)
logging.getLogger('ib_insync.wrapper').setLevel(logging.CRITICAL)
logging.getLogger('ib_insync.client').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore')

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'

# Try imports
try:
    from ib_insync import IB, Stock, ScannerSubscription
    HAS_IBKR = True
except ImportError:
    HAS_IBKR = False
    print("Warning: ib_insync not installed")

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# FILTER CRITERIA - WARRIOR TRADING GAP & GO (LONG)
# =============================================================================
@dataclass
class FilterCriteria:
    """Criteria for filtering stocks - LONG strategy."""
    # Price (small caps)
    min_price: float = 1.00           # Minimum $1
    max_price: float = 10.0           # Maximum $10

    # Gap - POSITIVE gap (gapping UP)
    min_gap_pct: float = 4.0          # Minimum +4% gap
    max_gap_pct: float = 50.0         # Maximum +50% gap (avoid parabolic)

    # Float (low float = more volatile)
    min_float: float = 500_000        # 500K minimum
    max_float: float = 20_000_000     # 20M ideal max
    max_float_extended: float = 100_000_000  # 100M absolute max

    # Volume
    min_pm_volume: int = 500_000      # 500K PM volume minimum
    min_relative_volume: float = 2.0  # 2x relative volume
    ideal_relative_volume: float = 3.0  # 3x is ideal

    # Institutional
    max_inst_pct: float = 30.0        # Max 30% institutional

    # Trading
    entry_type: str = 'breakout'      # 'breakout' or 'pullback'
    stop_type: str = 'below_low'      # Stop below pre-market low


DEFAULT_CRITERIA = FilterCriteria()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def calculate_gap_pct(current_price: float, prev_close: float) -> float:
    """Calculate gap percentage (positive = gap UP)."""
    if prev_close is None or prev_close == 0:
        return 0.0
    return ((current_price - prev_close) / prev_close) * 100


def fetch_finviz_data(ticker: str) -> Dict:
    """Fetch fundamental data from Finviz."""
    if not HAS_REQUESTS:
        return {}

    try:
        url = f'https://finviz.com/quote.ashx?t={ticker}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code != 200:
            return {}

        soup = BeautifulSoup(response.text, 'html.parser')
        data = {}

        # Parse table
        table = soup.find('table', class_='snapshot-table2')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for i in range(0, len(cells) - 1, 2):
                    label = cells[i].text.strip()
                    value = cells[i + 1].text.strip()
                    data[label] = value

        # Extract key fields
        result = {}

        # Float
        if 'Shs Float' in data:
            float_str = data['Shs Float']
            if 'M' in float_str:
                result['float'] = float(float_str.replace('M', '')) * 1_000_000
            elif 'B' in float_str:
                result['float'] = float(float_str.replace('B', '')) * 1_000_000_000
            elif 'K' in float_str:
                result['float'] = float(float_str.replace('K', '')) * 1_000

        # Institutional %
        if 'Inst Own' in data:
            inst_str = data['Inst Own'].replace('%', '')
            if inst_str != '-':
                result['inst_pct'] = float(inst_str)

        # Sector
        if 'Sector' in data:
            result['sector'] = data['Sector']

        # Industry
        if 'Industry' in data:
            result['industry'] = data['Industry']

        # Relative Volume
        if 'Rel Volume' in data:
            rel_vol = data['Rel Volume']
            if rel_vol != '-':
                result['rel_volume'] = float(rel_vol)

        return result

    except Exception as e:
        print(f"Error fetching Finviz data for {ticker}: {e}")
        return {}


def fetch_news_headlines(ticker: str) -> List[Dict]:
    """Fetch recent news headlines from Finviz."""
    if not HAS_REQUESTS:
        return []

    try:
        url = f'https://finviz.com/quote.ashx?t={ticker}'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        news_table = soup.find('table', id='news-table')

        if not news_table:
            return []

        headlines = []
        rows = news_table.find_all('tr')[:5]  # Last 5 headlines

        for row in rows:
            link = row.find('a')
            if link:
                headlines.append({
                    'title': link.text.strip(),
                    'url': link.get('href', ''),
                })

        return headlines

    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        return []


def classify_catalyst(headlines: List[Dict]) -> str:
    """Classify catalyst type from headlines."""
    if not headlines:
        return 'none'

    text = ' '.join([h['title'].lower() for h in headlines])

    # Keywords for catalyst types
    if any(w in text for w in ['earnings', 'revenue', 'profit', 'eps', 'quarterly']):
        return 'earnings'
    elif any(w in text for w in ['fda', 'approval', 'drug', 'trial', 'clinical']):
        return 'fda'
    elif any(w in text for w in ['contract', 'deal', 'partnership', 'agreement']):
        return 'contract'
    elif any(w in text for w in ['merger', 'acquisition', 'buyout', 'takeover']):
        return 'merger'
    elif any(w in text for w in ['offering', 'dilution', 'raise', 'shares']):
        return 'offering'
    elif any(w in text for w in ['upgrade', 'downgrade', 'analyst', 'target']):
        return 'analyst'

    return 'news'


# =============================================================================
# STOCK ANALYSIS
# =============================================================================
def analyze_stock(
    ticker: str,
    price: float,
    prev_close: float,
    pm_high: float = None,
    pm_low: float = None,
    pm_volume: int = None,
    criteria: FilterCriteria = DEFAULT_CRITERIA,
) -> Dict:
    """
    Analyze a stock for LONG opportunity.

    Returns dict with:
    - status: 'ENTER', 'WATCH', 'SKIP'
    - score: 0-100
    - reasons: list of reasons
    - entry_price: suggested entry
    - stop_price: suggested stop
    - target_price: suggested target
    """
    result = {
        'ticker': ticker,
        'price': price,
        'prev_close': prev_close,
        'status': 'SKIP',
        'score': 0,
        'reasons': [],
        'filters_passed': [],
        'filters_failed': [],
    }

    # Calculate gap
    gap_pct = calculate_gap_pct(price, prev_close)
    result['gap_pct'] = round(gap_pct, 1)

    # Fetch additional data
    finviz_data = fetch_finviz_data(ticker)
    result['float'] = finviz_data.get('float')
    result['inst_pct'] = finviz_data.get('inst_pct')
    result['sector'] = finviz_data.get('sector')
    result['rel_volume'] = finviz_data.get('rel_volume')

    # Fetch news
    headlines = fetch_news_headlines(ticker)
    result['headlines'] = headlines
    result['catalyst'] = classify_catalyst(headlines)

    # ==========================================================================
    # FILTER CHECKS
    # ==========================================================================
    score = 0

    # 1. Price check ($1-$10)
    if criteria.min_price <= price <= criteria.max_price:
        result['filters_passed'].append(f"Price ${price:.2f} in range")
        score += 10
    else:
        result['filters_failed'].append(f"Price ${price:.2f} out of range (${criteria.min_price}-${criteria.max_price})")

    # 2. Gap check (positive, +4% to +50%)
    if gap_pct >= criteria.min_gap_pct:
        if gap_pct <= criteria.max_gap_pct:
            result['filters_passed'].append(f"Gap +{gap_pct:.1f}% in range")
            score += 20
            if gap_pct >= 10:
                score += 10  # Bonus for strong gap
        else:
            result['filters_failed'].append(f"Gap +{gap_pct:.1f}% too high (max {criteria.max_gap_pct}%)")
    else:
        result['filters_failed'].append(f"Gap +{gap_pct:.1f}% too low (min {criteria.min_gap_pct}%)")

    # 3. Float check (< 20M ideal)
    if result['float']:
        float_m = result['float'] / 1_000_000
        if result['float'] <= criteria.max_float:
            result['filters_passed'].append(f"Float {float_m:.1f}M (low, ideal)")
            score += 20
        elif result['float'] <= criteria.max_float_extended:
            result['filters_passed'].append(f"Float {float_m:.1f}M (acceptable)")
            score += 10
        else:
            result['filters_failed'].append(f"Float {float_m:.1f}M too high (max {criteria.max_float_extended/1e6:.0f}M)")

    # 4. Relative Volume check (2x+)
    if result['rel_volume']:
        if result['rel_volume'] >= criteria.ideal_relative_volume:
            result['filters_passed'].append(f"Rel Vol {result['rel_volume']:.1f}x (ideal)")
            score += 20
        elif result['rel_volume'] >= criteria.min_relative_volume:
            result['filters_passed'].append(f"Rel Vol {result['rel_volume']:.1f}x (good)")
            score += 10
        else:
            result['filters_failed'].append(f"Rel Vol {result['rel_volume']:.1f}x too low (min {criteria.min_relative_volume}x)")

    # 5. PM Volume check (500K+)
    if pm_volume:
        if pm_volume >= criteria.min_pm_volume:
            result['filters_passed'].append(f"PM Vol {pm_volume/1000:.0f}K (good)")
            score += 10
        else:
            result['filters_failed'].append(f"PM Vol {pm_volume/1000:.0f}K too low (min {criteria.min_pm_volume/1000:.0f}K)")

    # 6. Catalyst bonus
    if result['catalyst'] != 'none':
        result['filters_passed'].append(f"Catalyst: {result['catalyst']}")
        score += 10

    # 7. Institutional check
    if result['inst_pct'] is not None:
        if result['inst_pct'] <= criteria.max_inst_pct:
            result['filters_passed'].append(f"Inst {result['inst_pct']:.0f}% OK")
        else:
            result['filters_failed'].append(f"Inst {result['inst_pct']:.0f}% high (max {criteria.max_inst_pct}%)")
            score -= 10

    # ==========================================================================
    # FINAL SCORING
    # ==========================================================================
    result['score'] = max(0, min(100, score))

    # Determine status
    if len(result['filters_failed']) == 0 and score >= 60:
        result['status'] = 'ENTER'
    elif gap_pct >= criteria.min_gap_pct and score >= 40:
        result['status'] = 'WATCH'
    else:
        result['status'] = 'SKIP'

    # Calculate entry/stop/target
    if pm_high and pm_low:
        result['entry_price'] = pm_high  # Break above PM high
        result['stop_price'] = pm_low * 0.98  # 2% below PM low

        risk = result['entry_price'] - result['stop_price']
        result['target_price'] = result['entry_price'] + (risk * 2)  # 2:1 R/R
        result['risk_pct'] = (risk / result['entry_price']) * 100

    return result


# =============================================================================
# IBKR SCANNER
# =============================================================================
def scan_ibkr_gainers(limit: int = 20) -> List[Dict]:
    """Scan IBKR for top gainers."""
    if not HAS_IBKR:
        print("IBKR not available")
        return []

    import random
    ib = IB()
    try:
        client_id = random.randint(3000, 3999)
        ib.connect('127.0.0.1', 4001, clientId=client_id)

        # Create scanner for top gainers
        sub = ScannerSubscription(
            instrument='STK',
            locationCode='STK.US.MAJOR',
            scanCode='TOP_PERC_GAIN',
        )

        # Add filters
        sub.abovePrice = 1.0
        sub.belowPrice = 10.0
        sub.aboveVolume = 100000

        results = ib.reqScannerData(sub)

        stocks = []
        for item in results[:limit]:
            contract = item.contractDetails.contract
            stocks.append({
                'ticker': contract.symbol,
                'price': item.marketData.last if hasattr(item, 'marketData') else None,
            })

        ib.disconnect()
        return stocks

    except Exception as e:
        print(f"IBKR scan error: {e}")
        if ib.isConnected():
            ib.disconnect()
        return []


def fetch_premarket_data(ticker: str) -> Dict:
    """Fetch pre-market data from IBKR."""
    if not HAS_IBKR:
        return {}

    import random
    ib = IB()
    try:
        client_id = random.randint(3000, 3999)
        ib.connect('127.0.0.1', 4001, clientId=client_id)

        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # Request market data
        ticker_data = ib.reqMktData(contract, '', False, False)
        ib.sleep(2)  # Wait for data

        data = {
            'price': ticker_data.last,
            'bid': ticker_data.bid,
            'ask': ticker_data.ask,
            'volume': ticker_data.volume,
        }

        # Request historical data for prev close
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='2 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
        )

        if bars:
            data['prev_close'] = bars[-1].close

        ib.disconnect()
        return data

    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        if ib.isConnected():
            ib.disconnect()
        return {}


# =============================================================================
# POSITION SIZING
# =============================================================================
def calculate_sizing(
    account_size: float,
    entry_price: float,
    stop_price: float,
    max_risk_pct: float = 2.0,  # 2% risk per trade
    max_position_pct: float = 20.0,  # 20% max position
) -> Dict:
    """
    Calculate position sizing based on risk.

    Risk-based sizing:
    - Risk amount = account * max_risk_pct
    - Position = risk_amount / (entry - stop)
    """
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return {
            'error': 'Invalid stop price',
            'shares': 0,
            'position_size': 0,
        }

    risk_amount = account_size * (max_risk_pct / 100)
    max_position = account_size * (max_position_pct / 100)

    # Shares based on risk
    shares = int(risk_amount / risk_per_share)
    position_size = shares * entry_price

    # Cap at max position
    if position_size > max_position:
        shares = int(max_position / entry_price)
        position_size = shares * entry_price

    return {
        'shares': shares,
        'position_size': round(position_size, 2),
        'position_pct': round((position_size / account_size) * 100, 1),
        'risk_amount': round(shares * risk_per_share, 2),
        'risk_pct': round((shares * risk_per_share / account_size) * 100, 2),
    }


# =============================================================================
# MAIN
# =============================================================================
def run_scan(criteria: FilterCriteria = DEFAULT_CRITERIA) -> List[Dict]:
    """Run full scan."""
    print("\n" + "=" * 60)
    print("  LONG SCANNER - Gap & Go Strategy")
    print("=" * 60)

    # Scan for gainers
    print("\n[1/3] Scanning IBKR for top gainers...")
    stocks = scan_ibkr_gainers()

    if not stocks:
        print("No stocks found from IBKR scan")
        return []

    print(f"Found {len(stocks)} candidates")

    # Analyze each stock
    print("\n[2/3] Analyzing stocks...")
    results = []

    for stock in stocks:
        ticker = stock['ticker']
        print(f"  Analyzing {ticker}...")

        # Fetch pre-market data
        pm_data = fetch_premarket_data(ticker)
        if not pm_data.get('price'):
            continue

        # Analyze
        analysis = analyze_stock(
            ticker=ticker,
            price=pm_data['price'],
            prev_close=pm_data.get('prev_close'),
            pm_volume=pm_data.get('volume'),
            criteria=criteria,
        )

        results.append(analysis)

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    # Output
    print("\n[3/3] Results:")
    print("-" * 60)

    for r in results:
        status_color = {
            'ENTER': '\033[92m',  # Green
            'WATCH': '\033[93m',  # Yellow
            'SKIP': '\033[90m',   # Gray
        }.get(r['status'], '')
        reset = '\033[0m'

        print(f"{status_color}{r['status']:6}{reset} {r['ticker']:6} "
              f"Gap: +{r['gap_pct']:5.1f}%  Score: {r['score']:3}  "
              f"Catalyst: {r.get('catalyst', 'none')}")

    return results


def analyze_single(ticker: str, no_ibkr: bool = False) -> Dict:
    """Analyze a single ticker."""
    print(f"\n{'=' * 60}")
    print(f"  ANALYZING: {ticker}")
    print(f"{'=' * 60}")

    if no_ibkr:
        # Manual input
        price = float(input(f"Current price for {ticker}: $"))
        prev_close = float(input(f"Previous close for {ticker}: $"))
        pm_high = float(input(f"Pre-market high (0 if unknown): $") or 0) or None
        pm_low = float(input(f"Pre-market low (0 if unknown): $") or 0) or None
        pm_volume = int(input(f"Pre-market volume (0 if unknown): ") or 0) or None
    else:
        # Fetch from IBKR
        pm_data = fetch_premarket_data(ticker)
        price = pm_data.get('price')
        prev_close = pm_data.get('prev_close')
        pm_high = None  # Would need intraday bars
        pm_low = None
        pm_volume = pm_data.get('volume')

        if not price:
            print(f"Could not fetch data for {ticker}")
            return {}

    # Analyze
    result = analyze_stock(
        ticker=ticker,
        price=price,
        prev_close=prev_close,
        pm_high=pm_high,
        pm_low=pm_low,
        pm_volume=pm_volume,
    )

    # Print results
    print(f"\n{'=' * 40}")
    print(f"Status: {result['status']} (Score: {result['score']})")
    print(f"{'=' * 40}")

    print(f"\nPrice: ${result['price']:.2f}")
    print(f"Gap: +{result['gap_pct']:.1f}%")

    if result.get('float'):
        print(f"Float: {result['float']/1e6:.1f}M")
    if result.get('rel_volume'):
        print(f"Rel Volume: {result['rel_volume']:.1f}x")
    if result.get('catalyst'):
        print(f"Catalyst: {result['catalyst']}")

    print(f"\n{'+' * 40}")
    print("PASSED:")
    for f in result['filters_passed']:
        print(f"  + {f}")

    if result['filters_failed']:
        print(f"\n{'-' * 40}")
        print("FAILED:")
        for f in result['filters_failed']:
            print(f"  - {f}")

    # Entry/Stop/Target
    if result.get('entry_price'):
        print(f"\n{'$' * 40}")
        print("TRADE PLAN:")
        print(f"  Entry:  ${result['entry_price']:.2f} (break PM high)")
        print(f"  Stop:   ${result['stop_price']:.2f}")
        print(f"  Target: ${result['target_price']:.2f} (2:1 R/R)")
        print(f"  Risk:   {result.get('risk_pct', 0):.1f}%")

    # Headlines
    if result.get('headlines'):
        print(f"\n{'#' * 40}")
        print("RECENT NEWS:")
        for h in result['headlines'][:3]:
            print(f"  - {h['title'][:60]}...")

    return result


def main():
    parser = argparse.ArgumentParser(description='LONG Scanner - Gap & Go Strategy')
    parser.add_argument('--ticker', type=str, help='Analyze single ticker')
    parser.add_argument('--no-ibkr', action='store_true', help='Manual input mode')
    parser.add_argument('--min-gap', type=float, default=4.0, help='Minimum gap %')
    parser.add_argument('--max-gap', type=float, default=50.0, help='Maximum gap %')
    args = parser.parse_args()

    criteria = FilterCriteria(
        min_gap_pct=args.min_gap,
        max_gap_pct=args.max_gap,
    )

    if args.ticker:
        analyze_single(args.ticker, no_ibkr=args.no_ibkr)
    else:
        run_scan(criteria)


if __name__ == '__main__':
    main()
