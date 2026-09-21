# region imports
from AlgorithmImports import *
# endregion

# =============================================================================
#  MICRO PULLBACK MOMENTUM  —  Day Trading Long-Only (Ross Cameron style)
#  Platform : QuantConnect / LEAN (Python)
#
#  Pipeline : Universe screener (price/gap/RVOL) -> per-symbol technical setup
#             -> micro-pullback entry -> risk mgmt (stop @ pullback low,
#             TP1 @ HOD 50%, R:R gate) -> dynamic emergency exits.
#
#  All tunables are exposed via GetParameter(...) so they can be optimized in
#  the QC parameter/optimization UI. See the LIMITATIONS block at the bottom
#  for float / news / pre-market data caveats.
# =============================================================================


class MicroPullbackMomentum(QCAlgorithm):

    # -------------------------------------------------------------------------
    # INITIALISATION
    # -------------------------------------------------------------------------
    def Initialize(self):
        self.SetStartDate(2024, 1, 2)
        self.SetEndDate(2024, 6, 30)
        self.SetCash(25_000)
        # Work entirely in US/Eastern so "07:00-10:00 EST" is literal.
        self.SetTimeZone(TimeZones.NewYork)

        # ---------------- Adjustable inputs (optimizable) --------------------
        self.p_min_price   = float(self.GetParameter("min_price")   or 2.0)
        self.p_max_price   = float(self.GetParameter("max_price")   or 20.0)
        self.p_gap_pct     = float(self.GetParameter("gap_pct")     or 0.25)   # +25%
        self.p_rvol_mult   = float(self.GetParameter("rvol_mult")   or 5.0)    # 5x
        self.p_start_h     = int(self.GetParameter("start_hour")    or 7)
        self.p_start_m     = int(self.GetParameter("start_minute")  or 0)
        self.p_end_h       = int(self.GetParameter("end_hour")      or 10)
        self.p_end_m       = int(self.GetParameter("end_minute")    or 0)
        self.p_ema_fast    = int(self.GetParameter("ema_fast")      or 9)
        self.p_ema_mid     = int(self.GetParameter("ema_mid")       or 20)
        self.p_ema_slow    = int(self.GetParameter("ema_slow")      or 200)
        self.p_vol_spike   = float(self.GetParameter("vol_spike_mult") or 2.0) # seller spike
        self.p_rr_min      = float(self.GetParameter("rr_min")      or 2.0)    # 1:2
        self.p_risk        = float(self.GetParameter("risk_per_trade") or 0.01) # 1% acct
        self.p_max_pos     = int(self.GetParameter("max_positions") or 3)
        self.p_avg_vol_days = int(self.GetParameter("avg_vol_days") or 20)

        # ---------------- Universe -------------------------------------------
        # Minute resolution + pre-market so we can see the 07:00-09:30 action.
        self.UniverseSettings.Resolution = Resolution.Minute
        self.UniverseSettings.ExtendedMarketHours = True
        self.AddUniverse(self._coarse_filter)

        self.sd = {}              # Symbol -> SymbolData
        self.watchlist = set()    # symbols that passed gap + RVOL today

        # Build the tradeable watchlist just before the window opens, and
        # flatten everything well before the close (no overnight risk).
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(self.p_start_h, max(self.p_start_m - 5, 0)),
                         self._build_watchlist)
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(15, 55),
                         self._flatten_all)

        self.SetWarmUp(timedelta(days=3))

    # -------------------------------------------------------------------------
    # UNIVERSE — coarse screen (runs daily, on prior-day data)
    # -------------------------------------------------------------------------
    def _coarse_filter(self, coarse):
        # Small-cap price band + must have real liquidity; keep the most active.
        candidates = [c for c in coarse
                      if c.HasFundamentalData is False or True  # small caps often lack it
                      and c.Price >= self.p_min_price
                      and c.Price <= self.p_max_price
                      and c.Volume > 500_000
                      and c.DollarVolume > 1_000_000]
        candidates.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in candidates[:200]]   # cap the universe size

    def OnSecuritiesChanged(self, changes):
        for sec in changes.AddedSecurities:
            sym = sec.Symbol
            if sym not in self.sd:
                self.sd[sym] = SymbolData(self, sym)
        for sec in changes.RemovedSecurities:
            sym = sec.Symbol
            if sym in self.sd:
                self.sd[sym].dispose()
                self.sd.pop(sym, None)
            self.watchlist.discard(sym)

    # -------------------------------------------------------------------------
    # WATCHLIST — gap + RVOL screen (runs right before the trading window)
    # -------------------------------------------------------------------------
    def _build_watchlist(self):
        self.watchlist.clear()
        for sym, sd in self.sd.items():
            # Previous daily close vs today's session open (gap %).
            hist = self.History(sym, self.p_avg_vol_days + 1, Resolution.Daily)
            if hist.empty or len(hist) < 2:
                continue
            closes = hist['close'].values
            vols   = hist['volume'].values
            prev_close = float(closes[-1])
            if prev_close <= 0:
                continue

            price_now = self.Securities[sym].Price
            if price_now <= 0:
                continue
            gap = (price_now - prev_close) / prev_close

            # RVOL ~= today's cumulative volume so far / average daily volume.
            avg_vol = float(vols[-self.p_avg_vol_days:].mean())
            vol_today = self.Securities[sym].Volume  # session volume so far
            rvol = (vol_today / avg_vol) if avg_vol > 0 else 0.0

            sd.prev_close = prev_close
            sd.gap = gap
            sd.rvol = rvol
            sd.hod = price_now

            if (self.p_min_price <= price_now <= self.p_max_price
                    and gap >= self.p_gap_pct
                    and rvol >= self.p_rvol_mult):
                self.watchlist.add(sym)

        if self.watchlist:
            self.Log(f"[{self.Time:%Y-%m-%d}] watchlist: "
                     + ", ".join(s.Value for s in self.watchlist))

    # -------------------------------------------------------------------------
    # MAIN LOOP
    # -------------------------------------------------------------------------
    def OnData(self, data):
        if self.IsWarmingUp:
            return

        for sym in list(self.watchlist):
            if sym not in data.Bars:
                continue
            sd = self.sd.get(sym)
            if sd is None or not sd.ready():
                continue
            bar = data.Bars[sym]
            sd.update(bar)                         # roll bars, update HOD

            invested = self.Portfolio[sym].Invested
            if invested:
                self._manage_open(sd, bar)         # exits on open positions
            elif self._in_window() and len(self.watchlist) and self._slots_free():
                self._try_enter(sd, bar)           # look for a new entry

    # -------------------------------------------------------------------------
    # SETUP + ENTRY (the micro pullback)
    # -------------------------------------------------------------------------
    def _setup_valid(self, sd, bar):
        """Trend/context pre-conditions (Section 3)."""
        price = bar.Close
        e9, e20, e200 = sd.ema9.Current.Value, sd.ema20.Current.Value, sd.ema200.Current.Value
        macd_line = sd.macd.Current.Value
        macd_sig  = sd.macd.Signal.Current.Value
        trend_5m_ok = sd.ema9_5m.Current.Value > sd.ema20_5m.Current.Value  # 5-min trend

        return (price > sd.vwap.Current.Value                 # above VWAP
                and e9 > e20 > e200                           # bullish EMA stack
                and macd_line > 0 and macd_line > macd_sig    # MACD +, above signal
                and trend_5m_ok)

    def _try_enter(self, sd, bar):
        if not self._setup_valid(sd, bar):
            return
        pb = sd.detect_micro_pullback()               # -> (pb_high, pb_low) or None
        if pb is None:
            return
        pb_high, pb_low = pb

        # Entry trigger: price breaks above the last red candle's high.
        if bar.High < pb_high:
            return

        entry = pb_high                                # stop-limit trigger level
        stop  = pb_low                                 # Section 5: stop @ pullback low
        risk  = entry - stop
        if risk <= 0:
            return

        # R:R gate — the HOD target must offer at least 1:rr_min (Section 5).
        target = sd.hod
        reward = target - entry
        if reward < self.p_rr_min * risk:
            return

        # Risk-based sizing: lose p_risk of the account if stopped.
        qty = int((self.Portfolio.TotalPortfolioValue * self.p_risk) / risk)
        if qty <= 0:
            return

        # Enter (market ~ the stop trigger firing). Record the trade plan.
        self.MarketOrder(sym := sd.symbol, qty)
        sd.stop_price = stop
        sd.tp1 = target
        sd.took_tp1 = False
        sd.entry = entry
        self.Log(f"ENTER {sym.Value} @~{entry:.2f} stop {stop:.2f} tp1(HOD) {target:.2f} "
                 f"R:R {reward/risk:.1f} qty {qty}")

    # -------------------------------------------------------------------------
    # POSITION MANAGEMENT (Sections 5 & 6)
    # -------------------------------------------------------------------------
    def _manage_open(self, sd, bar):
        sym = sd.symbol
        pos = self.Portfolio[sym]
        price = bar.Close

        # --- hard stop: pullback low ---
        if sd.stop_price is not None and bar.Low <= sd.stop_price:
            self.Liquidate(sym, tag="STOP pullback low")
            sd.reset_trade()
            return

        # --- TP1: sell 50% at the High of Day ---
        if (not sd.took_tp1) and sd.tp1 is not None and bar.High >= sd.tp1:
            half = int(abs(pos.Quantity) * 0.5)
            if half > 0:
                self.MarketOrder(sym, -half, tag="TP1 50% @ HOD")
            sd.took_tp1 = True
            # move stop to breakeven on the runner
            sd.stop_price = max(sd.stop_price or 0, sd.entry)
            return

        # --- dynamic emergency exits on the remaining shares (Section 6) ---
        macd_bearish_cross = sd.prev_hist is not None and sd.prev_hist > 0 and \
            (sd.macd.Current.Value - sd.macd.Signal.Current.Value) <= 0
        close_below_ema9 = bar.Close < sd.ema9.Current.Value
        seller_spike = (bar.Close < bar.Open) and sd.avg_vol() > 0 and \
            (bar.Volume >= self.p_vol_spike * sd.avg_vol())

        if macd_bearish_cross:
            self.Liquidate(sym, tag="EXIT MACD bearish cross"); sd.reset_trade(); return
        if close_below_ema9:
            self.Liquidate(sym, tag="EXIT close < EMA9"); sd.reset_trade(); return
        if seller_spike:
            self.Liquidate(sym, tag="EXIT seller volume spike"); sd.reset_trade(); return

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------
    def _in_window(self):
        t = self.Time
        after_open = (t.hour, t.minute) >= (self.p_start_h, self.p_start_m)
        before_cut = (t.hour, t.minute) < (self.p_end_h, self.p_end_m)
        return after_open and before_cut

    def _slots_free(self):
        held = sum(1 for kv in self.Portfolio if kv.Value.Invested)
        return held < self.p_max_pos

    def _flatten_all(self):
        self.Liquidate(tag="EOD flatten")
        for sd in self.sd.values():
            sd.reset_trade()


# =============================================================================
#  PER-SYMBOL STATE  (indicators, consolidators, rolling bars, trade plan)
# =============================================================================
class SymbolData:
    def __init__(self, algo, symbol):
        self.algo = algo
        self.symbol = symbol

        # 1-minute indicators
        self.vwap  = algo.VWAP(symbol)                                   # intraday, daily-anchored
        self.ema9  = algo.EMA(symbol, algo.p_ema_fast, Resolution.Minute)
        self.ema20 = algo.EMA(symbol, algo.p_ema_mid,  Resolution.Minute)
        self.ema200 = algo.EMA(symbol, algo.p_ema_slow, Resolution.Minute)
        self.macd  = algo.MACD(symbol, 12, 26, 9, MovingAverageType.Exponential, Resolution.Minute)

        # 5-minute trend confirmation (EMA9 vs EMA20 on a 5-min consolidator)
        self.ema9_5m  = ExponentialMovingAverage(algo.p_ema_fast)
        self.ema20_5m = ExponentialMovingAverage(algo.p_ema_mid)
        self._cons5 = TradeBarConsolidator(timedelta(minutes=5))
        algo.RegisterIndicator(symbol, self.ema9_5m,  self._cons5)
        algo.RegisterIndicator(symbol, self.ema20_5m, self._cons5)
        algo.SubscriptionManager.AddConsolidator(symbol, self._cons5)

        # rolling window of the last completed 1-min bars (pullback detection)
        self.bars = RollingWindow[TradeBar](12)

        # session context
        self.prev_close = None
        self.gap = 0.0
        self.rvol = 0.0
        self.hod = 0.0

        # trade plan
        self.entry = None
        self.stop_price = None
        self.tp1 = None
        self.took_tp1 = False
        self.prev_hist = None

    # ---- lifecycle ----
    def ready(self):
        return (self.vwap.IsReady and self.ema9.IsReady and self.ema20.IsReady
                and self.ema200.IsReady and self.macd.IsReady
                and self.ema9_5m.IsReady and self.ema20_5m.IsReady)

    def update(self, bar):
        self.bars.Add(bar)
        self.hod = max(self.hod, bar.High)
        self.prev_hist = self.macd.Current.Value - self.macd.Signal.Current.Value

    def avg_vol(self, n=5):
        if self.bars.Count == 0:
            return 0.0
        n = min(n, self.bars.Count)
        return sum(self.bars[i].Volume for i in range(n)) / n

    def reset_trade(self):
        self.entry = self.stop_price = self.tp1 = None
        self.took_tp1 = False

    def dispose(self):
        self.algo.SubscriptionManager.RemoveConsolidator(self.symbol, self._cons5)

    # ---- the micro pullback (Section 4) ----
    def detect_micro_pullback(self):
        """Impulse (up) -> 1 or 2 low-volume red candles. Returns (pb_high, pb_low)
        of the red pullback, else None. Index 0 = most recent completed bar."""
        if self.bars.Count < 5:
            return None
        b = [self.bars[i] for i in range(self.bars.Count)]

        # 1) the pullback = the most recent run of 1-2 red candles
        red = []
        k = 0
        while k < len(b) and b[k].Close < b[k].Open and len(red) < 2:
            red.append(b[k]); k += 1
        if len(red) < 1:
            return None
        # a 3rd consecutive red candle => not a *micro* pullback
        if k < len(b) and b[k].Close < b[k].Open and len(red) == 2:
            return None

        # 2) the impulse = the 3 bars preceding the pullback, must be up
        impulse = b[k:k + 3]
        if len(impulse) < 2:
            return None
        greens = sum(1 for x in impulse if x.Close >= x.Open)
        impulse_up = impulse[0].Close > impulse[-1].Close and greens >= 1
        if not impulse_up:
            return None

        # 3) pullback volume must be BELOW the impulse average volume
        imp_vol = sum(x.Volume for x in impulse) / len(impulse)
        pb_vol  = sum(x.Volume for x in red) / len(red)
        if imp_vol <= 0 or pb_vol >= imp_vol:
            return None

        pb_high = max(x.High for x in red)
        pb_low  = min(x.Low for x in red)
        return pb_high, pb_low


# =============================================================================
#  PLATFORM LIMITATIONS  (read before trusting a backtest)
# =============================================================================
#  FLOAT filter:  QuantConnect has NO reliable free "shares float" field. Coarse/
#    Fine fundamentals (Morningstar) expose shares outstanding, not free float,
#    and coverage for sub-$20 small caps is poor. Ross's "<10-20M float" rule
#    CANNOT be reproduced faithfully on QC without an external float dataset
#    (e.g. an imported custom data source). This algo therefore proxies "runner"
#    quality with the gap + RVOL + price filters only.
#
#  NEWS / catalyst filter:  QC has Tiingo/Benzinga news datasets but they are
#    add-ons (extra cost / subscription) and thin on micro caps. The "must have a
#    catalyst" rule is NOT implemented here — add Benzinga news + a keyword filter
#    if you subscribe.
#
#  PRE-MARKET DATA:  ExtendedMarketHours minute data for illiquid small caps is
#    sparse/gappy on QC's default feed. The 07:00-09:30 signals will be lower
#    quality than a real SIP feed (IBKR/Polygon). Gap% is measured vs the prior
#    DAILY close; RVOL is an approximation (session volume / 20-day avg).
#
#  FILLS / SLIPPAGE:  entries are modeled as MarketOrders at the trigger; real
#    small-cap pre-market spreads/slippage will make live results worse. Set a
#    realistic slippage & fee model before drawing conclusions.
# =============================================================================
