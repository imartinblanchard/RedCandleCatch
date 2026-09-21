#!/usr/bin/env python3
"""
ML Signals for LONG positions.

Monitors active positions and provides HOLD/EXIT signals based on:
- Price action vs entry
- Target reached
- Stop hit
- Time-based exit (EOD)

Usage:
    python -m bot.signals --add BZFD 5.50     # Add position
    python -m bot.signals --remove BZFD       # Remove position
    python -m bot.signals --check BZFD        # Check position
    python -m bot.signals --list              # List all positions
    python -m bot.signals --start             # Start monitoring
"""
import argparse
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'
POSITIONS_FILE = COMPUTED_DIR / 'active-positions.json'

# Ensure directory exists
COMPUTED_DIR.mkdir(parents=True, exist_ok=True)

# Try IBKR import
try:
    from ib_insync import IB, Stock
    HAS_IBKR = True
except ImportError:
    HAS_IBKR = False


@dataclass
class Position:
    """Active position."""
    ticker: str
    entry_price: float
    stop_price: float
    target_price: float
    entry_time: str
    shares: int = 0
    status: str = 'active'  # active, closed

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        return cls(**data)


class SignalManager:
    """Manages positions and generates signals."""

    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.ib = None
        self.load_positions()

    def load_positions(self):
        """Load positions from file."""
        if POSITIONS_FILE.exists():
            try:
                with open(POSITIONS_FILE) as f:
                    data = json.load(f)
                    self.positions = {
                        k: Position.from_dict(v)
                        for k, v in data.items()
                    }
            except Exception as e:
                print(f"Error loading positions: {e}")

    def save_positions(self):
        """Save positions to file."""
        try:
            with open(POSITIONS_FILE, 'w') as f:
                data = {k: v.to_dict() for k, v in self.positions.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving positions: {e}")

    def add_position(
        self,
        ticker: str,
        entry_price: float,
        stop_price: float = None,
        target_price: float = None,
        shares: int = 0,
    ):
        """Add a new position."""
        # Default stop: 10% below entry
        if stop_price is None:
            stop_price = entry_price * 0.90

        # Default target: 2:1 R/R
        if target_price is None:
            risk = entry_price - stop_price
            target_price = entry_price + (risk * 2)

        position = Position(
            ticker=ticker.upper(),
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            entry_time=datetime.now().isoformat(),
            shares=shares,
        )

        self.positions[ticker.upper()] = position
        self.save_positions()

        print(f"Added position: {ticker.upper()}")
        print(f"  Entry:  ${entry_price:.2f}")
        print(f"  Stop:   ${stop_price:.2f} ({(1 - stop_price/entry_price) * 100:.1f}% risk)")
        print(f"  Target: ${target_price:.2f} ({(target_price/entry_price - 1) * 100:.1f}% gain)")

    def remove_position(self, ticker: str):
        """Remove a position."""
        ticker = ticker.upper()
        if ticker in self.positions:
            del self.positions[ticker]
            self.save_positions()
            print(f"Removed position: {ticker}")
        else:
            print(f"Position not found: {ticker}")

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price from IBKR."""
        if not HAS_IBKR:
            return None

        try:
            if not self.ib or not self.ib.isConnected():
                import random
                self.ib = IB()
                client_id = random.randint(3000, 3999)
                self.ib.connect('127.0.0.1', 4001, clientId=client_id)

            contract = Stock(ticker, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            ticker_data = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(1)

            return ticker_data.last

        except Exception as e:
            print(f"Error getting price for {ticker}: {e}")
            return None

    def check_position(self, ticker: str, current_price: float = None) -> Dict:
        """Check a position and generate signal."""
        ticker = ticker.upper()

        if ticker not in self.positions:
            return {'error': f'Position not found: {ticker}'}

        pos = self.positions[ticker]

        # Get current price
        if current_price is None:
            current_price = self.get_current_price(ticker)
            if current_price is None:
                return {'error': f'Could not get price for {ticker}'}

        # Calculate P&L
        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        pnl_dollars = (current_price - pos.entry_price) * pos.shares if pos.shares else 0

        # Time in trade
        entry_time = datetime.fromisoformat(pos.entry_time)
        time_in_trade = datetime.now() - entry_time
        time_min = int(time_in_trade.total_seconds() / 60)

        # Generate signal
        signal = 'HOLD'
        reason = ''

        # Check target
        if current_price >= pos.target_price:
            signal = 'EXIT'
            reason = 'TARGET REACHED'

        # Check stop
        elif current_price <= pos.stop_price:
            signal = 'EXIT'
            reason = 'STOP HIT'

        # Time-based (near EOD)
        now = datetime.now()
        if now.hour >= 15 and now.minute >= 45:
            signal = 'WARNING'
            reason = 'EOD approaching'

        return {
            'ticker': ticker,
            'entry': pos.entry_price,
            'current': current_price,
            'stop': pos.stop_price,
            'target': pos.target_price,
            'pnl_pct': round(pnl_pct, 2),
            'pnl_dollars': round(pnl_dollars, 2),
            'time_min': time_min,
            'signal': signal,
            'reason': reason,
            'shares': pos.shares,
        }

    def check_all(self) -> List[Dict]:
        """Check all positions."""
        results = []
        for ticker in self.positions:
            result = self.check_position(ticker)
            results.append(result)
        return results

    def update_price(self, ticker: str, price: float):
        """Update entry price for a position (manual correction)."""
        ticker = ticker.upper()
        if ticker in self.positions:
            self.positions[ticker].entry_price = price
            self.save_positions()
            print(f"Updated {ticker} entry to ${price:.2f}")
        else:
            print(f"Position not found: {ticker}")

    def list_positions(self):
        """List all positions."""
        if not self.positions:
            print("No active positions")
            return

        print("\nActive Positions:")
        print("-" * 60)
        print(f"{'TICKER':<8} {'ENTRY':>8} {'STOP':>8} {'TARGET':>8} {'TIME':<10}")
        print("-" * 60)

        for ticker, pos in self.positions.items():
            entry_time = datetime.fromisoformat(pos.entry_time)
            elapsed = datetime.now() - entry_time
            hours = int(elapsed.total_seconds() / 3600)
            mins = int((elapsed.total_seconds() % 3600) / 60)

            print(f"{ticker:<8} ${pos.entry_price:>6.2f} ${pos.stop_price:>6.2f} "
                  f"${pos.target_price:>6.2f} {hours}h {mins}m")

    def start_monitoring(self, interval: int = 60):
        """Start monitoring all positions."""
        print("\nStarting position monitoring...")
        print(f"Interval: {interval} seconds")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                now = datetime.now()

                # Market hours check (9:30 - 16:00)
                if now.hour < 9 or (now.hour == 9 and now.minute < 30):
                    print(f"[{now.strftime('%H:%M')}] Waiting for market open...")
                    time.sleep(60)
                    continue

                if now.hour >= 16:
                    print(f"[{now.strftime('%H:%M')}] Market closed")
                    break

                # Check all positions
                results = self.check_all()

                print(f"\n[{now.strftime('%H:%M:%S')}] Position Check")
                print("-" * 50)

                for r in results:
                    if 'error' in r:
                        print(f"  {r.get('ticker', 'UNKNOWN')}: {r['error']}")
                        continue

                    # Color based on signal
                    if r['signal'] == 'EXIT':
                        color = '\033[91m'  # Red
                    elif r['signal'] == 'WARNING':
                        color = '\033[93m'  # Yellow
                    else:
                        color = '\033[92m'  # Green
                    reset = '\033[0m'

                    pnl_sign = '+' if r['pnl_pct'] >= 0 else ''
                    print(f"  {r['ticker']}: ${r['current']:.2f} "
                          f"({pnl_sign}{r['pnl_pct']:.1f}%) "
                          f"{color}{r['signal']}{reset} {r.get('reason', '')}")

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nMonitoring stopped")

        finally:
            if self.ib and self.ib.isConnected():
                self.ib.disconnect()


def main():
    parser = argparse.ArgumentParser(description='LONG Position Signals')
    parser.add_argument('--add', nargs=2, metavar=('TICKER', 'PRICE'),
                        help='Add position: TICKER ENTRY_PRICE')
    parser.add_argument('--stop', type=float, help='Stop price (with --add)')
    parser.add_argument('--target', type=float, help='Target price (with --add)')
    parser.add_argument('--shares', type=int, default=0, help='Number of shares (with --add)')
    parser.add_argument('--remove', type=str, help='Remove position')
    parser.add_argument('--check', type=str, help='Check position')
    parser.add_argument('--check-all', action='store_true', help='Check all positions')
    parser.add_argument('--list', action='store_true', help='List all positions')
    parser.add_argument('--update', nargs=2, metavar=('TICKER', 'PRICE'),
                        help='Update entry price')
    parser.add_argument('--start', action='store_true', help='Start monitoring')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval (seconds)')

    args = parser.parse_args()
    manager = SignalManager()

    if args.add:
        ticker, price = args.add
        manager.add_position(
            ticker=ticker,
            entry_price=float(price),
            stop_price=args.stop,
            target_price=args.target,
            shares=args.shares,
        )

    elif args.remove:
        manager.remove_position(args.remove)

    elif args.check:
        result = manager.check_position(args.check)
        print(json.dumps(result, indent=2))

    elif args.check_all:
        results = manager.check_all()
        for r in results:
            print(json.dumps(r, indent=2))

    elif args.list:
        manager.list_positions()

    elif args.update:
        ticker, price = args.update
        manager.update_price(ticker, float(price))

    elif args.start:
        manager.start_monitoring(interval=args.interval)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
