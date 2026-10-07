#!/usr/bin/env python3
"""
Live Dashboard for LONG Trading - Gap & Go Strategy

Terminal-based dashboard with:
- Pre-market scanner for gap UP stocks (scans every 15 min)
- Auto-saves matching tickers to data/long-checklist.csv
- Final scan at 09:25-09:29 before market open
- Real-time position monitoring

Usage:
    python -m bot.redcandlecatch_dashboard           # Start dashboard
    python -m bot.redcandlecatch_dashboard --now     # Start immediately (skip time check)

Data Collection:
    - Checklist saved to: data/long-checklist.csv
    - Run fetch_candles.py the next day to get 5-min candle data
"""
import argparse
import csv
import os
import sys
import time
import select
import termios
import tty
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
COMPUTED_DIR = DATA_DIR / 'computed'
CHECKLIST_FILE = DATA_DIR / 'long-checklist.csv'

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Checklist columns
CHECKLIST_COLUMNS = [
    'Date', 'Ticker', 'Gap%', 'Price', 'Float', 'Inst%',
    'PM_Vol', 'Rel_Vol', 'PM_High', 'Catalyst', 'Sector',
    'Score', 'Status', 'Notes'
]


def save_to_checklist(stocks: List[Dict], date_str: str = None):
    """
    Save matching stocks to the checklist CSV.
    One line per ticker per date (allows duplicates across days).
    """
    if not stocks:
        return

    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    # Load existing checklist or create new
    if CHECKLIST_FILE.exists():
        df = pd.read_csv(CHECKLIST_FILE)
    else:
        df = pd.DataFrame(columns=CHECKLIST_COLUMNS)

    added = 0
    for stock in stocks:
        # Skip if status is SKIP
        if stock.get('status') == 'SKIP':
            continue

        ticker = stock.get('ticker', '')

        # Check if already exists for this date
        exists = ((df['Date'] == date_str) & (df['Ticker'] == ticker)).any()
        if exists:
            # Update existing row
            idx = df[(df['Date'] == date_str) & (df['Ticker'] == ticker)].index[0]
            df.loc[idx, 'Gap%'] = stock.get('gap_pct', '')
            df.loc[idx, 'Price'] = stock.get('price', '')
            df.loc[idx, 'Score'] = stock.get('score', '')
            df.loc[idx, 'Status'] = stock.get('status', '')
            continue

        # Add new row
        new_row = {
            'Date': date_str,
            'Ticker': ticker,
            'Gap%': stock.get('gap_pct', ''),
            'Price': stock.get('price', ''),
            'Float': round(stock.get('float', 0) / 1e6, 2) if stock.get('float') else '',
            'Inst%': stock.get('inst_pct', ''),
            'PM_Vol': round(stock.get('pm_volume', 0) / 1000, 0) if stock.get('pm_volume') else '',
            'Rel_Vol': stock.get('rel_volume', ''),
            'PM_High': stock.get('pm_high', ''),
            'Catalyst': stock.get('catalyst', ''),
            'Sector': stock.get('sector', ''),
            'Score': stock.get('score', ''),
            'Status': stock.get('status', ''),
            'Notes': '',
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        added += 1

    # Sort by date and save
    df = df.sort_values(['Date', 'Ticker'])
    df.to_csv(CHECKLIST_FILE, index=False)

    return added


# Try imports
try:
    from bot.signals import SignalManager, Position
    from bot import redcandlecatch_scan as wscan      # filtrage LONG (même moteur que l'exécuteur)
    from bot import eligible                    # fichier de signaux partagé
    from execution.ibkr_broker import IBKRBroker
    HAS_BOT = True
except ImportError as e:
    print(f"Import error: {e}")
    HAS_BOT = False

# Terminal colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
GRAY = '\033[90m'
BOLD = '\033[1m'
RESET = '\033[0m'


class LiveDashboard:
    """Terminal-based live dashboard for LONG trading."""

    def __init__(self, start_now: bool = False):
        self.start_now = start_now
        self.phase = 'WAITING'  # WAITING, PREMARKET, TRADING, CLOSED
        self.watchlist: List[Dict] = []
        self.signals = SignalManager() if HAS_BOT else None
        self.messages: List[str] = []
        self.account_capital = None              # vrai capital IBKR (NetLiquidation), récupéré au scan
        self.last_scan = None
        self.final_scan_done = False  # Track if final pre-open scan was done
        self.running = True
        self.broker = None                       # IBKRBroker (clientId 32, distinct de l'exécuteur=31)
        self.scan_interval = 60                  # scan continu toutes les 60 s

    def _get_broker(self):
        """Connexion IBKR paresseuse (clientId 32, pour ne pas entrer en conflit
        avec l'exécuteur qui utilise 31)."""
        if not HAS_BOT:
            return None
        if self.broker is None:
            self.broker = IBKRBroker(client_id=32)
        if not self.broker.connect():
            return None
        return self.broker

    def clear_screen(self):
        """Clear terminal screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

    def get_phase(self) -> str:
        """Determine current trading phase."""
        if self.start_now:
            return 'PREMARKET'

        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # Pre-market: 4:30 - 9:30
        if (hour == 4 and minute >= 30) or (5 <= hour <= 8) or (hour == 9 and minute < 30):
            return 'PREMARKET'
        # Trading: 9:30 - 16:30 (aligné sur l'exécuteur)
        elif (hour == 9 and minute >= 30) or (10 <= hour <= 15) or (hour == 16 and minute < 30):
            return 'TRADING'
        # Closed
        elif hour > 16 or (hour == 16 and minute >= 30):
            return 'CLOSED'
        # Waiting
        else:
            return 'WAITING'

    def _add_message(self, msg: str):
        """Add message to display."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.messages.append(f"[{timestamp}] {msg}")
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]

    def _draw_header(self):
        """Draw dashboard header."""
        now = datetime.now()
        phase_colors = {
            'WAITING': GRAY,
            'PREMARKET': CYAN,
            'TRADING': GREEN,
            'CLOSED': RED,
        }
        color = phase_colors.get(self.phase, RESET)

        # Check if checklist exists and count today's entries
        checklist_count = 0
        if CHECKLIST_FILE.exists():
            try:
                df = pd.read_csv(CHECKLIST_FILE)
                today = now.strftime('%Y-%m-%d')
                checklist_count = len(df[df['Date'] == today])
            except:
                pass

        print(f"{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}  LONG DASHBOARD - Gap & Go Strategy{RESET}")
        print(f"  {now.strftime('%Y-%m-%d %H:%M:%S')}  |  Phase: {color}{self.phase}{RESET}")
        cap = f"${self.account_capital:,.0f}" if self.account_capital else "… (IBKR)"
        print(f"  Capital (compte IBKR): {cap}  |  Éligibles: {len(self.watchlist)}")
        print(f"{BOLD}{'=' * 60}{RESET}")

    def _draw_watchlist(self):
        """Liste des éligibles envoyés à l'exécuteur (fichier de signaux, sticky)."""
        print(f"\n{CYAN}[ÉLIGIBLES LONG -> exécuteur]{RESET}")
        print("-" * 72)
        if not self.watchlist:
            print(f"  {GRAY}Aucun titre éligible pour l'instant{RESET}")
            return
        print(f"  {'TICKER':<6} {'GAP':>6} {'PRICE':>7} {'FLOAT':>7} "
              f"{'CHART':>5} {'VOL':>4} {'FLT':>4} {'SSR':>4} {'@':>6}")
        print("-" * 72)
        for s in self.watchlist:
            gap = s.get('gap') or 0
            price = s.get('price') or 0
            fs = s.get('float_shares')
            float_m = (fs / 1e6) if fs else 0
            cr = s.get('chart_rating', '-'); vr = s.get('volume_rating', '-')
            fr = s.get('float_rating', '-')
            ssr = f"{YELLOW}SSR{RESET}" if s.get('ssr') else f"{GRAY}-{RESET}"
            print(f"  {GREEN}{s['ticker']:<6}{RESET} "
                  f"+{gap:>5.1f}% ${price:>6.2f} {float_m:>6.1f}M "
                  f"{cr:>5} {vr:>4} {fr:>4} {ssr:>4} {s.get('added',''):>6}")

    def _draw_positions(self):
        """Positions actives du TERMINATOR (lit redcandlecatch-open.json)."""
        import json as _json
        print(f"\n{GREEN}[POSITIONS ACTIVES — terminator]{RESET}")
        print("-" * 72)
        f = COMPUTED_DIR / 'redcandlecatch-open.json'
        try:
            pos = _json.loads(f.read_text()) if f.exists() else {}
        except Exception:
            pos = {}
        if not pos:
            print(f"  {GRAY}Aucune position active{RESET}")
            return
        print(f"  {'TICKER':<6} {'ENTRÉE':>8} {'NOW':>8} {'P&L%':>7} {'PHASE':<10} {'STOP':>7} {'GAP':>6}")
        print("-" * 72)
        for tk, p in pos.items():
            entry = p.get('fill') or p.get('entry', 0)      # fill réel si dispo, sinon signal
            last = p.get('last', entry) or entry
            pnl = (last - entry) / entry * 100 if entry else 0
            col = GREEN if pnl >= 0 else RED
            phase = "TRAIL" if p.get('activated') else "STOP -10%"
            stop = p.get('stop_level', '')
            stop_s = f"{stop:.2f}" if isinstance(stop, (int, float)) else '-'
            gap = p.get('gap', '')
            print(f"  {tk:<6} {entry:>8.3f} {last:>8.3f} "
                  f"{col}{pnl:>+6.1f}%{RESET} {phase:<10} {stop_s:>7} {str(gap):>6}")

    def _draw_messages(self):
        """Draw recent messages."""
        if self.messages:
            print(f"\n{YELLOW}[MESSAGES]{RESET}")
            for msg in self.messages[-8:]:
                print(f"  {msg}")

    def _draw_help(self):
        """Draw help footer."""
        print(f"\n{GRAY}" + "-" * 60 + f"{RESET}")

        if self.phase == 'PREMARKET':
            print(f"{GRAY}  [A] Add to watch  [X] Remove  [C] Capital  [R] Refresh  [Q] Quit{RESET}")
        elif self.phase == 'TRADING':
            print(f"{GRAY}  [A] Add position  [X] Close  [U] Update  [C] Capital  [Q] Quit{RESET}")
        else:
            print(f"{GRAY}  [Q] Quit{RESET}")

    def _handle_input(self):
        """Handle keyboard input."""
        # Check if input available
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            key = sys.stdin.read(1).upper()

            if key == 'Q':
                self.running = False
            elif key == 'R':
                self._do_scan()
            elif key == 'C':
                self._cmd_capital()
            elif key == 'A':
                self._cmd_add()
            elif key == 'X':
                self._cmd_remove()
            elif key == 'U' and self.phase == 'TRADING':
                self._cmd_update()

    def _cmd_capital(self):
        """Rafraîchir le capital depuis le compte IBKR (plus de saisie manuelle :
        le capital est toujours le vrai NetLiquidation du compte)."""
        br = self._get_broker()
        if br is None:
            self._add_message("IBKR non connecté")
            return
        try:
            nl = br.account_summary().get('NetLiquidation')
            if nl:
                self.account_capital = float(nl)
                self._add_message(f"Capital IBKR: ${self.account_capital:,.0f}")
            else:
                self._add_message("NetLiquidation indisponible")
        except Exception as e:
            self._add_message(f"capital err: {e}")

    def _cmd_add(self):
        """Add position or watchlist item."""
        self._restore_terminal()
        try:
            if self.phase == 'PREMARKET':
                ticker = input("\nAdd ticker to watch: ").upper()
                if ticker:
                    # Quick scan for this ticker
                    self._add_message(f"Analyzing {ticker}...")
            else:
                inp = input("\nAdd position (TICKER PRICE [STOP] [TARGET]): ").strip()
                if inp:
                    parts = inp.split()
                    ticker = parts[0].upper()
                    price = float(parts[1])
                    stop = float(parts[2]) if len(parts) > 2 else None
                    target = float(parts[3]) if len(parts) > 3 else None

                    if self.signals:
                        self.signals.add_position(ticker, price, stop, target)
                        self._add_message(f"Added {ticker} @ ${price:.2f}")
        except (ValueError, IndexError) as e:
            self._add_message(f"Invalid input: {e}")
        self._setup_terminal()

    def _cmd_remove(self):
        """Remove position or watchlist item."""
        self._restore_terminal()
        try:
            ticker = input("\nRemove ticker: ").upper()
            if ticker:
                if self.phase == 'PREMARKET':
                    self.watchlist = [w for w in self.watchlist if w['ticker'] != ticker]
                    self._add_message(f"Removed {ticker} from watchlist")
                else:
                    if self.signals:
                        self.signals.remove_position(ticker)
                        self._add_message(f"Closed {ticker}")
        except Exception as e:
            self._add_message(f"Error: {e}")
        self._setup_terminal()

    def _cmd_update(self):
        """Update position price."""
        self._restore_terminal()
        try:
            inp = input("\nUpdate (TICKER PRICE): ").strip()
            if inp:
                parts = inp.split()
                ticker = parts[0].upper()
                price = float(parts[1])
                if self.signals:
                    self.signals.update_price(ticker, price)
                    self._add_message(f"Updated {ticker} to ${price:.2f}")
        except (ValueError, IndexError) as e:
            self._add_message(f"Invalid input: {e}")
        self._setup_terminal()

    def _do_scan(self, is_final: bool = False):
        """Scan LONG (redcandlecatch_scan) puis écrit les éligibles dans le fichier de
        signaux (sticky). L'exécuteur (RedCandleCatch terminator) lira ce fichier."""
        self.last_scan = datetime.now()
        if not HAS_BOT:
            self._add_message("modules bot indisponibles")
            return
        br = self._get_broker()
        if br is None:
            self._add_message("IBKR non connecté (scan impossible)")
            return
        try:
            # vrai capital du compte IBKR (NetLiquidation) — remplace le montant en dur
            try:
                nl = br.account_summary().get('NetLiquidation')
                if nl:
                    self.account_capital = float(nl)
            except Exception:
                pass
            elig = wscan.scan_eligible(br)           # éligibles de CE cycle (TRADING, gap 5-10)
            eligible.write_all(elig)                 # merge STICKY dans le fichier du jour
            full = eligible.load()                   # liste sticky complète du jour
            # CAPTURE LIVE de l'univers LARGE 5-500% (collecte de données, indépendant du trading)
            try:
                import bot.collect_universe as cu
                nadd, ntot = cu.record(br)
                if nadd:
                    self._add_message(f"  [univers 5-500] +{nadd} nouveaux, {ntot} au total")
            except Exception as e:
                self._add_message(f"  [univers] err: {e}")
            self.watchlist = sorted(
                [dict(ticker=tk, **info) for tk, info in full.items()],
                key=lambda x: (x.get('gap') or 0), reverse=True)
            for tk in elig:
                self._add_message(f"  éligible: {tk} gap {elig[tk].get('gap')}% {elig[tk].get('reason','')}")
            self._add_message(f"scan: {len(elig)} ce cycle, {len(full)} au total (sticky) -> fichier de signaux")
        except Exception as e:
            import traceback
            self._add_message(f"scan erreur: {e}")
            traceback.print_exc()

    def _setup_terminal(self):
        """Set terminal to raw mode."""
        self.old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    def _restore_terminal(self):
        """Restore terminal settings."""
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def _run_headless(self):
        """Boucle SCANNER sans TUI (quand lancé en arrière-plan / nohup, sans terminal).
        Scanne en continu et écrit le fichier de signaux ; log court sur stdout."""
        print("=== Dashboard SCANNER (headless) — scan continu -> fichier de signaux ===", flush=True)
        try:
            while self.running:
                self.phase = self.get_phase()
                if self.phase in ('PREMARKET', 'TRADING'):
                    if not self.last_scan or (datetime.now() - self.last_scan).seconds >= self.scan_interval:
                        self._do_scan()
                        full = eligible.load()
                        cap = f"${self.account_capital:,.0f}" if self.account_capital else "?"
                        print(f"[{datetime.now():%H:%M:%S}] {self.phase} capital={cap} "
                              f"éligibles={len(full)}: {list(full)}", flush=True)
                time.sleep(5)
        except KeyboardInterrupt:
            pass

    def run(self):
        """Boucle principale. Interactif si vrai terminal, sinon headless (scanner seul)."""
        if not sys.stdin.isatty():
            self._run_headless()
            return
        self._setup_terminal()

        try:
            while self.running:
                self.phase = self.get_phase()

                # Clear and draw
                self.clear_screen()
                self._draw_header()

                if self.phase in ('PREMARKET', 'TRADING'):
                    # scan CONTINU en pré-marché ET en séance (le RedCandleCatch achète le
                    # dip n'importe quand) -> alimente le fichier de signaux
                    self._draw_watchlist()
                    if self.phase == 'TRADING':
                        self._draw_positions()
                    if not self.last_scan or (datetime.now() - self.last_scan).seconds >= self.scan_interval:
                        self._do_scan()

                elif self.phase == 'WAITING':
                    print(f"\n{GRAY}  Waiting for pre-market (4:30 AM)...{RESET}")

                elif self.phase == 'CLOSED':
                    self._draw_positions()
                    print(f"\n{GRAY}  Market closed{RESET}")

                self._draw_messages()
                self._draw_help()

                # Handle input
                self._handle_input()

                time.sleep(0.5)

        except KeyboardInterrupt:
            pass
        finally:
            self._restore_terminal()
            print("\nDashboard closed")


def main():
    parser = argparse.ArgumentParser(description='LONG Trading Dashboard')
    parser.add_argument('--now', action='store_true', help='Start immediately')
    args = parser.parse_args()

    dashboard = LiveDashboard(start_now=args.now)
    dashboard.run()


if __name__ == '__main__':
    main()
