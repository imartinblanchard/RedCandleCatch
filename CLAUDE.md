# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Trading bot for the **LONG Gap & Go strategy** (Warrior Trading style). Scans for small-cap stocks gapping UP with momentum, manages positions, and collects data for ML training. Uses the same IBKR instance as the short-journal project but with different Client IDs (30+ vs 10/20).

**Direction**: LONG (buy low, sell high on gap-up momentum)

> ⚠️ **MISE À JOUR 2026-09-23 (rebuild point-in-time `research/pit_gappers/`) — fait autorité sur la description ci-dessous.**
> Un audit a montré que l'ancien "edge post-open" (gap 10-20) était un **artefact de look-ahead** ; mesuré proprement il est nul.
> Config live DÉSORMAIS :
> - **Bande de gap 5-10 %** (plus 10-20). Seule bande OOS-validée. `GAP_MIN/MAX = 5/10`.
> - **Classification PM/post-open par l'heure du DIP** (plus par `added`) + **recheck du gap** : on n'entre que si le gap est ENCORE dans 5-10 % au moment du dip (l'éligibilité est sticky).
> - **Plancher de float 5M** (`FLOAT_MIN_HARD`, exclut l'ultra-bas perdant ; float inconnu passe).
> - **Entrée en LIMITE marketable** (plus d'ordre marché) — l'edge (+0,5 %/tr) meurt dès +0,5 % de slippage.
> - Inchangé : dip 1,5 %, act +10 %, trail 2 %, stop −10 %, prix 3-20 $, dip-candle ≥ 200 K$, `TRADE_PM=False`.
> Backtest de cette règle : +0,46 %/tr (t=3,5), TEST +0,61 % (t=3,2). Voir mémoire `edge-reel-gap-5-10` et `lookahead-postopen-invalide`.
> Les paragraphes ci-dessous décrivent encore l'ANCIENNE config (10-20, dip adaptatif −5/−1,5 par `added`) — à lire comme historique.

**Live strategy — RedCandleCatch_SmallCap**: see [STRATEGY.md](STRATEGY.md). Dip-buy
momentum during regular hours. Universe: gap **10-20%** measured **04:00→noon** (catches
post-open runners, not just pre-market), price 3-20$ (session dollar-volume filter disabled 19/09; liquidity is gated at entry by
the dip candle ≥ $200K). Entry (**post-open runners only** since 18/09 — PM gappers no longer traded, `TRADE_PM=False`, but still collected): **adaptive dip by eligibility TIME** — **−5%** if eligible **before the open**
(`added < 09:31`, pre-market gapper), **−1.5%** if **added after the open** (post-open runner),
AND the **dip candle itself** must have **volume × close ≥ $200K** (`MIN_DIP_DOLLAR_VOL`,
18/09 — easy fills / anti-slippage; skipped entries are logged as `SKIP … illiquide`).
Exit: 2-phase STOP −10% → at **+5% (PM) / +10% (post-open) of the SIGNAL price** (adaptive activation) → **native
IBKR TRAIL 2%**, **forced exit at 15:55** (2-tier: liquid RTH sell → extended → GTC next
open), 1 share/trade. Stop/activation levels use the **SIGNAL
price** (dip-candle close, matches the chart), NOT the fill; the fill is only for P&L.
See [FINDINGS.md](FINDINGS.md) and the `todo-post-session` memory for the 2026-09-16
changes (adaptive dip, post-open gap, liquidity filter, prev_close fix, signal-price
levels). ⚠️ Edge is IN-SAMPLE / borne supérieure — paper-test before trusting live.

**Two entry points only** (everything else is a library called by these):
- `python -m bot.redcandlecatch_dashboard` — RedCandleCatch scanner/UI, scans the pre-market and
  writes a **sticky** per-day signal file `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json`
  (via `bot.eligible`) that the terminator reads.
- `python -m bot.redcandlecatch_terminator` — the executor. Reads the eligible signal file,
  detects the adaptive dip entry (−5% if pre-open eligible / −1.5% if post-open, dip candle ≥ $200K), manages the 2-phase exit, and journals every trade.
  **PAPER by default** (no real orders); pass `--live` for real IBKR orders.
  **You must run BOTH** (scanner feeds the executor via the signal file).

> ⚠️ **`terminator_long.py` / `bot/strategy.py` are the OLD paper path** — the
> VWAP-pullback pre-market strategy, archived in
> [STRATEGY_VWAP_ARCHIVE.md](STRATEGY_VWAP_ARCHIVE.md). Kept for reference, **never**
> ran live. The live bot is `redcandlecatch_terminator` + `redcandlecatch_scan`.

## Commands

```bash
# Activate environment
source .venv/bin/activate

# Main dashboard (live trading)
python -m bot.redcandlecatch_dashboard          # Start live dashboard
python -m bot.redcandlecatch_dashboard --now    # Skip time check (testing)

# RedCandleCatch terminator - the LIVE bot (adaptive dip -1.5%/-5%, dip-candle liq >=200K, act +10% / trail 2%, see STRATEGY.md)
# NOTE: run redcandlecatch_dashboard first (it writes the eligible signal file this reads).
python -m bot.redcandlecatch_terminator            # PAPER: journals trades, no real orders
python -m bot.redcandlecatch_terminator --live     # LIVE: places REAL IBKR orders
python -m bot.redcandlecatch_terminator --once     # One cycle (debug)
python -m bot.redcandlecatch_terminator --tickers ABC,XYZ   # Fixed watchlist (bypass gap scan)

# OLD paper path (VWAP-pullback strategy, reference only — NOT the live bot)
python -m bot.terminator_long              # PAPER: live IBKR prices, journals trades, no orders

# Scanner
python -m bot.scanner                    # Scan IBKR top gainers
python -m bot.scanner --ticker BZFD      # Analyze single stock
python -m bot.scanner --no-ibkr          # Manual input mode

# Position signals
python -m bot.signals --add BZFD 5.50                          # Add position
python -m bot.signals --add BZFD 5.50 --stop 5.00 --target 6.50 --shares 100
python -m bot.signals --remove BZFD      # Remove position
python -m bot.signals --list             # List positions
python -m bot.signals --start            # Start monitoring

# Data collection (run next day)
python -m bot.fetch_candles              # Fetch pending candles
python -m bot.fetch_candles --date 2025-05-28
python -m bot.fetch_candles --dry-run    # Preview only

# Research dataset — ALL tickers that pass our filters (PM + post-open), UNBIASED (real-time)
# Run DAILY (next day; Alpaca SIP historical has a delay so same-day returns nothing).
python -m bot.collect_eligibles          # master table + 1-min bars for new eligible days
python -m bot.collect_eligibles --date 2026-09-17
python -m bot.collect_eligibles --no-bars   # metadata master only (fast, no Alpaca)

# ML analysis
python -m analysis.features              # Show available features
python -m analysis.entry_model --train   # Train entry model
```

## Architecture

### Module Responsibilities

**Entry points** (things you run — run BOTH; scanner feeds executor via signal file):
| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `bot/redcandlecatch_dashboard.py` | Terminal UI + pre-market scanner | Phase detection, `scan_eligible()`, writes eligible signal file |
| `bot/redcandlecatch_terminator.py` | LIVE trade engine (adaptive dip −1.5%/−5%, dip-candle liq ≥$200K, native trail 2%) | reads eligible file, 2-phase exit, journals to `redcandlecatch-journal.csv`, `--live` guard |

**RedCandleCatch strategy libraries** (called by `redcandlecatch_terminator`):
| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `bot/redcandlecatch_scan.py` | Gap scan + RedCandleCatch filters | `scan_eligible()`, `GAP_MIN/MAX=5/10` (23/09, ex-10/20), `FLOAT_MIN_HARD=5M`, chart/volume/float/SSR ratings |
| `bot/eligible.py` | Sticky per-day signal file | `write_all()`, `load()`, `upsert()` → `redcandlecatch-eligible-YYYY-MM-DD.json` |
| `bot/indicators.py` | Pure math | `vwap()`, `ema()`, `vwap_bands()`/`vwap_upper()` |
| `execution/ibkr_broker.py` | IBKR prices + orders | `IBKRBroker` (prices, positions, bars, buy/sell, `allow_live` guard) |

**OLD paper path** (reference only, NOT live — the VWAP-pullback strategy in STRATEGY.md):
| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `bot/terminator_long.py` | Old paper trade engine | `PaperTerminator`, `scan_candidates()` |
| `bot/strategy.py` | Old VWAP-pullback rules | `check_entry()`, `check_exit()` + tuned constants |

**Scan / data / config**:
| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `bot/scanner.py` | Gap screening & scoring | `FilterCriteria`, `scan_ibkr_gainers()`, `analyze_stock()` |
| `bot/alpaca_scanner.py` | Alt scan + historical backfill | `scan_alpaca_gainers()`, `premarket_stats()` (SIP historical only) |
| `bot/signals.py` | Manual position management | `Position`, `SignalManager`, `check_position()` |
| `bot/fetch_candles.py` | Historical data | `fetch_candle_data()`, updates prices/percent CSVs |
| `bot/config.py` | Configuration | `ACCOUNT_SIZE`, IBKR + Alpaca settings, `STRATEGIES`, ML config |
| `analysis/features.py` | Feature extraction | Pre-entry & intraday features for ML |
| `analysis/entry_model.py` | ML model | RandomForest for entry prediction |

### Data Flow

```
LIVE TRADING PATH (regular hours 09:30-16:30) — the RedCandleCatch bot
  redcandlecatch_dashboard.py → redcandlecatch_scan.scan_eligible() (gap 10-20%, filters)
    → writes data/computed/redcandlecatch-eligible-YYYY-MM-DD.json  (sticky signal file)
  redcandlecatch_terminator.py → reads eligible file → IBKR 1-min bars → adaptive dip entry (−5% pre-open / −1.5% post-open, dip candle ≥$200K)
    → STOP -10% → (at +5% PM / +10% post-open) → TRAIL 2% → forced exit 15:55 (2-tier)
    → redcandlecatch-journal.csv (+ open positions in redcandlecatch-open.json)

PRE-MARKET (04:30-09:30) — the analysis/data path
  dashboard.py → scanner.py → analyze stocks → save to long-checklist.csv

OLD PAPER PATH (reference only, not live)
  terminator_long.py → strategy.check_entry/exit (VWAP-pullback) → terminator-long-journal.csv

NEXT DAY
  fetch_candles.py → long-prices.csv + long-percent.csv

ML TRAINING
  features.py → entry_model.py → data/computed/models/
```

### IBKR Connection Pattern

All modules use `ib_insync` with random Client IDs in the 30-3999 range to avoid conflicts:

```python
from ib_insync import IB, Stock, ScannerSubscription
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=random_id)  # Port 4001 for live/paper
```

Scanner uses `TOP_PERC_GAIN` scan code for gap-up stocks. The terminator's
`IBKRBroker` uses a fixed `clientId=31` (prices + orders on one connection, port
4001, auto-reconnect). Orders are marketable LIMIT with `outsideRth=True` so they
fill pre-market; `allow_live=False` blocks real orders (paper/journal default).

**Alpaca** (scan alt + historical backfill only, not execution): keys in `.env`
(git-ignored, reused from ../stock-journal). This account has **SIP historical
only** — recent/real-time SIP returns 403, so real-time queries use IEX.

## Data Files

| File | Format | Purpose |
|------|--------|---------|
| `data/long-checklist.csv` | Date,Ticker,Gap%,Price,Float,... | Daily scan results |
| `data/long-prices.csv` | OHLC columns per 5-min candle | Absolute prices for backtesting |
| `data/long-percent.csv` | Same structure, % vs Open | Percentage changes for ML |
| `data/computed/active-positions.json` | JSON dict by ticker | Current open positions (signals.py) |
| `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json` | JSON dict by ticker | **Sticky signal file** — dashboard writes, terminator reads |
| `data/computed/redcandlecatch-journal.csv` | date,ticker,gap,entry,exit,reason,pnl_pct,mfe_pct,...,mode | **LIVE RedCandleCatch** trade log (RedCandleCatch_SmallCap, adaptive dip/trail 2%) |
| `data/computed/redcandlecatch-open.json` | JSON dict by ticker | RedCandleCatch's open positions (restart-safe, LIVE or PAPER) |
| `data/computed/terminator-long-journal.csv` | date,ticker,setup,entry,exit,reason,pnl_pct,mfe_pct,... | OLD paper path trade log (VWAP-pullback, reference) |
| `data/computed/terminator-long-open.json` | JSON dict by ticker | OLD paper path open positions |
| `data/collected/eligibles.csv` | date,ticker,is_premarket,gap,price,dollar_vol,ratings,... | **Research master table** — every ticker that passed the filters (PM + post-open), captured in real-time (survivorship-bias-FREE). Built by `collect_eligibles`. |
| `data/collected/bars/YYYY-MM-DD.parquet` | ticker,date,datetime,o,h,l,c,v | 1-min bars 04:00-16:00 of each eligible ticker that day (Alpaca SIP hist). For backtesting the collected universe. |

## Selection Criteria (Warrior Trading)

| Criterion | Value |
|-----------|-------|
| Gap | +4% to +50% |
| Price | $1 - $10 |
| Float | < 20M ideal, < 100M max |
| Rel Volume | 2x+ minimum |
| PM Volume | > 150K |
| Inst % | < 30% |

## Risk Management

- **Risk per trade**: 2% of account (`ACCOUNT_SIZE` in config.py)
- **Max position**: 20% of account
- **Stop loss**: Below PM low or ~10% below entry
- **Target**: 2:1 risk/reward minimum
- Position sizing: `shares = risk_amount / (entry - stop)`

The **live RedCandleCatch terminator** currently overrides this for testing:
**1 share/trade, 1 position per ticker/day**. 2-phase exit: fixed **STOP −10%**, then at
**+5% (PM) / +10% (post-open)** profit switch to a native **TRAIL 2%**, with a **forced exit at 15:55** (2-tier:
liquid RTH → extended → GTC). Universe: gap
**10–20%** (measured 04:00→noon), price **3–20$**, **dip candle ≥ $200K** (`MIN_DIP_DOLLAR_VOL`) — the sole liquidity gate (the scanner's
session dollar-volume filter was disabled 19/09; `dollar_vol` is still recorded). Entry: a 1-min
**adaptive dip** (−5% if eligible pre-open / −1.5% if added post-open). Levels off the **signal price**, native
IBKR trail. (The old `terminator_long` used a fixed −5% stop + VWAP+2σ TP — see STRATEGY.md.)

## Key Differences from Short Journal

| Aspect | Short | Long |
|--------|-------|------|
| WIN condition | Price DOWN | Price UP |
| Stop placement | Above entry | Below entry |
| Strategy | Fade the gap | Ride momentum |
| Client IDs | 10, 20 | 30+ |
