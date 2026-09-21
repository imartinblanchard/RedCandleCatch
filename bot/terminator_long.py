#!/usr/bin/env python3
"""
Terminator LONG — paper / journal mode.

Runs the pre-market momentum strategy (bot.strategy) LIVE on real IBKR prices but
DOES NOT place orders: every entry/exit is written to a journal CSV, like a
forward paper-trade. Because it runs on future days, the journal is out-of-sample
evidence for STRATEGY.md.

State is restart-safe: open paper positions live in a JSON file, closed trades in
the journal. Kill and relaunch any time — it re-reads its open positions.

Usage:
    python -m bot.terminator_long                 # live paper loop (scans gainers)
    python -m bot.terminator_long --once          # one cycle (debug)
    python -m bot.terminator_long --tickers ABC,XYZ   # watch a fixed list
"""
import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
except Exception:
    ET = None

from bot import strategy
from bot.indicators import vwap_upper
from execution.ibkr_broker import IBKRBroker

COMPUTED = Path(__file__).parent.parent / 'data' / 'computed'
JOURNAL = COMPUTED / 'terminator-long-journal.csv'
STATE = COMPUTED / 'terminator-long-open.json'
JOURNAL_COLS = ['date', 'ticker', 'setup', 'entry_time', 'entry', 'stop', 'band_tp',
                'exit_time', 'exit', 'reason', 'pnl_pct', 'mfe_pct', 'shares', 'mode']

MARKET_OPEN = (9, 30)
SHARES = 1  # paper: mirrors the real-money 1-share test


def now_et() -> datetime:
    return datetime.now(ET) if ET else datetime.now()


def is_after_open(t: datetime) -> bool:
    return (t.hour, t.minute) >= MARKET_OPEN


def load_state() -> Dict[str, dict]:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: Dict[str, dict]):
    STATE.write_text(json.dumps(state, indent=2))


def append_journal(row: dict):
    new = not JOURNAL.exists()
    with open(JOURNAL, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=JOURNAL_COLS)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, '') for c in JOURNAL_COLS})


def pm_bars(broker: IBKRBroker, ticker: str) -> List[dict]:
    """Today's pre-market 1-min bars (04:00–09:30 ET), oldest→newest."""
    raw = broker.intraday_1min(ticker, duration='23400 S')  # ~6.5h back
    today = now_et().date()
    out = []
    for b in raw:
        t = b['t'].astimezone(ET) if ET else b['t']
        if t.date() == today and 4 <= t.hour and (t.hour, t.minute) < MARKET_OPEN:
            out.append({**b, 't': t})
    return out


def scan_candidates(broker: IBKRBroker, limit: int = 15) -> List[str]:
    """Top % gainers $1–$10 via IBKR scanner."""
    try:
        from ib_insync import ScannerSubscription
        sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                                  scanCode='TOP_PERC_GAIN')
        sub.abovePrice = 1.0; sub.belowPrice = 10.0; sub.aboveVolume = 100000
        rows = broker.ib.reqScannerData(sub)
        return [r.contractDetails.contract.symbol for r in rows[:limit]]
    except Exception as e:
        print(f"scan error: {e}")
        return []


class PaperTerminator:
    def __init__(self, broker: IBKRBroker, tickers: Optional[List[str]] = None,
                 max_positions: int = 1):
        self.broker = broker
        self.fixed_tickers = tickers
        self.max_positions = max_positions
        self.state = load_state()
        self.candidates: List[str] = tickers or []

    def _refresh_candidates(self):
        if self.fixed_tickers:
            return
        found = scan_candidates(self.broker)
        if found:
            self.candidates = found

    def cycle(self):
        t = now_et()
        self._refresh_candidates()
        # watch candidates + any open position ticker
        watch = list(dict.fromkeys(self.candidates + list(self.state)))
        for tk in watch:
            bars = pm_bars(self.broker, tk)
            if len(bars) < strategy.MIN_ABOVE + 2:
                # after the open, close any leftover at last price (backstop)
                if tk in self.state and is_after_open(t):
                    self._close(tk, self.state[tk].get('last', self.state[tk]['entry']), 'OPEN')
                continue
            if tk in self.state:
                self._manage_open(tk, bars, t)
            elif len(self.state) < self.max_positions and not is_after_open(t):
                self._maybe_enter(tk, bars)

    def _maybe_enter(self, tk: str, bars: List[dict]):
        # evaluate the last CLOSED bar (drop the current forming minute)
        closed = bars[:-1]
        if len(closed) < strategy.MIN_ABOVE + 2:
            return
        sig = strategy.check_entry(closed)
        if not sig:
            return
        band = vwap_upper(closed, strategy.BAND_K)
        self.state[tk] = {
            'entry': sig['entry'], 'stop': sig['stop'], 'setup': sig['reason'],
            'entry_time': closed[-1]['t'].strftime('%H:%M'), 'peak': closed[-1]['h'],
            'band_tp': round(band, 4) if band else '', 'last': sig['entry'],
        }
        save_state(self.state)
        print(f"[{now_et():%H:%M}] ENTRY {tk} @ {sig['entry']:.4f} "
              f"stop {sig['stop']:.4f} bandTP {self.state[tk]['band_tp']} (PAPER)")

    def _manage_open(self, tk: str, bars: List[dict], t: datetime):
        pos = self.state[tk]
        last = bars[-1]
        pos['peak'] = max(pos.get('peak', pos['entry']), last['h'])
        pos['last'] = last['c']
        if is_after_open(t):
            self._close(tk, last['c'], 'OPEN')
            return
        ex = strategy.check_exit(bars, pos['entry'])
        if ex:
            self._close(tk, ex['price'], ex['reason'])
        else:
            save_state(self.state)

    def _close(self, tk: str, exit_px: float, reason: str):
        pos = self.state.pop(tk)
        entry = pos['entry']
        pnl = (exit_px - entry) / entry * 100
        mfe = (pos.get('peak', entry) - entry) / entry * 100
        append_journal({
            'date': now_et().strftime('%Y-%m-%d'), 'ticker': tk, 'setup': pos.get('setup', ''),
            'entry_time': pos.get('entry_time', ''), 'entry': round(entry, 4),
            'stop': pos.get('stop', ''), 'band_tp': pos.get('band_tp', ''),
            'exit_time': now_et().strftime('%H:%M'), 'exit': round(exit_px, 4),
            'reason': reason, 'pnl_pct': round(pnl, 2), 'mfe_pct': round(mfe, 2),
            'shares': SHARES, 'mode': 'PAPER',
        })
        save_state(self.state)
        print(f"[{now_et():%H:%M}] EXIT  {tk} @ {exit_px:.4f} {reason} "
              f"{pnl:+.2f}% (mfe {mfe:+.1f}%) -> journal")

    def run(self, interval: float = 20.0, once: bool = False):
        n_open = len(self.state)
        print(f"Terminator LONG — PAPER/journal. {len(self.candidates)} candidats, "
              f"{n_open} position(s) ouverte(s) reprise(s). Journal: {JOURNAL.name}")
        while True:
            try:
                self.cycle()
            except Exception as e:
                print(f"cycle error: {e}")
            if once:
                return
            time.sleep(interval)


def main():
    ap = argparse.ArgumentParser(description='Terminator LONG (paper/journal)')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--interval', type=float, default=20.0)
    ap.add_argument('--tickers', type=str, help='comma-separated fixed watchlist')
    ap.add_argument('--max-positions', type=int, default=1)
    args = ap.parse_args()

    broker = IBKRBroker(allow_live=False)  # PAPER: never places orders
    if not broker.connect():
        print("✗ IBKR indisponible (IB Gateway sur 4001 ?)")
        return
    tickers = [t.strip().upper() for t in args.tickers.split(',')] if args.tickers else None
    term = PaperTerminator(broker, tickers=tickers, max_positions=args.max_positions)
    try:
        term.run(interval=args.interval, once=args.once)
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        broker.disconnect()


if __name__ == '__main__':
    main()
