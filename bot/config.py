#!/usr/bin/env python3
"""
Configuration for the LONG trading bot.

Based on Warrior Trading Gap & Go strategy criteria.
"""
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'
CREDENTIALS_DIR = PROJECT_ROOT / 'credentials'

# Account settings
ACCOUNT_SIZE = 25000  # USD
MAX_RISK_PER_TRADE = 0.02  # 2% (tighter for long)
MAX_POSITION_SIZE = 0.20  # 20% max per position

# IBKR Connection (same TWS, different client IDs)
IBKR_HOST = '127.0.0.1'
IBKR_PORT_LIVE = 4001
IBKR_PORT_PAPER = 4002
IBKR_CLIENT_ID = 30  # For bot (different from short journal: 10, 20)

# Alpaca Market Data (alternative SCAN source, coexists with IBKR)
# Keys are read from environment / .env file (see .env.example), never hardcoded.
import os as _os


def _load_dotenv():
    """Minimal .env loader (no external dependency)."""
    env_path = PROJECT_ROOT / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        _os.environ.setdefault(key, value)


_load_dotenv()

ALPACA_API_KEY_ID = _os.environ.get('ALPACA_API_KEY_ID', '')
ALPACA_API_SECRET_KEY = _os.environ.get('ALPACA_API_SECRET_KEY', '')
ALPACA_DATA_URL = 'https://data.alpaca.markets'

# This account has SIP for HISTORICAL bars (>15 min old) but NOT recent/real-time
# SIP (returns 403 "subscription does not permit querying recent SIP data").
# So: historical backfill uses SIP; live/real-time queries must use IEX.
ALPACA_HIST_FEED = _os.environ.get('ALPACA_DATA_FEED', 'sip')  # historical bars
ALPACA_REALTIME_FEED = _os.environ.get('ALPACA_REALTIME_FEED', 'iex')  # snapshots/latest

# Webhook Discord (optionnel) : notifie les entrées/sorties du terminator.
# Créer un salon Discord -> Intégrations -> Webhooks -> copier l'URL dans .env :
#   DISCORD_WEBHOOK=https://discord.com/api/webhooks/....
DISCORD_WEBHOOK = _os.environ.get('DISCORD_WEBHOOK', '')

# Direction - LONG strategy
DIRECTION = 'long'

# Strategies configuration - LONG (entry on breakout, stop below low)
STRATEGIES = {
    'momentum': {
        'name': 'Momentum',
        'entry': 'breakout',  # Entry on PM high break
        'stop_loss': 10,  # % below entry (tight)
        'take_profit': 20,  # 2:1 risk/reward
        'exit_type': 'TARGET_OR_EOD',
        'sizing': 0.10,  # 10% of account
    },
    'pullback': {
        'name': 'Pullback',
        'entry': 'pullback',  # Entry on pullback to VWAP
        'stop_loss': 5,  # % below entry
        'take_profit': 10,  # 2:1 risk/reward
        'exit_type': 'TARGET_OR_EOD',
        'sizing': 0.10,
    },
}

# ML Model settings
ML_CONFIG = {
    'model_type': 'random_forest',
    'test_size': 0.2,
    'random_state': 42,
    'n_estimators': 100,
    'max_depth': 10,
    'min_samples_split': 5,
}

# Feature columns for LONG ML (to be refined)
FEATURE_COLUMNS = [
    # Gap features
    'gap_pct',
    # Pre-market features
    'pm_high_pct',
    'pm_low_pct',
    'pm_range_pct',
    'pm_volume',
    # Momentum features
    'first_5min_pct',
    'first_15min_pct',
    'first_30min_pct',
    # Market context
    'fear_greed',
    'spy_change_pct',
    'vix_close',
    # Volume
    'relative_volume',
    # Date features
    'day_of_week',
    'is_monday',
    'is_friday',
]

# Categorical features (need encoding)
CATEGORICAL_FEATURES = [
    'gap_category',
    'pm_trend',
    'first_5min_direction',
    'float_category',
    'sector',
]

# Target variable
TARGET_COLUMN = 'win'  # 1 if trade was profitable (price went UP), 0 otherwise

# Alert thresholds
ALERT_CONFIG = {
    'min_win_probability': 0.60,  # Alert if P(win) >= 60%
    'min_confidence': 0.65,
}

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = PROJECT_ROOT / 'bot' / 'bot.log'
