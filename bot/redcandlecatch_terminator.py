#!/usr/bin/env python3
"""
RedCandleCatch — paper / journal (stratégie validée sur 8 mois de backtest).

Stratégie : sur les gros gappers (gap pré-marché ≥50%, prix ≥3$), pendant la
séance régulière (09:30–16:30), ENTRER LONG après une bougie 1-min qui chute de
≥3% (achat du creux, ordre LIMITE), et SORTIR sur un TRAILING STOP de 6% depuis
le plus haut. Plusieurs positions possibles (1 par ticker, 1 titre chacune,
1 trade/ticker/jour). Défaut = paper/journal ; avec --live = VRAIS ORDRES + stop
dur -10% chez IBKR. Voir memory/no-robust-long-edge.md.

Usage:
    python -m bot.redcandlecatch_terminator                 # boucle paper (journal seul)
    python -m bot.redcandlecatch_terminator --live          # VRAIS ORDRES (1 titre/trade)
    python -m bot.redcandlecatch_terminator --once          # un cycle (debug)
    python -m bot.redcandlecatch_terminator --tickers ABC,XYZ   # watchlist fixe
"""
import argparse, csv, json, time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from zoneinfo import ZoneInfo; ET = ZoneInfo('America/New_York')
except Exception:
    ET = None

from execution.ibkr_broker import IBKRBroker
from bot import redcandlecatch_scan as wscan
from bot import eligible

# ---- paramètres de la stratégie (issus du backtest) ----
# Config validée 2026-09-11 (backtest 9 mois) : gap 10-20% + dip -5% + trail 2%
# -> +1,97%/tr, win 74%, pf 1,93, t-stat 7,34 (vs +0,69% pour l'ancienne config).
GAP_MIN, GAP_MAX = wscan.GAP_MIN, wscan.GAP_MAX   # fourchette de gap (source: redcandlecatch_scan)
PRICE_MIN, PRICE_MAX = 3.0, 20.0
DIP = 0.05              # bougie de -5% déclenche l'entrée (gappers PM). 18/09 : passé de -6%
                        # à -5% après l'analyse OOS + portefeuille. Le -6% a la meilleure
                        # expectancy/trade, MAIS -5% donne PLUS de trades (4,1 vs 2,7/jour) et
                        # un meilleur rendement COMPOSÉ (qualité+fréquence). OOS test -5% :
                        # +1,39%/tr, win 72%, pf 1,63, t=3,8. Choix fréquence+composé (Martin).
# --- DIP ADAPTATIF (16/09) : le seuil dépend du MOMENT D'ÉLIGIBILITÉ du ticker :
#  - gapper éligible AVANT l'ouverture (dans la liste avant 09:31) -> dip -5% (DIP)
#    = micro-cap PM survolatile (validé OOS sur candles.parquet, gap 10-20).
#  - ticker ajouté APRÈS l'ouverture (post-open runner) -> dip -1,5% (DIP_LIQUID)
#    = plus calme. 18/09 : -1,5% domine -2% en OOS (exp +2,19%, pf 2,48, t=10,8, 9,6 tr/j
#    vs +1,97%/2,13/6,7 à -2%). Contraste avec le PM : le post-open veut un dip LÉGER.
# On lit l'heure 'added' du fichier de signaux (heure de 1re éligibilité).
DIP_LIQUID = 0.015      # dip des runners POST-OUVERTURE (ajoutés après 09:31)
PREOPEN_CUTOFF = '09:31'  # éligible avant cette heure = gapper pré-marché -> DIP (-6%)
# TRADE_PM (18/09) : on NE TRADE PLUS les gappers PM (edge intrinsèquement faible : n=86/8mois,
# exp +0,69%, R/R 0,55 -> net-négatif après commissions ; l'edge vit dans le post-open). On
# CONTINUE de les COLLECTER (le scanner/eligibles les enregistre) pour la recherche.
TRADE_PM = False
# --- FILTRE DE LIQUIDITÉ SUR LA BOUGIE DE DIP (18/09, décision Martin) ---
# On n'entre que si la MINUTE d'entrée (bougie de dip) a brassé assez : volume × close >= seuil.
# But = FACILITÉ D'EXÉCUTION (entrer/sortir sans slippage). Le filtre du SCANNER porte sur le
# volume CUMULÉ session ; celui-ci porte sur la BOUGIE elle-même (la minute où on tire).
# Sur data non biaisée, élimine les entrées type LGHL (+4% de slippage sur bougie fine).
MIN_DIP_DOLLAR_VOL = 200_000   # $ min de dollar-volume sur la bougie de dip (0 = désactivé)
# --- sortie EN DEUX PHASES ---
STOP = 0.10             # phase 1 : STOP fixe -10% (survit au repli initial)
# ACTIVATION ADAPTATIVE (18/09) : l'effet du seuil d'activation est OPPOSÉ selon la population
# (validé 8 mois). Les gappers PM plongent fort (-5%) puis rebondissent FAIBLEMENT -> +5% optimal
# (+10% les rend NÉGATIFS, pf 0,92). Les runners post-open font un petit repli (-1,5%) et
# CONTINUENT de courir -> +10% optimal (exp +2,43->+3,08%). On choisit par moment d'éligibilité,
# comme le dip. Le seuil retenu est stocké dans pos['activate'] à l'entrée.
ACTIVATE_PM = 0.05      # gappers PM (éligible avant 09:31) : bascule phase 2 à +5%
ACTIVATE_POST = 0.10    # runners post-open (ajoutés après) : bascule à +10%
TRAIL = 0.02            # phase 2 : TRAIL natif 2% (paramètre dominant ; ne PAS descendre
                        # plus bas : sous 2% on passe sous la résolution des bougies 1-min)
FILL_TIMEOUT = 3        # cycles d'attente du fill ; sinon = halt/illiquide -> annuler + retenter
SHARES = 1              # 1 titre/trade (test live à risque minimal)
ENTRY_END = (15, 55)    # dernières entrées à 15:55 (= début de la sortie forcée, pas d'entrée tardive inutile)
RTH_OPEN, RTH_CLOSE = (9, 30), (16, 30)
# --- BACKSTOP à deux niveaux (16/09) : sortir AVANT la vraie clôture (16:00 ET) pendant
# que c'est LIQUIDE, puis filet extended si pas sorti. HARD_EXIT = sortie forcée au marché.
HARD_EXIT = (15, 55)    # 15:55 ET : vente forcée des positions encore ouvertes (marché liquide)
REG_CLOSE = (16, 0)     # clôture RÉGULIÈRE US (après = extended hours)
EXT_CLOSE = (20, 0)     # fin de l'extended hours ; au-delà on ne re-price plus (GTC déjà posé)

COMPUTED = Path(__file__).resolve().parent.parent / 'data' / 'computed'
STATE = COMPUTED / 'redcandlecatch-open.json'
JOURNAL = COMPUTED / 'redcandlecatch-journal.csv'
JOURNAL_COLS = ['date','ticker','gap','entry_time','entry','exit_time','exit','reason',
                'pnl_pct','mfe_pct','shares','dollars','mode',
                # features de sélection (pour entraîner le modèle ML long plus tard)
                'float_m','inst_pct','chart_r','volume_r','float_r','ssr']


def now_et() -> datetime:
    return datetime.now(ET) if ET else datetime.now()

def hm(t) -> tuple: return (t.hour, t.minute)
def tmin(t) -> int: return t.hour * 60 + t.minute   # minutes depuis minuit (pour l'arithmétique bougies)

def load_state() -> Dict[str, dict]:
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except Exception: return {}
    return {}

def save_state(s): STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(s, indent=2))

def append_journal(row: dict):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    new = not JOURNAL.exists()
    with JOURNAL.open('a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=JOURNAL_COLS)
        if new: w.writeheader()
        w.writerow(row)


def _today_bars(broker: IBKRBroker, tk: str) -> List[dict]:
    """Toutes les bougies 1-min d'aujourd'hui (pré-marché inclus), ET, oldest→newest."""
    raw = broker.intraday_1min(tk, duration='46800 S')      # ~13h : couvre le pré-marché depuis 16:30
    today = now_et().date(); out = []
    for b in raw:
        t = b['t'].astimezone(ET) if ET else b['t']
        if t.date() == today:
            out.append({**b, 't': t})
    return out

def _prev_close(broker: IBKRBroker, tk: str) -> Optional[float]:
    try:
        c = broker._contract(tk)
        bars = broker.ib.reqHistoricalData(c, endDateTime='', durationStr='3 D',
                                           barSizeSetting='1 day', whatToShow='TRADES',
                                           useRTH=True, formatDate=1)
        return float(bars[-2].close) if len(bars) >= 2 else None
    except Exception:
        return None

def gap_pct(broker: IBKRBroker, tk: str, today_bars: List[dict]) -> Optional[float]:
    """Gap = (plus-haut pré-marché 04:00-09:30) / clôture veille - 1, en %."""
    pm = [b for b in today_bars if (4, 0) <= hm(b['t']) < RTH_OPEN]
    if not pm: return None
    pc = _prev_close(broker, tk)
    if not pc or pc <= 0: return None
    return (max(b['h'] for b in pm) - pc) / pc * 100


def scan_candidates(broker: IBKRBroker, limit: int = 30) -> List[str]:
    """Univers Gus : TOP_PERC_GAIN small-caps <500M, prix 3-20$.
    Les filtres fins (float, PM vol, vol relatif, ratings) sont appliqués ensuite
    par redcandlecatch_scan.evaluate()."""
    try:
        from ib_insync import ScannerSubscription
        sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                                  scanCode='TOP_PERC_GAIN', numberOfRows=limit)
        sub.abovePrice = PRICE_MIN; sub.belowPrice = PRICE_MAX
        sub.marketCapBelow = wscan.MARKET_CAP_MAX          # < 500M (small caps)
        rows = broker.ib.reqScannerData(sub)
        return [r.contractDetails.contract.symbol for r in rows[:limit]]
    except Exception as e:
        print(f"scan error: {e}")
        return []


class RedCandleCatchTerminator:
    def __init__(self, broker: IBKRBroker, tickers: Optional[List[str]] = None,
                 live: bool = False):
        self.broker = broker
        self.fixed = tickers
        self.live = live                            # True = vrais ordres IBKR
        self.candidates: List[str] = tickers or []
        self.gap_ok: Dict[str, float] = {}          # ticker -> gap% (validés ≥50)
        self.state = load_state()                   # 1 position max
        self.done: set = set()                      # tickers déjà tradés aujourd'hui (1/jour)
        self.last_bar: Dict[str, object] = {}        # ticker -> horodatage de la dernière bougie CLÔTURÉE déjà évaluée (dédup : 1 bougie = 1 décision)
        self.orders: Dict[str, object] = {}         # ticker -> ordre de protection courant (STOP ou TRAIL)
        self.evals: Dict[str, dict] = {}             # ticker -> résultat redcandlecatch_scan.evaluate (ratings/flags)
        self._protected: set = set()                 # symboles avec un ordre de vente vivant (réconciliation)
        self.day = now_et().date()

    def _stop_at(self, tk: str, shares: int, stop_price: float):
        """Pose un STOP (vente au marché sur touche) à un prix ABSOLU, arrondi au penny.
        Brique unique de protection : le stop FIXE (phase 1) ET le trail géré (phase 2)
        sont des stops à un prix calculé par le BOT depuis le prix SIGNAL / le sommet des
        bougies. On n'utilise PLUS le trail natif IBKR : il ancrait au prix de POSE et ne
        suivait pas le sommet du graphique (cas LUXE 16/09). Arrondi au penny pour éviter
        le rejet err 201 (sous-penny)."""
        if not self.live:
            return None
        try:
            from ib_insync import StopOrder
            c = self.broker._contract(tk)
            o = StopOrder('SELL', shares, round(stop_price, 2)); o.tif = 'DAY'; o.outsideRth = True
            return self.broker.ib.placeOrder(c, o)
        except Exception as e:
            print(f"    ⚠️ STOP ÉCHEC {tk}: {e}")
            return None

    def _fixed_stop(self, tk: str, shares: int, entry: float):
        """Phase 1 : STOP fixe à -STOP% du prix SIGNAL (entry)."""
        o = self._stop_at(tk, shares, entry * (1 - STOP))
        if o is not None:
            print(f"    STOP fixe -{STOP*100:.0f}% posé @ {entry*(1-STOP):.2f}")
        return o

    def _trailing_stop(self, tk: str, shares: int, ref: float = 0.0):
        """Phase 2 : ordre TRAIL NATIF IBKR à TRAIL% (géré par IBKR, suit le sommet).
        On ne fournit QUE `trailingPercent` (fournir trailStopPrice fait rejeter err 201,
        cf research/test_trail_covered.py 14/09). IBKR gère le trailing. `ref` inutilisé."""
        if not self.live:
            return None
        try:
            from ib_insync import Order
            c = self.broker._contract(tk)
            o = Order(action='SELL', totalQuantity=shares, orderType='TRAIL',
                      trailingPercent=round(TRAIL * 100, 2), tif='DAY', outsideRth=True)
            trade = self.broker.ib.placeOrder(c, o)
            print(f"    TRAIL natif {TRAIL*100:.0f}% posé (géré par IBKR)")
            return trade
        except Exception as e:
            print(f"    ⚠️ TRAIL ÉCHEC {tk}: {e}")
            return None

    def _cancel_order(self, tk: str):
        o = self.orders.pop(tk, None)
        if o is not None:
            try: self.broker.ib.cancelOrder(o.order)
            except Exception as e: print(f"    ⚠️ annulation ordre {tk}: {e}")

    def _order_diag(self, tk: str) -> str:
        """Statut réel de l'ordre d'achat + messages (raison de rejet/halt)."""
        tr = self.orders.get(tk)
        if tr is None:
            return "pas d'objet ordre (non soumis ?)"
        try:
            st = tr.orderStatus.status
            msgs = "; ".join(f"{e.status}:{e.message}" for e in getattr(tr, 'log', []) if e.message)
            return f"status={st} filled={tr.orderStatus.filled} remaining={tr.orderStatus.remaining}" + (f" | {msgs}" if msgs else "")
        except Exception as e:
            return f"lecture statut impossible: {e}"

    def _last_buy_fill(self, tk: str):
        """Prix RÉELLEMENT payé à l'achat (pour journaliser l'entrée vraie, pas le
        prix du signal — sinon le forward-test surestime la performance)."""
        try:
            px = None
            for f in self.broker.ib.fills():
                if f.contract.symbol.upper() == tk and f.execution.side == 'BOT':
                    px = float(f.execution.price)
            return px
        except Exception:
            return None

    def _last_sell_fill(self, tk: str):
        """Prix du dernier remplissage VENTE de ce ticker (pour journaliser la sortie)."""
        try:
            px = None
            for f in self.broker.ib.fills():
                if f.contract.symbol.upper() == tk and f.execution.side == 'SLD':
                    px = float(f.execution.price)
            return px
        except Exception:
            return None

    def _refresh(self):
        """L'exécuteur NE SCANNE PLUS : il lit la liste d'éligibles écrite par le
        dashboard/scanner (fichier de signaux, sticky). Une fois un ticker reçu il
        entre dans gap_ok/evals et y reste (sticky côté fichier).
        Mode --tickers : évalue lui-même la liste fixe, pour debug sans dashboard."""
        if self.fixed:
            for tk in self.fixed:
                if tk in self.gap_ok or tk in self.state:
                    continue
                tb = _today_bars(self.broker, tk)
                if not tb:
                    continue
                g = gap_pct(self.broker, tk, tb)
                price = tb[-1]['c']
                pmb = [b for b in tb if (4, 0) <= hm(b['t']) < RTH_OPEN]
                pm_vol = sum(b['v'] for b in pmb)
                pm_min = sum(1 for b in pmb if b['v'] > 0)
                ev = wscan.evaluate(self.broker, tk, g, price, pm_vol, pm_min)
                if ev['eligible']:
                    self.gap_ok[tk] = round(g, 1) if g else ''
                    self.evals[tk] = ev
                    print(f"    ✓ {tk} retenu (mode --tickers) — {ev['reason']}")
            self.candidates = list(self.fixed)
            return
        # mode normal : lire le fichier de signaux du dashboard/scanner
        elig = eligible.load()
        for tk, info in elig.items():
            if tk in self.gap_ok or tk in self.state:
                continue
            self.gap_ok[tk] = info.get('gap', '')
            self.evals[tk] = {'float_shares': info.get('float_shares'), 'inst_pct': info.get('inst_pct'),
                              'chart_rating': info.get('chart_rating'), 'volume_rating': info.get('volume_rating'),
                              'float_rating': info.get('float_rating'), 'ssr': info.get('ssr'),
                              'added': info.get('added')}   # heure de 1re éligibilité -> choix du dip
            print(f"[{now_et():%H:%M}] ← {tk} reçu du scanner (gap {info.get('gap')}%, {info.get('reason','')})")
        self.candidates = list(elig)

    def cycle(self):
        t = now_et()
        if t.date() != self.day:                     # nouveau jour -> reset
            self.day = t.date(); self.done.clear(); self.gap_ok.clear(); self.evals.clear(); self.last_bar.clear()
        if hm(t) < RTH_OPEN:
            return                                   # avant l'ouverture : rien
        # BUG corrigé 16/09 : avant, le cycle sortait dès 16:30 -> le backstop ne se
        # déclenchait JAMAIS -> positions gardées overnight à nu. Maintenant : après la
        # clôture, on CONTINUE de tourner tant qu'il reste des positions à solder ; on
        # n'idle que lorsque tout est plat.
        if hm(t) >= RTH_CLOSE and not self.state:
            return
        self.broker.connect()                        # reconnecte si besoin (survit aux restarts Gateway)
        self._refresh()
        watch = list(dict.fromkeys(list(self.gap_ok) + list(self.state)))
        # protections vivantes chez IBKR (1 appel/cycle) -> base de la réconciliation
        self._protected = self.broker.protected_symbols() if (self.live and self.state) else set()
        cur = tmin(t)                                # minute courante ET (en minutes totales)
        for tk in watch:
            bars = [b for b in _today_bars(self.broker, tk) if RTH_OPEN <= hm(b['t']) < RTH_CLOSE]
            # SYNCHRO BOUGIES : ne garder que les bougies STRICTEMENT CLÔTURÉES (minute < minute
            # courante). On DROP la bougie en formation par HORODATAGE — plus de dépendance à la
            # position bars[-2] (fragile : IBKR omet les minutes sans trade sur les titres peu
            # liquides -> bars[-2] pouvait pointer une mauvaise bougie ou une bougie partielle,
            # d'où des entrées sur un -5% transitoire jamais clôturé, ex AKAN 18/09).
            cbars = [b for b in bars if tmin(b['t']) < cur]
            if len(cbars) < 1:
                continue
            if tk in self.state:
                self._manage(tk, cbars, t)
            elif tk not in self.done and hm(t) < ENTRY_END:   # multi-positions : 1 par ticker
                self._maybe_enter(tk, cbars, cur)

    def _maybe_enter(self, tk: str, cbars: List[dict], cur: int):
        r = cbars[-1]                                # dernière bougie CLÔTURÉE (sélection par HORODATAGE)
        # FRAÎCHEUR : n'agir que sur la bougie qui vient JUSTE de clôturer (minute = cur-1).
        # Une bougie plus vieille = signal périmé (titre peu liquide, minutes sans trade) : on
        # n'entre PAS sur un dip d'il y a plusieurs minutes. Le cycle tourne toutes les 20s
        # (3x/minute) -> on attrape toujours la bougie fraîche.
        if tmin(r['t']) != cur - 1:
            return
        # DÉDUP : 1 bougie clôturée = 1 décision (sinon les 3 cycles de la minute la ré-évaluent).
        if self.last_bar.get(tk) == r['t']:
            return
        self.last_bar[tk] = r['t']
        # DIP selon le MOMENT d'éligibilité (pas le volume) : éligible AVANT 09:31 = gapper
        # pré-marché -> -6% ; ajouté APRÈS = runner post-open -> -2%. (added inconnu -> -6% par
        # sécurité, ex mode --tickers.)
        added = (self.evals.get(tk, {}) or {}).get('added') or ''
        premarket = (not added) or (added < PREOPEN_CUTOFF)
        eff_dip = DIP if premarket else DIP_LIQUID
        if not (r['o'] > 0 and (r['c'] - r['o']) / r['o'] <= -eff_dip and r['c'] >= PRICE_MIN):
            return
        # PM DÉSACTIVÉ (18/09) : on ne trade plus les gappers pré-marché (edge faible). On logue
        # quand même l'opportunité (pour la traçabilité), mais on n'entre pas. Collecte inchangée.
        if premarket and not TRADE_PM:
            print(f"[{now_et():%H:%M}] SKIP {tk} bougie {r['t']:%H:%M} gapper PM (dip -{eff_dip*100:.0f}%, "
                  f"éligible {added or '?'}) -> PM désactivé (post-open seulement)")
            return
        # FILTRE LIQUIDITÉ sur la BOUGIE DE DIP : la minute d'entrée doit avoir brassé assez pour
        # un fill propre (sinon slippage, ex LGHL). volume × close de la bougie de dip elle-même.
        dip_dvol = (r.get('v') or 0) * r['c']
        if MIN_DIP_DOLLAR_VOL and dip_dvol < MIN_DIP_DOLLAR_VOL:
            print(f"[{now_et():%H:%M}] SKIP {tk} bougie {r['t']:%H:%M} dip OK mais illiquide "
                  f"(${dip_dvol/1e3:.0f}K < ${MIN_DIP_DOLLAR_VOL/1e3:.0f}K) -> pas d'entrée")
            return
        entry = r['c']; shares = SHARES
        mode = 'LIVE' if self.live else 'PAPER'
        # LOG DE PREUVE : les dernières bougies CLÔTURÉES lues par le bot (horodatage + OHLC +
        # dip intra-bougie) -> vérifiable a posteriori que l'entrée colle bien à une vraie bougie.
        tail = ' | '.join(f"{b['t']:%H:%M} o{b['o']:.3f} h{b['h']:.3f} l{b['l']:.3f} c{b['c']:.3f} "
                          f"({(b['c']-b['o'])/b['o']*100:+.1f}%)" for b in cbars[-4:])
        print(f"[{now_et():%H:%M}] ENTRY {tk} @ {entry:.4f} (dip -{eff_dip*100:.0f}% "
              f"{'PM' if premarket else 'post-open'}, éligible {added or '?'}, bougie {r['t']:%H:%M}) "
              f"gap {self.gap_ok.get(tk,'')}% {shares} titre(s) (~{shares*entry:.2f}$) ({mode})")
        print(f"    [bougies clôturées] {tail}")
        if self.live:                                # achat ; le STOP sera posé APRÈS confirmation du fill
            res = self.broker.buy(tk, shares, entry, tag='RCC')
            self.orders[tk] = res.get('trade') if isinstance(res, dict) else None
            print(f"    achat placé, attente du fill (halt-check)... [{self._order_diag(tk)}]")
        ev = self.evals.get(tk, {})                  # features de sélection (snapshot à l'entrée)
        fs = ev.get('float_shares')
        self.state[tk] = {'entry': entry, 'gap': self.gap_ok.get(tk, ''),
                          'entry_time': r['t'].strftime('%H:%M'), 'peak': entry,
                          # activation ADAPTATIVE : +5% pour PM, +10% pour post-open (comme le dip)
                          'activate': ACTIVATE_PM if premarket else ACTIVATE_POST,
                          'shares': shares, 'last': entry, 'activated': False, 'confirmed': False,
                          'pending': bool(self.live), 'wait': 0,
                          'float_m': round(fs / 1e6, 3) if fs else '', 'inst_pct': ev.get('inst_pct', ''),
                          'chart_r': ev.get('chart_rating', ''), 'volume_r': ev.get('volume_rating', ''),
                          'float_r': ev.get('float_rating', ''), 'ssr': 1 if ev.get('ssr') else 0}
        save_state(self.state)

    def _manage(self, tk: str, cbars: List[dict], t: datetime):
        pos = self.state[tk]
        cb = cbars[-1]                               # dernière bougie CLÔTURÉE (sélection par HORODATAGE, cf. cycle())
        # Le peak ne compte QUE les bougies STRICTEMENT APRÈS l'entrée. Sinon, sur le
        # cycle suivant l'entrée, cb est encore la bougie d'entrée (dip) et son HIGH
        # (le spike d'AVANT le dip, ex CSAI 15/09 : high 4,00 avant close 3,73) gonflait
        # le peak -> MFE faussé + activation prématurée du trailing (bascule phase 2 sur
        # un faux +5%). Ça alignait mal le live sur le backtest (qui, lui, ne prend le
        # peak qu'à partir de i+1). Corrigé 15/09.
        if cb['t'].strftime('%H:%M') > pos['entry_time']:
            pos['peak'] = max(pos.get('peak', pos['entry']), cb['h'])
        pos['last'] = cb['c']
        eod = hm(t) >= HARD_EXIT           # 15:55 : fenêtre de SORTIE FORCÉE (avant le vrai close 16:00)
        if self.live:
            held = self.broker.positions().get(tk)
            qty = held.get('shares', 0) if held else 0
            # 0) CONFIRMATION DU FILL (détection de halt) : on attend que la position apparaisse
            if pos.get('pending'):
                if qty > 0:                          # achat rempli -> on démarre le two-phase
                    pos['pending'] = False; pos['confirmed'] = True
                    fill = self._last_buy_fill(tk)   # prix VRAIMENT payé (slippage inclus)
                    if fill:
                        if abs(fill - pos['entry']) / pos['entry'] > 0.001:
                            print(f"    fill réel {fill:.4f} (signal {pos['entry']:.4f}) "
                                  f"-> slippage {(fill-pos['entry'])/pos['entry']*100:+.2f}%")
                        pos['fill'] = fill           # prix RÉEL -> sert au P&L SEULEMENT
                    # Les NIVEAUX (stop/activation/trail) partent du prix SIGNAL (pos['entry'] =
                    # close de la bougie dip = ce que montrent graphique/backtest/indicateur),
                    # PAS du fill (16/09, demande de Martin : aligner le live sur le chart).
                    self.orders.pop(tk, None)        # réf d'achat (rempli) -> on oublie
                    pos['stop_level'] = round(pos['entry'] * (1 - STOP), 2)
                    self.orders[tk] = self._stop_at(tk, pos['shares'], pos['stop_level'])
                    print(f"[{now_et():%H:%M}] {tk} achat CONFIRMÉ -> STOP -{STOP*100:.0f}% @ {pos['stop_level']}")
                    save_state(self.state)
                else:
                    pos['wait'] = pos.get('wait', 0) + 1
                    if pos['wait'] >= FILL_TIMEOUT:  # pas rempli -> halté/illiquide
                        diag = self._order_diag(tk)  # capturer le statut AVANT d'annuler (cancel retire l'objet)
                        self._cancel_order(tk)       # annuler l'achat
                        h2 = self.broker.positions().get(tk)      # re-check (race d'un fill de dernière seconde)
                        if h2 and h2.get('shares', 0) > 0:
                            pos['pending'] = False; pos['confirmed'] = True
                            self.orders[tk] = self._fixed_stop(tk, pos['shares'], pos['entry'])
                            print(f"[{now_et():%H:%M}] {tk} rempli in-extremis -> STOP posé"); save_state(self.state)
                        else:
                            print(f"[{now_et():%H:%M}] {tk} achat NON rempli ({pos['wait']} cycles) -> DIAG: {diag}")
                            # rejet de PERMISSION (err 201 : closing-only, small cap, ineligible) :
                            # inutile de retenter, IBKR refusera toute la journée -> on écarte le titre.
                            low = (diag or '').lower()
                            refus = any(k in low for k in ('no trading permission', 'closing-only',
                                                           'closing only', 'customer ineligible',
                                                           'not accepted', 'no opening trades'))
                            if refus:
                                print(f"    -> REFUSÉ par IBKR (permission) : {tk} écarté pour la journée")
                                self.done.add(tk)     # pas de retry inutile
                            else:
                                print(f"    -> ANNULÉ (non rempli : halt ou illiquide), retry possible")
                            self.state.pop(tk, None)
                            save_state(self.state)    # persister l'annulation (sinon fichier périmé)
                    else:
                        save_state(self.state)
                return
            # 1) SORTIE détectée : la position a disparu (STOP ou TRAIL rempli chez IBKR)
            if pos.get('confirmed') and qty <= 0:
                px = self._last_sell_fill(tk) or pos.get('last', pos['entry'])
                self._cancel_order(tk)
                reason = 'EOD' if pos.get('eod_order') else ('TRAIL' if pos.get('activated') else 'STOP')
                self._close(tk, px, reason, already_sold=True); return
            if qty > 0:
                pos['confirmed'] = True
                # 1bis) RÉCONCILIATION : le broker est la SOURCE DE VÉRITÉ.
                # Si la position existe mais n'a AUCUN ordre de vente vivant (redémarrage
                # du bot, annulation par IBKR, Gateway relancé), on repose la protection.
                if tk not in self._protected:
                    kind = 'TRAIL' if pos.get('activated') else 'STOP'
                    print(f"[{now_et():%H:%M}] ⚠️ {tk} position SANS protection -> repose {kind}")
                    o = (self._trailing_stop(tk, pos['shares'], pos.get('peak', pos['entry']))
                         if pos.get('activated')
                         else self._fixed_stop(tk, pos['shares'], pos['entry']))  # entry = SIGNAL
                    if o is not None:
                        self.orders[tk] = o
                        self._protected.add(tk)
            # 2) BACKSTOP À DEUX NIVEAUX (dès 15:55) : sortie forcée pendant que c'est LIQUIDE
            #    (RTH avant 16:00), puis filet en extended hours, puis GTC pour le prochain open.
            #    On (re)pose une vente marketable GTC outsideRth ; la SORTIE (qty<=0) est
            #    journalisée par le bloc "1) SORTIE détectée" ci-dessus au fill.
            if eod:
                if qty > 0:
                    reprice = hm(t) < EXT_CLOSE            # re-price tant que RTH/extended ouvert
                    if reprice or not pos.get('eod_order'):
                        self._cancel_order(tk)
                        res = self.broker.sell(tk, qty, cb['c'], tag='RCC-EOD', tif='GTC')
                        self.orders[tk] = res.get('trade') if isinstance(res, dict) else None
                        pos['eod_order'] = True
                        tier = 'RTH liquide' if hm(t) < REG_CLOSE else ('extended' if reprice else 'GTC next-open')
                        print(f"[{now_et():%H:%M}] {tk} SORTIE FORCÉE ({tier}) -> vente marketable GTC @ ~{cb['c']:.2f}")
                        save_state(self.state)
                return
            # 3) ACTIVATION : à +ACTIVATE% du prix SIGNAL (théorique, PAS le fill) -> pose le
            #    TRAIL NATIF IBKR. C'est le seul point calé sur le prix théorique (demande de
            #    Martin 16/09) ; le trailing lui-même reste géré par IBKR.
            act = pos.get('activate', ACTIVATE_POST)     # seuil ADAPTATIF (+5% PM / +10% post-open)
            if pos.get('confirmed') and not pos.get('activated') and pos['peak'] >= pos['entry'] * (1 + act):
                trail = self._trailing_stop(tk, pos['shares'], pos['peak'])   # poser le TRAIL d'ABORD
                if trail is not None:                                        # ne lâcher le STOP que si le TRAIL est posé
                    self._cancel_order(tk)                                    # annuler le STOP fixe
                    self.orders[tk] = trail
                    pos['activated'] = True
                    print(f"[{now_et():%H:%M}] {tk} +{act*100:.0f}% (théorique) atteint -> TRAIL natif {TRAIL*100:.0f}%")
            save_state(self.state)
        else:                                        # PAPER : simulation two-phase sur bougies 1-min
            if eod: self._close(tk, cb['c'], 'EOD'); return
            if not pos.get('activated'):
                if cb['l'] <= pos['entry'] * (1 - STOP): self._close(tk, pos['entry']*(1-STOP), 'STOP'); return
                if pos['peak'] >= pos['entry'] * (1 + pos.get('activate', ACTIVATE_POST)): pos['activated'] = True
            else:
                if cb['l'] <= pos['peak'] * (1 - TRAIL): self._close(tk, pos['peak']*(1-TRAIL), 'TRAIL'); return
            save_state(self.state)

    def _close(self, tk: str, exit_px: float, reason: str, already_sold: bool = False):
        pos = self.state.pop(tk)
        self.done.add(tk)                            # pas de ré-entrée sur ce ticker aujourd'hui
        if self.live:
            if not already_sold:                     # sortie EOD : vente au marché (l'ordre a déjà été annulé)
                self.broker.sell(tk, pos.get('shares', 0), exit_px, tag='RCC')
            self.orders.pop(tk, None)
        # P&L sur le prix RÉELLEMENT payé (fill) ; le prix signal ne sert qu'aux NIVEAUX.
        base = pos.get('fill') or pos['entry']       # fill réel (live) sinon signal (paper)
        pnl = (exit_px - base) / base * 100
        mfe = (pos.get('peak', base) - base) / base * 100
        append_journal({'date': now_et().strftime('%Y-%m-%d'), 'ticker': tk, 'gap': pos.get('gap', ''),
                        'entry_time': pos.get('entry_time', ''), 'entry': round(base, 4),
                        'exit_time': now_et().strftime('%H:%M'), 'exit': round(exit_px, 4),
                        'reason': reason, 'pnl_pct': round(pnl, 2), 'mfe_pct': round(mfe, 2),
                        'shares': pos.get('shares', ''), 'dollars': round(pos.get('shares', 0) * base, 2),
                        'mode': 'LIVE' if self.live else 'PAPER',
                        'float_m': pos.get('float_m', ''), 'inst_pct': pos.get('inst_pct', ''),
                        'chart_r': pos.get('chart_r', ''), 'volume_r': pos.get('volume_r', ''),
                        'float_r': pos.get('float_r', ''), 'ssr': pos.get('ssr', '')})
        save_state(self.state)
        print(f"[{now_et():%H:%M}] EXIT  {tk} @ {exit_px:.4f} {reason} {pnl:+.2f}% "
              f"(mfe {mfe:+.1f}%) -> journal")

    def run(self, interval: float = 20.0, once: bool = False):
        mode = 'LIVE — VRAIS ORDRES' if self.live else 'PAPER/journal'
        pop = 'POST-OPEN seulement' if not TRADE_PM else 'PM + post-open'
        print(f"RedCandleCatch — {mode}. {pop}. dip -{DIP*100:.0f}%/-{DIP_LIQUID*100:.1f}% | 2-phases: STOP -{STOP*100:.0f}% "
              f"-> +{ACTIVATE_PM*100:.0f}%/{ACTIVATE_POST*100:.0f}% -> TRAIL {TRAIL*100:.0f}%, gap {GAP_MIN:.0f}-{GAP_MAX:.0f}%, prix {PRICE_MIN:.0f}-{PRICE_MAX:.0f}$, "
              f"liq bougie-dip >= ${MIN_DIP_DOLLAR_VOL/1e3:.0f}K, "
              f"{SHARES} titre(s)/trade, {len(self.state)} ouverte(s). Journal: {JOURNAL.name}")
        while True:
            try: self.cycle()
            except Exception as e: print(f"cycle error: {e}")
            if once: return
            time.sleep(interval)


def main():
    ap = argparse.ArgumentParser(description='RedCandleCatch (paper/journal)')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--interval', type=float, default=20.0)
    ap.add_argument('--tickers', type=str, help='watchlist fixe (contourne le scan gap)')
    ap.add_argument('--live', action='store_true', help='VRAIS ORDRES IBKR (défaut: paper/journal)')
    args = ap.parse_args()
    broker = IBKRBroker(allow_live=args.live)        # --live => vrais ordres, sinon paper
    if not broker.connect():
        print("✗ IBKR indisponible (IB Gateway sur 4001 ?)"); return
    if args.live:
        print("⚠️  MODE LIVE : le bot va passer de VRAIS ORDRES (multi-positions, "
              f"{SHARES} titre(s)/trade, 1/ticker/jour, 2-phases STOP-{STOP*100:.0f}%/+{ACTIVATE_PM*100:.0f}%-{ACTIVATE_POST*100:.0f}%/TRAIL{TRAIL*100:.0f}%).")
    tickers = [t.strip().upper() for t in args.tickers.split(',')] if args.tickers else None
    term = RedCandleCatchTerminator(broker, tickers=tickers, live=args.live)
    try:
        term.run(interval=args.interval, once=args.once)
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        broker.disconnect()


if __name__ == '__main__':
    main()
