#!/usr/bin/env python3
"""
IBKR Broker — real-time prices AND live order placement on one IBKR session.

Used by the LONG Terminator. A single reconnecting ib_insync connection serves
both the price feed (good pre-market data) and order execution on the REAL
account (port 4001).

SAFETY MODEL (real money):
  - `allow_live=False` by default -> orders are only logged, never transmitted.
  - Even with `allow_live=True`, each order call still honors `dry_run`.
  - Orders are ALWAYS marketable LIMIT with `outsideRth=True` so they fill in
    pre-market / after-hours (plain MARKET orders are rejected outside RTH).
    A buy limit sits slightly ABOVE the ref price, a sell slightly BELOW -> fill.

Usage (self-test, no real order):
    python -m execution.ibkr_broker            # connect, show account/positions, dry-run buy
"""
import logging
from typing import Dict, List, Optional

logging.getLogger('ib_insync').setLevel(logging.CRITICAL)

from ib_insync import IB, Stock, LimitOrder, MarketOrder

from bot import config

MARKETABLE = 0.005   # 0.5% price cushion to make a limit order fill immediately
DEFAULT_CLIENT_ID = 31  # LONG bot range (30+); scanner uses random 3000-3999


class IBKRBroker:
    def __init__(self, host: str = config.IBKR_HOST, port: int = config.IBKR_PORT_LIVE,
                 client_id: int = DEFAULT_CLIENT_ID, allow_live: bool = False):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.allow_live = allow_live
        self.ib: Optional[IB] = None
        self.log: list = []

    # ---- connection (auto-reconnect: IB Gateway restarts daily on 2FA) ----
    def _ensure(self) -> Optional[IB]:
        if self.ib is not None and self.ib.isConnected():
            return self.ib
        try:
            if self.ib:
                self.ib.disconnect()
        except Exception:
            pass
        try:
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
            # handler RÉACTIVÉ 10/09 : ATTT (non halté, 60k actions/min) a eu 2 ordres MKT
            # annulés sans fill -> il faut voir le motif de rejet IBKR.
            self.ib.errorEvent += self._on_error
        except Exception as e:
            self._log('CONNECT_ERR', str(e))
            self.ib = None
        return self.ib

    def _on_error(self, reqId, errorCode, errorString, contract):
        # 2104/2106/2158 = messages d'info "market data farm OK" -> on ignore
        if errorCode in (2104, 2106, 2107, 2158, 2119):
            return
        # 162 "scanner subscription cancelled" = normal après reqScannerData (bénin)
        if errorCode == 162 and 'scanner subscription cancelled' in (errorString or '').lower():
            return
        sym = getattr(contract, 'symbol', '') if contract else ''
        print(f"    ⚠️ IBKR err {errorCode} {sym}: {errorString}")

    def connect(self) -> bool:
        return self._ensure() is not None

    def disconnect(self):
        try:
            if self.ib:
                self.ib.disconnect()
        except Exception:
            pass

    def _log(self, *a):
        self.log.append(a)

    def _contract(self, ticker: str) -> Optional[Stock]:
        ib = self._ensure()
        if not ib:
            return None
        c = Stock(ticker, 'SMART', 'USD')
        try:
            ib.qualifyContracts(c)
            return c
        except Exception as e:
            self._log('QUALIFY_ERR', ticker, str(e))
            return None

    # ---- account / positions (source of truth for the Terminator) ----
    def account_summary(self) -> Dict[str, str]:
        ib = self._ensure()
        if not ib:
            return {}
        return {v.tag: v.value for v in ib.accountSummary()}

    def positions(self) -> Dict[str, dict]:
        """{'AAPL': {'shares': 1, 'avg': 311.2}} — shares >0 long, <0 short."""
        ib = self._ensure()
        if not ib:
            return {}
        out = {}
        for p in ib.positions():
            sym = p.contract.symbol.upper()
            sh = int(p.position)
            if sh != 0:
                out[sym] = {'shares': sh, 'avg': float(p.avgCost or 0)}
        return out

    def protected_symbols(self) -> set:
        """Symboles ayant un ordre de VENTE actif chez IBKR (STOP ou TRAIL vivant).
        Source de vérité du broker -> permet de détecter une position non protégée
        après un redémarrage du bot ou une annulation par IBKR."""
        ib = self._ensure()
        if not ib:
            return set()
        out = set()
        try:
            ib.reqAllOpenOrders()
            ib.sleep(1)
            for t in ib.openTrades():
                st = t.orderStatus.status
                if (t.order.action == 'SELL'
                        and st not in ('Cancelled', 'ApiCancelled', 'Filled', 'Inactive')):
                    out.add(t.contract.symbol.upper())
        except Exception as e:
            self._log('PROT_ERR', str(e))
        return out

    # ---- prices (real-time, works pre-market) ----
    def prices(self, tickers: List[str]) -> Dict[str, float]:
        ib = self._ensure()
        if not ib or not ib.isConnected():
            return {}
        reqs = []
        for tk in tickers:
            c = self._contract(tk)
            if c:
                reqs.append((tk, c, ib.reqMktData(c, '', False, False)))
        ib.sleep(1.5)  # let prices populate
        out = {}
        for tk, c, t in reqs:
            px = t.last if (t.last and t.last > 0) else (t.close if (t.close and t.close > 0) else None)
            if px:
                out[tk] = float(px)
            try:
                ib.cancelMktData(c)
            except Exception:
                pass
        return out

    def quote(self, ticker: str) -> Dict[str, Optional[float]]:
        """Last / bid / ask for one ticker (for marketable order pricing)."""
        ib = self._ensure()
        if not ib:
            return {}
        c = self._contract(ticker)
        if not c:
            return {}
        t = ib.reqMktData(c, '', False, False)
        ib.sleep(1.5)
        q = {
            'last': t.last if (t.last and t.last > 0) else None,
            'bid': t.bid if (t.bid and t.bid > 0) else None,
            'ask': t.ask if (t.ask and t.ask > 0) else None,
            'close': t.close if (t.close and t.close > 0) else None,
        }
        try:
            ib.cancelMktData(c)
        except Exception:
            pass
        return q

    # ---- intraday bars (1-min, pre-market included, fresh each cycle) ----
    def intraday_1min(self, ticker: str, duration: str = '7200 S') -> List[dict]:
        """
        Recent 1-min TRADES bars including pre-market/after-hours (useRTH=False).
        Returns [{'t': datetime, 'o','h','l','c','v'}, ...] oldest->newest.
        Fetched fresh each cycle (no streaming state) to stay restart-safe.
        """
        ib = self._ensure()
        c = self._contract(ticker)
        if not ib or not c:
            return []
        try:
            bars = ib.reqHistoricalData(
                c, endDateTime='', durationStr=duration,
                barSizeSetting='1 min', whatToShow='TRADES',
                useRTH=False, formatDate=2,
            )
        except Exception as e:
            self._log('BARS_ERR', ticker, str(e))
            return []
        return [{'t': b.date, 'o': b.open, 'h': b.high, 'l': b.low,
                 'c': b.close, 'v': b.volume} for b in bars]

    # ---- orders (marketable LIMIT, outsideRth so it fills pre-market) ----
    def _place(self, ticker: str, action: str, qty: int, limit: float,
               tag: str, dry_run: bool, tif: str = 'DAY'):
        limit = round(limit, 2)   # penny tick (évite rejet err 201 sous-penny)
        blocked = dry_run or not self.allow_live
        self._log(tag, ticker, f'{action} {qty}@{limit}',
                  'DRY' if blocked else 'LIVE')
        if blocked:
            return {'status': 'dry_run', 'ticker': ticker, 'action': action,
                    'qty': qty, 'limit': limit}
        ib = self._ensure()
        c = self._contract(ticker)
        if not ib or not c:
            return {'status': 'error', 'reason': 'no_connection_or_contract'}
        order = LimitOrder(action, qty, limit)
        order.tif = tif           # 'DAY' par défaut ; 'GTC' pour survivre à la nuit (sortie forcée)
        order.outsideRth = True   # allow pre-market / after-hours fills
        trade = ib.placeOrder(c, order)
        return {'status': 'submitted', 'ticker': ticker, 'action': action,
                'qty': qty, 'limit': limit, 'trade': trade}

    def buy(self, ticker: str, qty: int, ref_price: float,
            tag: str = 'BUY', dry_run: bool = False, tif: str = 'DAY'):
        """Entrée en LIMITE MARKETABLE (limite ~0,5% AU-DESSUS du ref -> fill quasi immédiat,
        slippage PLAFONNÉ, et exécutable en pré-marché/extended contrairement à un ordre marché).
        CHANGÉ 23/09 : l'edge post-open est trop fin pour un ordre marché — la recherche montre
        qu'il MEURT dès +0,5%/côté de slippage ; un marché sur small-cap dépasse ça facilement.
        Si ça ne remplit pas (halt / prix qui fuit), le terminator annule/retente (FILL_TIMEOUT)."""
        return self._place(ticker, 'BUY', qty,
                            ref_price * (1 + MARKETABLE), tag, dry_run, tif=tif)

    def sell(self, ticker: str, qty: int, ref_price: float,
             tag: str = 'SELL', dry_run: bool = False, tif: str = 'DAY'):
        """Marketable sell: limit slightly BELOW ref -> immediate fill. tif='GTC' pour
        une sortie forcée qui survit RTH -> extended -> prochaine ouverture."""
        return self._place(ticker, 'SELL', qty,
                            ref_price * (1 - MARKETABLE), tag, dry_run, tif=tif)

    def cancel_all(self):
        ib = self._ensure()
        if ib:
            ib.reqGlobalCancel()


# ---------------------------------------------------------------------------
def _self_test():
    print("Connecting to IBKR (live port 4001, clientId 31)...")
    broker = IBKRBroker(allow_live=False)  # SAFE: no real orders in self-test
    if not broker.connect():
        print("  ✗ Could not connect. Is IB Gateway running on 4001?")
        return
    print("  ✓ Connected.")

    summ = broker.account_summary()
    net = summ.get('NetLiquidation', '?')
    print(f"  Account NetLiquidation: {net}")
    print(f"  Open positions: {broker.positions() or '{}'}")

    q = broker.quote('AAPL')
    print(f"  AAPL quote: {q}")

    print("\n  DRY-RUN order (nothing is transmitted):")
    ref = q.get('last') or q.get('close') or 100.0
    res = broker.buy('AAPL', 1, ref, tag='TEST', dry_run=True)
    print(f"    -> {res}")
    for entry in broker.log:
        print(f"    log: {entry}")

    broker.disconnect()
    print("\n  Disconnected. Phase 1 OK (prices + positions + dry-run order).")


if __name__ == '__main__':
    _self_test()
