"""Filtrage RedCandleCatch LONG — inspiré du système de Gus (short-journal) mais réorienté
pour le LONG (les ratings de qualité sont INVERSÉS).

Univers      : scanner IBKR TOP_PERC_GAIN, small-caps < 500M, prix 3-20$.
Filtres durs : float 0.2M-50M, volume PM >= 50k, volume relatif anti-pump (< 50x),
               gap >= 50% (SANS plafond).  (Filtre inst désactivé — hook laissé.)
Ratings 1-5  : INVERSÉS pour le long — chart en tendance UP = 5, volume élevé = 5,
               micro-float = 5.  Un rating chart/volume == 1 => rejet.
Signaux      : catalyseur (news, hook), SSR réinterprété en contexte de rebond long.
Différés     : filtre institutionnel + modèle ML (pas de données long tant qu'on n'a
               pas de trades remplis).

Toutes les fonctions réseau/IBKR sont défensives (timeouts, try/except) et mises en
cache par (ticker, jour) : le loop live ne doit jamais bloquer ni marteler Finviz.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from datetime import date, datetime
import math

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo('America/New_York')
except Exception:
    ET = None

RTH_OPEN = (9, 30)

def _hm(t) -> tuple:
    return (t.hour, t.minute)

def _now_et() -> datetime:
    return datetime.now(ET) if ET else datetime.now()

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_WEB = True
except Exception:
    HAS_WEB = False

# ------------------------------------------------------------------ constantes
# Config validée 2026-09-11 : la tranche 10-20% bat nettement le >=50% (9/9 mois
# gagnants, t-stat 4,01 vs 2,03). Le >=50% concentrait 92% de son profit sur mai-juin.
GAP_MIN, GAP_MAX = 10.0, 20.0        # fourchette de gap, %
PRICE_MIN, PRICE_MAX = 3.0, 20.0
MARKET_CAP_MAX = 500_000_000         # small caps (filtre du SCANNER IBKR, pas d'evaluate)
# --- ÉLIGIBILITÉ POST-OUVERTURE (16/09) : le gap est mesuré sur le plus-haut de 04:00
# jusqu'à midi (pas seulement le pré-marché). Ça capte les runners qui entrent dans la
# bande 10-20% APRÈS 9:30 (83% des candidats étaient ratés). Validé OOS via
# research/intraday_gappers/. Le dip adaptatif du terminator gère leur volatilité (-2%).
ENABLE_POSTOPEN = True               # False -> ancien comportement (gap PM 04:00-09:30 seul)
POSTOPEN_END = (12, 0)               # fin de la fenêtre de mesure du gap (midi ET)
# --- FILTRE DE LIQUIDITÉ session — DÉSACTIVÉ le 19/09 ---
# Historique : ajouté le 16/09 comme filtre du $vol CUMULÉ session (mauvaise interprétation
# de l'intention de Martin). Le VRAI garde-fou de liquidité voulu est sur la BOUGIE DE DIP
# (là où on entre) → implémenté dans redcandlecatch_terminator (`MIN_DIP_DOLLAR_VOL = 200K`).
# Ce filtre-ci coupait trop tôt (au niveau univers) des tickers dont la bougie de dip serait
# pourtant remplissable. Désactivé -> éligibilité = gap 10-20 + prix 3-20 seulement ;
# le $200K bougie-dip est le SEUL juge de liquidité. Bonus : collecte de recherche plus large.
ENABLE_LIQUIDITY = False
MIN_DOLLAR_VOL = 500_000             # (inutilisé tant que ENABLE_LIQUIDITY=False ; encore renseigné/collecté dans dollar_vol)
# --- hooks DÉSACTIVÉS : filtres non validés qui coupaient les MEILLEURS trades ---
# Mesuré le 11/09 sur la tranche 10-20% : PM vol >=50k => +1,07%/tr (t=2,18) alors que
# les trades REJETÉS (<50k) font +2,28%/tr (t=7,33). Plus le volume PM est faible,
# meilleur est le trade. Idem pour le float (hérité de Gus/short, non backtestable) et
# les ratings (logique d'inversion inventée, jamais validée). Le live applique donc
# EXACTEMENT le backtest : gap 10-20%, prix 3-20$, dip -5%.
# --- TRADABILITÉ : on filtre sur la RÉGULARITÉ du pré-marché, pas sur le volume total.
# Cas FLWS (14/09) : 45 168 actions en PM (volume total correct) mais seulement 48 minutes
# actives sur 276 -> quand il trade il trade bien, mais il ne trade presque jamais = intradable.
# Le volume total ne détecte pas ça ; le nb de minutes actives, oui.
# Backtest : minutes>=60 -> n=275, exp +1,26%/tr, t=2,94  (vs pm_vol>=50k : n=226, +1,07%, t=2,18).
ENABLE_PM_VOL = False                # DÉSACTIVÉ 14/09 : avec vol>=100k + min>=60 le backtest
PM_VOL_MIN = 100_000                 #   tombait à n=157, exp +0,66%/tr, t=1,10 (NON significatif).
                                     #   Sans filtre : n=701, +1,89%/tr, t=7,15.
ENABLE_PM_MINUTES = False            # DÉSACTIVÉ 14/09 (voir ci-dessus)
PM_MINUTES_MIN = 60                  # minutes (bougies à volume > 0) entre 04:00 et 09:30
# 14/09 : minutes remises à 60, c'est le VOLUME (100k) qui écarte les titres fins.
# Vérifié : RAMZ (82k), AAOZ (53k), CBRZ (73k) échouent tous sur le volume seul.
ENABLE_FLOAT_FILTER = False          # si True : rejet hors bande FLOAT_MIN-FLOAT_MAX
FLOAT_MIN, FLOAT_MAX = 200_000, 50_000_000
ENABLE_RATINGS = False               # si True : rejet si chart_rating==1 ou volume_rating==1
ENABLE_ANTIPUMP = False              # anti-pump (rel-vol) DÉSACTIVÉ : backtest 09/09 montre que
REL_VOL_MAX = 50.0                   #   les titres pumpés (rvol 50+) sont GAGNANTS en long (+0,54%/tr,
                                     #   62% des trades). Le filtre venait de Gus (short) et nuisait au long.
ENABLE_INST_FILTER = False           # si True : rejet si inst_pct > INST_MAX
INST_MAX = 20.0
ENABLE_ML = False                    # pas de modèle long tant qu'on n'a pas de data

# ------------------------------------------------------------------ cache jour
_CACHE: Dict[str, dict] = {}         # clé "ticker" -> {jour, fund, ta}
_CACHE_DAY: Optional[date] = None

def _slot(ticker: str) -> dict:
    global _CACHE_DAY
    today = date.today()
    if _CACHE_DAY != today:
        _CACHE.clear(); _CACHE_DAY = today
    return _CACHE.setdefault(ticker.upper(), {})

# =============================================================== fondamentaux
def _parse_number(val: str) -> Optional[float]:
    """'2.5M' -> 2_500_000, '1.2B', '-500K', '-' -> None."""
    if not val or val == '-':
        return None
    val = val.replace(',', '').strip()
    mult = 1
    if val.endswith('B'): mult, val = 1_000_000_000, val[:-1]
    elif val.endswith('M'): mult, val = 1_000_000, val[:-1]
    elif val.endswith('K'): mult, val = 1_000, val[:-1]
    try:
        return float(val) * mult
    except Exception:
        return None

def fetch_fundamentals(ticker: str) -> dict:
    """float_shares, inst_pct, market_cap, income via Finviz (best-effort, caché)."""
    slot = _slot(ticker)
    if 'fund' in slot:
        return slot['fund']
    fund = {'float_shares': None, 'inst_pct': None, 'market_cap': None, 'income': None}
    if HAS_WEB:
        try:
            url = f'https://finviz.com/quote.ashx?t={ticker}'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                for row in soup.find_all('tr', class_='table-dark-row'):
                    cells = row.find_all('td')
                    for i, cell in enumerate(cells):
                        t = cell.get_text(strip=True)
                        if t == 'Shs Float':
                            fund['float_shares'] = _parse_number(cells[i + 1].get_text(strip=True))
                        elif t == 'Inst Own':
                            v = cells[i + 1].get_text(strip=True).replace('%', '')
                            try: fund['inst_pct'] = float(v)
                            except Exception: pass
                        elif t == 'Market Cap':
                            fund['market_cap'] = _parse_number(cells[i + 1].get_text(strip=True))
                        elif t == 'Income':
                            fund['income'] = _parse_number(cells[i + 1].get_text(strip=True))
        except Exception as e:
            print(f"    Finviz err {ticker}: {e}")
    slot['fund'] = fund
    return fund

# =============================================================== TA quotidienne
def _sma(v: List[float], n: int) -> Optional[float]:
    return sum(v[-n:]) / n if len(v) >= n else None

def _rsi(closes: List[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-n, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0: gains += d
        else: losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)

def daily_ta(broker, ticker: str) -> dict:
    """Indicateurs quotidiens pour les ratings + SSR. Caché par jour."""
    slot = _slot(ticker)
    if 'ta' in slot:
        return slot['ta']
    ta = {'trend': 'UNKNOWN', 'rsi': None, 'dist_sma20_pct': 0.0,
          'momentum_5d': 0.0, 'rel_volume': 1.0, 'ssr': False}
    try:
        c = broker._contract(ticker)
        bars = broker.ib.reqHistoricalData(
            c, endDateTime='', durationStr='3 M', barSizeSetting='1 day',
            whatToShow='TRADES', useRTH=True, formatDate=1)
        closes = [float(b.close) for b in bars]
        vols = [float(b.volume) for b in bars if b.volume is not None]
        if len(closes) >= 21:
            last = closes[-1]
            sma20 = _sma(closes, 20)
            sma20_prev = _sma(closes[:-5], 20)
            if sma20:
                ta['dist_sma20_pct'] = (last - sma20) / sma20 * 100
                if last > sma20 and sma20_prev and sma20 >= sma20_prev:
                    ta['trend'] = 'UP'
                elif last < sma20 and sma20_prev and sma20 <= sma20_prev:
                    ta['trend'] = 'DOWN'
                else:
                    ta['trend'] = 'FLAT'
            ta['rsi'] = _rsi(closes, 14)
            if len(closes) >= 6 and closes[-6]:
                ta['momentum_5d'] = (last - closes[-6]) / closes[-6] * 100
        if len(vols) >= 21:
            avg = sum(vols[-21:-1]) / 20
            if avg > 0:
                ta['rel_volume'] = vols[-1] / avg
        # SSR : clôture veille en baisse >= 10% vs l'avant-veille
        if len(closes) >= 2 and closes[-2] > 0:
            ta['ssr'] = (closes[-1] - closes[-2]) / closes[-2] <= -0.10
    except Exception as e:
        print(f"    TA err {ticker}: {e}")
    slot['ta'] = ta
    return ta

# =============================================================== ratings LONG
def rate_chart_long(ta: dict) -> int:
    """1-5, INVERSÉ vs Gus : 5 = belle tendance UP pour acheter le momentum."""
    score = 3.0
    trend = ta.get('trend', 'UNKNOWN')
    if trend == 'UP': score += 1
    elif trend == 'DOWN': score -= 1
    m = ta.get('momentum_5d', 0) or 0
    if m > 10: score += 1
    elif m > 0: score += 0.5
    elif m < -10: score -= 1
    rsi = ta.get('rsi')
    if rsi is not None:
        if 50 <= rsi <= 70: score += 0.5          # force saine
        elif rsi > 78: score -= 0.5                # suracheté -> risque de chasser
        elif rsi < 35: score -= 1                  # trop faible
    dist = ta.get('dist_sma20_pct', 0) or 0
    if 0 < dist <= 30: score += 0.5                # au-dessus de la MM, sain
    elif dist > 60: score -= 0.5                   # trop étendu pour chasser
    return max(1, min(5, round(score)))

def rate_volume_long(ta: dict) -> int:
    """1-5, INVERSÉ vs Gus : 5 = volume relatif élevé (le momentum a de la participation)."""
    rel = ta.get('rel_volume', 1) or 1
    if rel >= 5: return 5
    if rel >= 3: return 4
    if rel >= 2: return 3
    if rel >= 1: return 2
    return 1

def rate_float(float_shares: Optional[float]) -> int:
    """1-5, NEUTRE (volatilité) : micro-float = 5. Identique à Gus."""
    if float_shares is None: return 3
    if float_shares < 2_000_000: return 5
    if float_shares < 5_000_000: return 4
    if float_shares < 15_000_000: return 3
    if float_shares < 30_000_000: return 2
    return 1

# =============================================================== évaluation
def evaluate(broker, ticker: str, gap_pct: Optional[float], price: Optional[float],
             pm_volume: Optional[float], pm_minutes: Optional[int] = None,
             dollar_vol: Optional[float] = None) -> dict:
    """Applique tous les filtres LONG. `pm_minutes` = nb de minutes pré-marché ayant
    RÉELLEMENT échangé (bougies à volume > 0) — mesure de tradabilité.
    Retourne {eligible, reason, float_shares, inst_pct, ratings..., ssr, ta}."""
    out = {'eligible': False, 'reason': '', 'float_shares': None, 'inst_pct': None,
           'chart_rating': None, 'volume_rating': None, 'float_rating': None,
           'ssr': False, 'ta': None, 'pm_minutes': pm_minutes}

    # --- gap / prix (garde-fous de base) ---
    if gap_pct is None or not (GAP_MIN <= gap_pct < GAP_MAX):
        g = f'{gap_pct:.0f}' if gap_pct is not None else '?'
        out['reason'] = f'gap {g}% hors {GAP_MIN:.0f}-{GAP_MAX:.0f}%'; return out
    if price is None or not (PRICE_MIN <= price <= PRICE_MAX):
        out['reason'] = f'prix {price} hors {PRICE_MIN}-{PRICE_MAX}'; return out
    if ENABLE_PM_VOL and pm_volume is not None and pm_volume < PM_VOL_MIN:
        out['reason'] = f'PM vol {pm_volume:.0f} < {PM_VOL_MIN:,}'; return out
    if ENABLE_PM_MINUTES and pm_minutes is not None and pm_minutes < PM_MINUTES_MIN:
        out['reason'] = f'{pm_minutes} min actives en PM < {PM_MINUTES_MIN} (intradable)'; return out
    if ENABLE_LIQUIDITY and dollar_vol is not None and dollar_vol < MIN_DOLLAR_VOL:
        out['reason'] = f'dollar-vol ${dollar_vol/1e6:.1f}M < ${MIN_DOLLAR_VOL/1e6:.0f}M requis'; return out

    # --- fondamentaux : collectés pour le JOURNAL (features ML), filtres désactivés ---
    fund = fetch_fundamentals(ticker)
    out['float_shares'] = fund['float_shares']; out['inst_pct'] = fund['inst_pct']
    fs = fund['float_shares']
    if ENABLE_FLOAT_FILTER and fs is not None:
        if fs < FLOAT_MIN: out['reason'] = f'float {fs/1e6:.2f}M < {FLOAT_MIN/1e6:.1f}M'; return out
        if fs > FLOAT_MAX: out['reason'] = f'float {fs/1e6:.1f}M > {FLOAT_MAX/1e6:.0f}M'; return out
    if ENABLE_INST_FILTER and fund['inst_pct'] is not None and fund['inst_pct'] > INST_MAX:
        out['reason'] = f'inst {fund["inst_pct"]:.0f}% > {INST_MAX:.0f}%'; return out

    # --- TA + volume relatif anti-pump ---
    ta = daily_ta(broker, ticker); out['ta'] = ta; out['ssr'] = ta['ssr']
    if ENABLE_ANTIPUMP and ta['rel_volume'] and ta['rel_volume'] > REL_VOL_MAX:
        out['reason'] = f'rel-vol {ta["rel_volume"]:.0f}x > {REL_VOL_MAX:.0f}x (déjà pumpé)'; return out

    # --- ratings : calculés pour le JOURNAL (features ML), rejet désactivé ---
    cr = rate_chart_long(ta); vr = rate_volume_long(ta); fr = rate_float(fs)
    out['chart_rating'] = cr; out['volume_rating'] = vr; out['float_rating'] = fr
    if ENABLE_RATINGS:
        if cr == 1:
            out['reason'] = 'chart rating = 1'; return out
        if vr == 1:
            out['reason'] = 'volume rating = 1'; return out

    out['eligible'] = True
    out['reason'] = f'OK (chart={cr} vol={vr} float={fr}{" SSR" if ta["ssr"] else ""})'
    return out

# ============================================================ scanner autonome
# (utilisé par le dashboard/scanner ; l'exécuteur ne scanne plus, il lit le fichier)
def _today_bars(broker, tk: str) -> List[dict]:
    """Bougies 1-min d'aujourd'hui (pré-marché inclus), ET, oldest→newest."""
    raw = broker.intraday_1min(tk, duration='46800 S')
    today = _now_et().date(); out = []
    for b in raw:
        t = b['t'].astimezone(ET) if ET else b['t']
        if t.date() == today:
            out.append({**b, 't': t})
    return out

def _prev_close(broker, tk: str) -> Optional[float]:
    """Clôture de la VEILLE. BUG corrigé 16/09 : `bars[-2]` supposait que la dernière
    barre daily était aujourd'hui — FAUX en pré-marché (la barre du jour n'existe pas
    encore) → on prenait avant-hier (cas ARTL : 4,78 au lieu de 5,34 → faux gap 16,8%).
    Fix : prendre la dernière barre daily dont la date est STRICTEMENT avant aujourd'hui."""
    try:
        c = broker._contract(tk)
        bars = broker.ib.reqHistoricalData(c, endDateTime='', durationStr='5 D',
                                           barSizeSetting='1 day', whatToShow='TRADES',
                                           useRTH=True, formatDate=1)
        today = _now_et().date()
        def bar_date(b):
            d = b.date
            return d.date() if hasattr(d, 'hour') else d   # datetime -> date ; sinon déjà une date
        prev = [b for b in bars if bar_date(b) < today]
        return float(prev[-1].close) if prev else None
    except Exception:
        return None

def gap_pct(broker, tk: str, today_bars: List[dict]) -> Optional[float]:
    """Gap = (plus-haut 04:00 -> fin de fenêtre) / clôture veille - 1, en %.
    Fenêtre : jusqu'à midi si ENABLE_POSTOPEN (capte les runners post-9:30), sinon
    jusqu'à l'ouverture 9:30 (ancien comportement PM-only)."""
    end = POSTOPEN_END if ENABLE_POSTOPEN else RTH_OPEN
    win = [b for b in today_bars if (4, 0) <= _hm(b['t']) < end]
    if not win:
        return None
    pc = _prev_close(broker, tk)
    if not pc or pc <= 0:
        return None
    return (max(b['h'] for b in win) - pc) / pc * 100

def scan_universe(broker, limit: int = 30) -> List[str]:
    """Univers Gus : TOP_PERC_GAIN small-caps < 500M, prix 3-20$."""
    try:
        from ib_insync import ScannerSubscription
        sub = ScannerSubscription(instrument='STK', locationCode='STK.US.MAJOR',
                                  scanCode='TOP_PERC_GAIN', numberOfRows=limit)
        sub.abovePrice = PRICE_MIN; sub.belowPrice = PRICE_MAX
        sub.marketCapBelow = MARKET_CAP_MAX
        rows = broker.ib.reqScannerData(sub)
        return [r.contractDetails.contract.symbol for r in rows[:limit]]
    except Exception as e:
        print(f"scan error: {e}")
        return []

def scan_eligible(broker, limit: int = 30) -> Dict[str, dict]:
    """Scanne l'univers + applique tous les filtres LONG. Retourne les titres
    ÉLIGIBLES sous forme {ticker: snapshot} (gap, float, inst, ratings, ssr)."""
    out: Dict[str, dict] = {}
    for tk in scan_universe(broker, limit):
        tb = _today_bars(broker, tk)
        if not tb:
            continue
        g = gap_pct(broker, tk, tb)
        price = tb[-1]['c']
        pmb = [b for b in tb if (4, 0) <= _hm(b['t']) < RTH_OPEN]
        pm_vol = sum(b['v'] for b in pmb)
        pm_min = sum(1 for b in pmb if b['v'] > 0)   # minutes RÉELLEMENT échangées
        session_vol = sum(b['v'] for b in tb)        # volume cumulé du jour (04:00 -> maintenant)
        dollar_vol = session_vol * price if price else 0  # dollar-volume (filtre de liquidité)
        ev = evaluate(broker, tk, g, price, pm_vol, pm_min, dollar_vol)
        if ev['eligible']:
            out[tk] = {
                'gap': round(g, 1) if g else '',
                'price': round(price, 4),
                'pm_minutes': pm_min, 'pm_vol': int(pm_vol), 'dollar_vol': int(dollar_vol),
                'float_shares': ev['float_shares'], 'inst_pct': ev['inst_pct'],
                'chart_rating': ev['chart_rating'], 'volume_rating': ev['volume_rating'],
                'float_rating': ev['float_rating'], 'ssr': ev['ssr'],
                'reason': ev['reason'], 'added': _now_et().strftime('%H:%M'),
            }
    return out
