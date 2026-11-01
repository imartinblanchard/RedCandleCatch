#!/usr/bin/env python3
"""SCREEN fondamental façon Buffett (qualité + valeur) sur un univers, via yfinance (ratios ACTUELS).

⚠️ C'est un SCREEN (ce qui paraît bon MAINTENANT), PAS un backtest. Un vrai backtest value exigerait
des fondamentaux POINT-IN-TIME + les titres faillis (biais du survivant) = données payantes qu'on n'a
pas. De plus le facteur 'value' (bas P/E/P/B) sous-performe la croissance depuis ~15 ans, et l'edge réel
de Buffett (moats, management, float d'assurance, détention à vie) ne se réduit pas à des ratios.

Composite : qualité (ROE, marge, peu de dette) + valeur (P/E, P/B, PEG bas), rangs croisés.
Usage : python -m research.value_lab.screen [nasdaq100]"""
import os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.swing_lab.universes import UNIVERSES

FIELDS = ['trailingPE', 'forwardPE', 'priceToBook', 'returnOnEquity', 'profitMargins',
          'debtToEquity', 'dividendYield', 'pegRatio', 'marketCap']


def resolve(uni):
    """Tickers d'un univers : registre swing_lab, ou 'sp500' (liste courante via Wikipedia)."""
    if uni in UNIVERSES:
        return UNIVERSES[uni]
    if uni == 'sp500':
        import requests, io
        html = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=20).text
        tbl = pd.read_html(io.StringIO(html))[0]
        return [str(s).replace('.', '-') for s in tbl['Symbol'].tolist()]   # BRK.B -> BRK-B (yfinance)
    raise SystemExit(f"univers inconnu : {uni}")


def fetch(tickers, cache):
    if os.path.exists(cache):
        print(f"  (cache brut réutilisé : {os.path.basename(cache)})")
        return pd.read_parquet(cache)
    import yfinance as yf
    rows = []
    for tk in tickers:
        try:
            info = yf.Ticker(tk).info
            rows.append(dict(ticker=tk, **{f: info.get(f) for f in FIELDS}))
        except Exception as e:
            print(f"  ⚠️ {tk}: {e}")
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    df.to_parquet(cache, index=False)
    return df


def main():
    uni = sys.argv[1] if len(sys.argv) > 1 else 'nasdaq100'
    tickers = resolve(uni)
    print(f"Screen fondamental (yfinance, ratios actuels) : {len(tickers)} titres de '{uni}'...\n", flush=True)
    d = fetch(tickers, os.path.join(HERE, 'results', f'value_raw_{uni}.parquet'))
    d = d.dropna(subset=['trailingPE', 'returnOnEquity'])
    d = d[(d.trailingPE > 0) & (d.trailingPE < 200)]          # profitable, pas aberrant
    n = len(d)

    def good(s, small_better):   # percentile 0-100 où MEILLEUR = 100
        return s.rank(ascending=not small_better, pct=True) * 100

    # VALEUR : P/E bas, P/B bas, PEG bas = MIEUX (small_better=True)
    val = (good(d.trailingPE, True) + good(d.priceToBook.fillna(d.priceToBook.max()), True)
           + good(d.pegRatio.fillna(d.pegRatio.max()), True)) / 3
    # QUALITÉ : ROE haut, marge haute = mieux ; dette basse = mieux
    qual = (good(d.returnOnEquity, False) + good(d.profitMargins.fillna(0), False)
            + good(d.debtToEquity.fillna(d.debtToEquity.max()), True)) / 3
    d = d.assign(value=val.round(), quality=qual.round(), score=(val + qual).round())
    d = d.sort_values('score', ascending=False).reset_index(drop=True)
    d.to_csv(os.path.join(HERE, 'results', f'value_screen_{uni}.csv'), index=False)

    cols = ['ticker', 'trailingPE', 'priceToBook', 'returnOnEquity', 'profitMargins', 'debtToEquity',
            'dividendYield', 'value', 'quality', 'score']
    disp = d[cols].copy()
    disp['returnOnEquity'] = (disp.returnOnEquity * 100).round(0)
    disp['profitMargins'] = (disp.profitMargins * 100).round(0)
    disp[['trailingPE', 'priceToBook', 'debtToEquity', 'dividendYield']] = \
        disp[['trailingPE', 'priceToBook', 'debtToEquity', 'dividendYield']].round(1)
    print(f"{n} titres notés. TOP 15 'QUALITÉ À PRIX RAISONNABLE' (score = valeur + qualité) :")
    print(disp.head(15).to_string(index=False))
    print(f"\nBAS DE TABLEAU (chers / faible qualité) :")
    print(disp.tail(5).to_string(index=False))
    print("\nLÉGENDE: ROE/marges en %, value/quality/score = percentiles (100=meilleur).")
    print("⚠️ SCREEN actuel, pas un backtest. Facteur value en retard ~15 ans. Buffett ≠ ratios seuls.")
    print(f"CSV: research/value_lab/results/value_screen_{uni}.csv")


if __name__ == '__main__':
    main()
