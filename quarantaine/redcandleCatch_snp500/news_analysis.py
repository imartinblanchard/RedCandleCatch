#!/usr/bin/env python3
"""
Corrélation NEWS ↔ mouvements sur les 10 titres les plus volatils du S&P 500.

Questions :
  1. Le volume de news corrèle-t-il avec l'amplitude des mouvements journaliers ?
  2. Les gros jours de baisse (les dips = nos entrées) sont-ils news-driven ?
  3. STRATÉGIE : un dip AVEC news rebondit-il différemment d'un dip SANS news ?
     (si oui -> filtrer par news pourrait rescuer l'entrée)

Source news : Alpaca /v1beta1/news (Benzinga). Mapping : date calendaire du created_at
(⚠️ approximation : une news après clôture est attribuée à ce jour, pas au suivant).

Lancer : source .venv/bin/activate && python redcandleCatch_snp500/news_analysis.py
"""
import os, sys, math, time
import requests
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine
from bot import config

HERE = os.path.dirname(os.path.abspath(__file__))
HEADERS = {'APCA-API-KEY-ID': config.ALPACA_API_KEY_ID,
           'APCA-API-SECRET-KEY': config.ALPACA_API_SECRET_KEY}
DIP_K = 2.0          # dip = ret1 <= -DIP_K * sigma (même définition que la stratégie)
FWD = 10             # rendement forward à 10 jours (horizon de la stratégie)
MAX_PAGES = 120      # garde-fou pagination news / ticker


def fetch_news_counts(symbol, start, end):
    """Renvoie une Series date->nb d'articles pour ce symbole."""
    url = f'{config.ALPACA_DATA_URL}/v1beta1/news'
    counts = {}
    token = None
    for _ in range(MAX_PAGES):
        params = {'symbols': symbol, 'start': start, 'end': end, 'limit': 50,
                  'sort': 'asc'}
        if token:
            params['page_token'] = token
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        r.raise_for_status()
        j = r.json()
        for n in j.get('news', []):
            d = n['created_at'][:10]
            counts[d] = counts.get(d, 0) + 1
        token = j.get('next_page_token')
        if not token:
            break
        time.sleep(0.15)
    return pd.Series(counts, dtype=float)


def main():
    df = engine.load_table(os.path.join(HERE, 'data', 'daily.parquet'))
    vol = df.groupby('ticker')['c'].apply(lambda s: s.pct_change().std() * math.sqrt(252)).sort_values(ascending=False)
    top10 = list(vol.head(10).index)
    start, end = str(df.date.min()), str(df.date.max())
    print(f"Top 10 volatils : {top10}")
    print(f"Période : {start} -> {end}\n")

    rows_corr = []
    dip_news, dip_nonews = [], []      # rendements forward 10j
    for tk in top10:
        g = df[df.ticker == tk].sort_values('date').reset_index(drop=True).copy()
        news = fetch_news_counts(tk, start, end)
        g['news'] = g['date'].map(news).fillna(0.0)
        g['absret'] = g['ret1'].abs()
        g['fwd'] = g['c'].shift(-FWD) / g['c'] - 1
        # 1. corrélation volume news <-> amplitude du move
        corr = g[['news', 'absret']].corr().iloc[0, 1]
        # 2. news sur les dips
        dips = g[g['ret1'] <= -DIP_K * g['sigma']]
        p_news_dip = (dips['news'] > 0).mean() if len(dips) else np.nan
        p_news_all = (g['news'] > 0).mean()
        rows_corr.append((tk, len(g), int(g['news'].sum()), corr, len(dips), p_news_dip, p_news_all))
        # 3. rebond des dips avec/sans news
        d = dips.dropna(subset=['fwd'])
        dip_news += list(d[d['news'] > 0]['fwd'])
        dip_nonews += list(d[d['news'] == 0]['fwd'])
        print(f"  {tk:6} news={int(g['news'].sum()):>5}  corr(news,|ret|)={corr:+.2f}  "
              f"dips={len(dips):>3}  P(news|dip)={p_news_dip*100 if p_news_dip==p_news_dip else 0:>3.0f}%  "
              f"P(news|jour)={p_news_all*100:>3.0f}%")

    print("\n=== 1-2. SYNTHÈSE ===")
    C = pd.DataFrame(rows_corr, columns=['tk', 'jours', 'news', 'corr', 'dips', 'p_news_dip', 'p_news_all'])
    print(f"  corr(news,|ret|) moyenne : {C['corr'].mean():+.2f}  (>0 = plus de news les jours qui bougent)")
    print(f"  P(news | dip) moy = {C['p_news_dip'].mean()*100:.0f}%   vs   P(news | jour) moy = {C['p_news_all'].mean()*100:.0f}%")

    print(f"\n=== 3. LE DIP REBONDIT-IL DIFFÉREMMENT AVEC/SANS NEWS ? (rendement forward {FWD}j) ===")
    a, b = np.array(dip_news), np.array(dip_nonews)
    def line(x, lab):
        if len(x) == 0:
            print(f"  {lab:16} n=0"); return
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0
        print(f"  {lab:16} n={len(x):>4}  fwd{FWD}j moy={x.mean()*100:+.2f}%  "
              f"win={100*(x>0).mean():.0f}%  t={t:+.1f}")
    line(a, 'dip AVEC news')
    line(b, 'dip SANS news')
    if len(a) > 1 and len(b) > 1:
        diff = a.mean() - b.mean()
        print(f"  -> écart (avec - sans) = {diff*100:+.2f} pts sur {FWD}j")


if __name__ == '__main__':
    main()
