#!/usr/bin/env python3
"""Construit la liste d'EXCLUSION de l'univers : ticker-jours dont le gap veille->ouverture est un
ARTEFACT (reverse split) ou un RACHAT (acquisition/merger) — qu'on ne veut PAS trader.

Détection :
  - reverse_split : yfinance .splits (ratio < 1) avec ex-date proche du jour (fenêtre [-2, 0]).
    + secours : titre de news « reverse split » / « share consolidation ».
  - acquisition   : titres de news (patterns M&A précis) autour du jour.

Entrée : univers liquide (liquid_universe_pm.csv, latepm>=0.20) + news-*.json.
Sorties : data/collected_live/excluded.csv (ticker,date,reason) + splits_cache.json (réutilisable)."""
import os, sys, json, re, time, glob, datetime as dt
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, 'data', 'collected_live')
PM = os.path.join(ROOT, 'research', 'live_lab', 'results', 'liquid_universe_pm.csv')
CACHE = os.path.join(DATA, 'splits_cache.json')
OUT = os.path.join(DATA, 'excluded.csv')

# CIBLE d'un rachat UNIQUEMENT (le titre se fait acheter -> collé au prix de l'offre). On N'exclut PAS
# l'acquéreur (« to acquire X », « acquisition of X ») = vrai catalyseur qu'on veut trader.
ACQ = re.compile(r'\b(to be acquired|be acquired by|being acquired|will be acquired|'
                 r'(takeover|buyout) (offer|bid|deal|report|proposal)|agreed takeover|'
                 r'tender offer|to be taken private|taken private in|'
                 r'per share in cash|all-cash (deal|transaction|acquisition|merger)|'
                 r'to be bought by|agree[sd]? to be acquired)\b', re.I)
RSPLIT = re.compile(r'\b(reverse (stock )?split|share consolidation|consolidation of (its )?shares)\b', re.I)


def load_splits(tickers):
    import yfinance as yf
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [t for t in tickers if t not in cache]
    print(f"splits : {len(cache)} en cache, {len(todo)} à récupérer via yfinance", flush=True)
    for i, tk in enumerate(todo):
        try:
            s = yf.Ticker(tk).splits
            cache[tk] = {d.strftime('%Y-%m-%d'): float(r) for d, r in s.items()} if s is not None and len(s) else {}
        except Exception:
            cache[tk] = {}
        if i % 50 == 0:
            json.dump(cache, open(CACHE, 'w')); print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(0.25)
    json.dump(cache, open(CACHE, 'w'))
    return cache


def news_hits(date):
    p = os.path.join(DATA, f'news-{date}.json')
    if not os.path.exists(p):
        return {}
    d = json.load(open(p)); out = {}
    for tk, items in d.items():
        txt = ' | '.join(it.get('title', '') for it in items)
        if ACQ.search(txt): out[tk] = 'acquisition'
        elif RSPLIT.search(txt): out[tk] = 'reverse_split'
    return out


def main():
    u = pd.read_csv(PM); liq = u[u.latepm_frac >= 0.20][['date', 'ticker']].drop_duplicates()
    tickers = sorted(liq.ticker.unique())
    splits = load_splits(tickers)
    news_by_day = {d: news_hits(d) for d in sorted(liq.date.unique())}
    rows = []
    for _, r in liq.iterrows():
        tk, date = r.ticker, r.date
        reason = None
        # 1) reverse split (yfinance) : ex-date dans [jour-2, jour]
        D = dt.date.fromisoformat(date)
        for ds, ratio in splits.get(tk, {}).items():
            if ratio < 1 and 0 <= (D - dt.date.fromisoformat(ds)).days <= 2:
                reason = 'reverse_split'; break
        # 2) news (acquisition / reverse split annoncé)
        if reason is None:
            reason = news_by_day.get(date, {}).get(tk)
        if reason:
            rows.append(dict(ticker=tk, date=date, reason=reason))
    ex = pd.DataFrame(rows)
    ex.to_csv(OUT, index=False)
    n_rs = int((ex.reason == 'reverse_split').sum()) if len(ex) else 0
    n_acq = int((ex.reason == 'acquisition').sum()) if len(ex) else 0
    print(f"\nEXCLUSIONS : {len(ex)} ticker-jours ({n_rs} reverse_split, {n_acq} acquisition) "
          f"sur {len(liq)} ({len(ex)/max(len(liq),1)*100:.1f}%)")
    if len(ex):
        print("\nExemples :"); print(ex.head(20).to_string(index=False))
    print(f"\n-> {OUT}")


if __name__ == '__main__':
    main()
