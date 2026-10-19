# RedCandleCatch

**Automated LONG *Gap & Go* trading bot for small-cap momentum stocks**, running on Interactive Brokers (IBKR). It scans for stocks gapping up with momentum, buys the **pullback from the day's high when volume capitulates**, holds to the close under a wide stop, and collects a survivorship-bias-free dataset for research.

> ⚠️ **Disclaimer** — This is experimental software for research and educational purposes.
> Trading involves substantial risk of loss. Nothing here is financial advice. The backtested
> edge is measured **in-sample** (survivorship bias + optimistic fills) and is an **upper bound** —
> it must be forward-tested before being trusted. Use at your own risk.

---

## Strategy in one paragraph — v3 "Retrace & Capitulation"

Small-caps that gap **+5–10 %** (measured 04:00 → noon ET) tend to run to a high-of-day (HOD), then
**pull back**. The bot buys that pullback — but only when the sellers **capitulate**: it waits for a
**≥ 8 % retrace from the HOD** where **volume accelerates on the way down** (2nd-half / 1st-half
volume ratio > 1.3 over ≥ 4 candles), with two "falling-knife" guards — the stock must have
**run up ≥ 2 % intraday** before the dip and still show a **≥ 1 % gap at the open** (not a faded
pre-market spike). The entry is sized off the **signal price** (the dip-candle close, matching the
chart). The exit is deliberately simple: a fixed **−10 % stop** and then **hold to the close** (no
trailing, no take-profit — trailing exited winners too early), with a **forced exit at 15:55 ET**.
Regular session only (`TRADE_PM=False`). Full details in [STRATEGY.md](STRATEGY.md); dated research
log in [FINDINGS.md](FINDINGS.md).

## Architecture — two processes, run both

```
┌─────────────────────────┐        writes         ┌──────────────────────────────┐
│ redcandlecatch_dashboard │ ── eligible signal ─▶ │ redcandlecatch_terminator    │
│  (scanner / universe)    │   file (sticky JSON)  │  (executor: detects dip,     │
│                          │                       │   places & manages orders)   │
└─────────────────────────┘                       └──────────────────────────────┘
        │                                                       │
        └── IBKR (gap scan, filters) ──────────────────────────┘
```

- **`python -m bot.redcandlecatch_dashboard`** — scans the pre-market/session, writes a sticky
  per-day signal file `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json`.
- **`python -m bot.redcandlecatch_terminator --live`** — reads that file, detects the dip entry,
  places real IBKR orders, manages the two-phase exit, and journals every trade.
  Without `--live` it runs in **PAPER** mode (journals only, no real orders).

## Setup

```bash
git clone https://github.com/imartinblanchard/RedCandleCatch.git
cd RedCandleCatch
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your Alpaca keys (IBKR runs via IB Gateway on :4001)
```

Requires a running **IB Gateway / TWS** on port 4001 (paper or live account) and, for the
research data pipeline, **Alpaca** API keys (SIP historical).

## Usage

```bash
# 1) Scanner  +  2) Executor  (run BOTH)
python -m bot.redcandlecatch_dashboard
python -u -m bot.redcandlecatch_terminator --live >> data/redcandlecatch-live.log 2>&1

# Research dataset (run daily, next day) — every ticker that passed the filters, unbiased
python -m bot.collect_eligibles

# System health check
./scripts/healthcheck.sh
```

## Project structure

| Path | Purpose |
|------|---------|
| `bot/` | Live bot — scanner (`redcandlecatch_scan`), executor (`redcandlecatch_terminator`), dashboard, signal file, data collection |
| `execution/` | IBKR broker wrapper (prices, orders, positions) |
| `research/` | Backtests, validation scripts, historical datasets, Pine indicator |
| `analysis/` | Feature extraction & ML entry model |
| `data/` | Signals, trade journal, collected research dataset (`COLUMN_UNITS.md` documents every column's unit) |
| `scripts/` | Ops helpers (health check, daily collection, parquet→CSV) |

## Documentation

- **[STRATEGY.md](STRATEGY.md)** — the live strategy, every parameter, how to run.
- **[FINDINGS.md](FINDINGS.md)** — dated research log justifying each decision.
- **[data/COLUMN_UNITS.md](data/COLUMN_UNITS.md)** — units of every data column ($ vs % vs volume).
- **[CLAUDE.md](CLAUDE.md)** — repository guide (architecture, conventions).

## Status

Forward-test in progress, **1 share/trade** (minimal-risk validation — at this size commissions make
the mode intentionally loss-making; it validates *execution*, not profit). On the 10 live sessions
collected through 2026-10-12 the v3 config shows **+2.78 %/trade (t = 3.0)**, ~2–3 trades/day — the
first config to reach significance — but this is an **upper bound** (survivorship bias, optimistic
fills, gross P&L). The real judge is the accumulating live/forward record.

## License

[MIT](LICENSE)
