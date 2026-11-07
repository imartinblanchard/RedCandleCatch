#!/usr/bin/env python3
"""Règles d'EXCLUSION partagées (recherche ET live) : écarter les titres dont le gap veille->ouverture
est un ARTEFACT (reverse split) ou un RACHAT-CIBLE (le titre se fait acheter -> collé au prix de l'offre).
On N'exclut PAS l'acquéreur (« to acquire X ») = vrai catalyseur qu'on veut trader.

- Recherche : research/price_lab/build_exclusions.py importe les regex d'ici (source unique).
- Live      : bot/redcandlecatch_scan.py appelle live_exclusion_reason() au scan (titres news + splits yfinance)."""
import re
import datetime as dt

# CIBLE d'un rachat uniquement (sens « se fait acheter »), pas l'acquéreur.
ACQ_RE = re.compile(r'\b(to be acquired|be acquired by|being acquired|will be acquired|'
                    r'(takeover|buyout) (offer|bid|deal|report|proposal)|agreed takeover|'
                    r'tender offer|to be taken private|taken private in|'
                    r'per share in cash|all-cash (deal|transaction|acquisition|merger)|'
                    r'to be bought by|agree[sd]? to be acquired)\b', re.I)
RSPLIT_RE = re.compile(r'\b(reverse (stock )?split|share consolidation|consolidation of (its )?shares)\b', re.I)

_SPLITS_CACHE = {}        # ticker -> {date_iso: ratio}  (live, via yfinance)


def is_acquisition(titles):
    return bool(ACQ_RE.search(' | '.join(titles or [])))


def is_reverse_split_news(titles):
    return bool(RSPLIT_RE.search(' | '.join(titles or [])))


def reverse_split_near(ticker, date, splits=None, window=2):
    """True si un reverse split (ratio<1) a une ex-date dans [date-window, date].
    `splits` = {date_iso: ratio} (optionnel, sinon yfinance en live avec cache)."""
    if splits is None:
        if ticker not in _SPLITS_CACHE:
            try:
                import yfinance as yf
                s = yf.Ticker(ticker).splits
                _SPLITS_CACHE[ticker] = {d.strftime('%Y-%m-%d'): float(r) for d, r in s.items()} if s is not None and len(s) else {}
            except Exception:
                _SPLITS_CACHE[ticker] = {}
        splits = _SPLITS_CACHE[ticker]
    for ds, ratio in splits.items():
        try:
            if ratio < 1 and 0 <= (date - dt.date.fromisoformat(ds)).days <= window:
                return True
        except Exception:
            continue
    return False


def exclusion_reason(ticker, date, titles, splits=None):
    """-> 'reverse_split' | 'acquisition' | None. `titles` = titres de news récents du ticker."""
    if reverse_split_near(ticker, date, splits) or is_reverse_split_news(titles):
        return 'reverse_split'
    if is_acquisition(titles):
        return 'acquisition'
    return None


def live_exclusion_reason(ticker, titles, date=None):
    """Version LIVE : splits récupérés via yfinance (cache module). `date` = date ET du jour."""
    return exclusion_reason(ticker, date or dt.date.today(), titles, splits=None)
