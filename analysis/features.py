#!/usr/bin/env python3
"""
Feature extraction for LONG trades.

Extracts features from raw price data for ML models.
Adapted for LONG (gap up, momentum) strategy.

Usage:
    python -m analysis.features
    python -m analysis.features --play momentum
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'

# Ensure directory exists
COMPUTED_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# FEATURE DEFINITIONS - LONG STRATEGY
# =============================================================================
# Features available at market open (9:30) - can use for ENTRY prediction
PRE_ENTRY_FEATURES = [
    # Gap (positive = gap UP)
    'gap_pct',
    'gap_category',  # small (4-10%), medium (10-20%), large (>20%)

    # Pre-market
    'pm_high_pct',   # PM high vs prev close
    'pm_low_pct',    # PM low vs prev close
    'pm_range_pct',  # PM range
    'pm_trend',      # up, down, flat
    'pm_volume',     # Absolute PM volume

    # Market context
    'fear_greed',
    'spy_change_pct',
    'vix_close',

    # Fundamentals
    'float_shares',
    'float_category',  # micro (<5M), low (<20M), medium (<100M), high
    'inst_pct',

    # Catalyst
    'has_catalyst',
    'catalyst_type',  # earnings, fda, contract, news, none

    # Volume
    'relative_volume',
    'volume_category',  # low (<2x), medium (2-5x), high (>5x)

    # Date
    'day_of_week',
    'is_monday',
    'is_friday',

    # Sector
    'sector',
    'industry',
]

# Features available during trade (after entry)
INTRADAY_FEATURES = [
    # Momentum
    'first_5min_pct',
    'first_15min_pct',
    'first_30min_pct',
    'first_hour_pct',

    # Direction
    'first_5min_direction',  # up, down, flat

    # Velocity
    'velocity_5min',   # %/min
    'velocity_15min',
    'velocity_30min',

    # VWAP
    'vs_vwap_pct',  # Price vs VWAP

    # Range
    'intraday_range_pct',
    'high_pct',
    'low_pct',
]


def calculate_gap_pct(open_price: float, prev_close: float) -> float:
    """Calculate gap percentage."""
    if prev_close is None or prev_close == 0:
        return 0.0
    return ((open_price - prev_close) / prev_close) * 100


def categorize_gap(gap_pct: float) -> str:
    """Categorize gap size."""
    if gap_pct < 4:
        return 'minimal'
    elif gap_pct < 10:
        return 'small'
    elif gap_pct < 20:
        return 'medium'
    else:
        return 'large'


def categorize_float(float_shares: float) -> str:
    """Categorize float size."""
    if float_shares is None:
        return 'unknown'
    float_m = float_shares / 1_000_000
    if float_m < 5:
        return 'micro'
    elif float_m < 20:
        return 'low'
    elif float_m < 100:
        return 'medium'
    else:
        return 'high'


def categorize_volume(rel_volume: float) -> str:
    """Categorize relative volume."""
    if rel_volume is None:
        return 'unknown'
    if rel_volume < 2:
        return 'low'
    elif rel_volume < 5:
        return 'medium'
    else:
        return 'high'


def calculate_pm_trend(pm_high_pct: float, pm_low_pct: float) -> str:
    """Determine pre-market trend."""
    if pm_high_pct is None or pm_low_pct is None:
        return 'unknown'

    # If high is significantly above low midpoint
    midpoint = (pm_high_pct + pm_low_pct) / 2
    if pm_high_pct > midpoint + 2:
        return 'up'
    elif pm_low_pct < midpoint - 2:
        return 'down'
    else:
        return 'flat'


def extract_features_from_row(row: pd.Series) -> Dict:
    """
    Extract features from a single trade row.

    Args:
        row: Series with trade data (Open, High, Low, Close, prev_close, etc.)

    Returns:
        Dict with extracted features
    """
    features = {}

    # Gap
    open_price = row.get('Open', row.get('open'))
    prev_close = row.get('prev_close')

    if open_price and prev_close:
        features['gap_pct'] = calculate_gap_pct(open_price, prev_close)
        features['gap_category'] = categorize_gap(features['gap_pct'])

    # Pre-market
    features['pm_high_pct'] = row.get('pm_high_pct')
    features['pm_low_pct'] = row.get('pm_low_pct')

    if features['pm_high_pct'] and features['pm_low_pct']:
        features['pm_range_pct'] = features['pm_high_pct'] - features['pm_low_pct']
        features['pm_trend'] = calculate_pm_trend(features['pm_high_pct'], features['pm_low_pct'])

    features['pm_volume'] = row.get('pm_volume')

    # Fundamentals
    features['float_shares'] = row.get('float', row.get('float_shares'))
    if features['float_shares']:
        features['float_category'] = categorize_float(features['float_shares'])

    features['inst_pct'] = row.get('inst_pct', row.get('institutional_pct'))

    # Volume
    features['relative_volume'] = row.get('rel_volume', row.get('relative_volume'))
    if features['relative_volume']:
        features['volume_category'] = categorize_volume(features['relative_volume'])

    # Market context
    features['fear_greed'] = row.get('fear_greed')
    features['spy_change_pct'] = row.get('spy_change_pct')
    features['vix_close'] = row.get('vix_close')

    # Catalyst
    features['has_catalyst'] = row.get('has_catalyst', 0)
    features['catalyst_type'] = row.get('catalyst_type', 'none')

    # Date
    date = row.get('Date', row.get('date'))
    if date:
        if isinstance(date, str):
            date = pd.to_datetime(date)
        features['day_of_week'] = date.dayofweek
        features['is_monday'] = 1 if date.dayofweek == 0 else 0
        features['is_friday'] = 1 if date.dayofweek == 4 else 0

    # Sector
    features['sector'] = row.get('sector')
    features['industry'] = row.get('industry')

    # Intraday (if available)
    high = row.get('High', row.get('high'))
    low = row.get('Low', row.get('low'))
    close = row.get('Close', row.get('close'))

    if open_price and high and low:
        features['high_pct'] = ((high - open_price) / open_price) * 100
        features['low_pct'] = ((low - open_price) / open_price) * 100
        features['intraday_range_pct'] = ((high - low) / open_price) * 100

    if open_price and close:
        features['close_pct'] = ((close - open_price) / open_price) * 100

    return features


def extract_features_from_csv(input_file: Path, output_file: Path):
    """
    Extract features from raw trade data CSV.

    Args:
        input_file: Path to raw CSV
        output_file: Path for output features CSV
    """
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} rows")

    # Extract features
    features_list = []
    for idx, row in df.iterrows():
        features = extract_features_from_row(row)
        features['ticker'] = row.get('Ticker', row.get('ticker'))
        features['date'] = row.get('Date', row.get('date'))
        features_list.append(features)

    # Create features dataframe
    features_df = pd.DataFrame(features_list)

    # Save
    features_df.to_csv(output_file, index=False)
    print(f"Saved {len(features_df)} rows to {output_file}")

    return features_df


def main():
    parser = argparse.ArgumentParser(description='Extract features for LONG trades')
    parser.add_argument('--input', type=str, help='Input CSV file')
    parser.add_argument('--output', type=str, help='Output features CSV')
    args = parser.parse_args()

    if args.input and args.output:
        extract_features_from_csv(Path(args.input), Path(args.output))
    else:
        print("Feature extraction module for LONG strategy")
        print("\nPRE-ENTRY FEATURES (available at 9:30):")
        for f in PRE_ENTRY_FEATURES[:10]:
            print(f"  - {f}")
        print(f"  ... and {len(PRE_ENTRY_FEATURES) - 10} more")

        print("\nINTRADAY FEATURES (available during trade):")
        for f in INTRADAY_FEATURES[:10]:
            print(f"  - {f}")


if __name__ == '__main__':
    main()
