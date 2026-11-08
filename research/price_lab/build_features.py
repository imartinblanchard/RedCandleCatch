#!/usr/bin/env python3
"""Matérialise les features HORS-PRIX par ticker-jour (une ligne par (date,ticker)) à partir
de la collecte live : bars (volume), meta (float/inst/mcap), news (horodatées), halts (Nasdaq).
Calqué sur build_liquid_universe_pm.py / build_exclusions.py : lit data/collected_live/, écrit
un CSV que l'engine joint sur (date,ticker) pour slicer au-delà du prix.

Features :
  gap_max      : gap MAX atteint en RTH (hod-pc)/pc*100  — le « niveau de gap » du jour
  float_shares, inst_pct, market_cap         : meta
  dvol_session : somme(v*c) RTH ($)           — liquidité séance
  float_rot    : volume RTH / float_shares    — rotation du float (x)
  pm_dvol, latepm_dvol : liquidité pré-marché ($, depuis liquid_universe_pm)
  has_news, news_premkt, n_news : news datée du jour / avant 9:30 / nb
  halt_count, first_halt_min, halted : arrêts de cotation (0 tant que forward-collecte vide)

⚠️ halts = FORWARD-ONLY (collecte démarrée 08/11, cf fetch_halts.py) : 0 sur les séances
antérieures. Les autres features sont dispo sur tout l'historique collecté.

Sortie : research/price_lab/results/features.csv
Usage   : python -m research.price_lab.build_features
"""
import os, sys, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt

DATA = bt.DATA
OUT = os.path.join(HERE, 'results', 'features.csv')
RTH0, RTH1 = 570, 960                                  # 9:30 .. 16:00 (minutes ET)


def load_meta_mcap():
    """(ticker,date) -> market_cap (le reste float/inst vient déjà des groups)."""
    out = {}
    for mf in glob.glob(os.path.join(DATA, 'meta-*.json')):
        day = os.path.basename(mf)[5:-5]
        try:
            for tk, m in json.load(open(mf)).items():
                out[(tk, day)] = m.get('market_cap')
        except Exception:
            continue
    return out


def load_halts():
    """(ticker,date) -> liste de minutes ET des halts de ce jour (HaltDate == day)."""
    out = {}
    for hf in glob.glob(os.path.join(DATA, 'halts-*.json')):
        day = os.path.basename(hf)[6:-5]
        try:
            data = json.load(open(hf))
        except Exception:
            continue
        for tk, halts in data.items():
            mins = []
            for h in halts:
                t = (h.get('halt_time') or '')[:5]         # 'HH:MM'
                if len(t) == 5 and t[2] == ':':
                    try:
                        mins.append(int(t[:2]) * 60 + int(t[3:]))
                    except ValueError:
                        pass
            if mins:
                out[(tk, day)] = sorted(mins)
    return out


def load_pm_liq():
    """(ticker,date) -> (pm_dvol, latepm_dvol) depuis liquid_universe_pm.csv si présent."""
    p = os.path.join(os.path.dirname(HERE), 'live_lab', 'results', 'liquid_universe_pm.csv')
    if not os.path.exists(p):
        return {}
    u = pd.read_csv(p)
    return {(r.ticker, r.date): (r.pm_dvol, r.latepm_dvol) for r in u.itertuples()}


def main():
    groups, dates = bt.load_groups()
    news = bt.load_news()                                # (tk,date) -> [minutes]
    halts = load_halts()
    mcap = load_meta_mcap()
    pmliq = load_pm_liq()

    rows = []
    for g in groups:
        tk, date, pc = g['tk'], g['date'], g['pc']
        mins, h, c, v = g['mins'], g['h'], g['c'], g['v']
        rth = (mins >= RTH0) & (mins < RTH1)
        if not rth.any():
            continue
        hod = np.maximum.accumulate(h)
        gap_max = float(((hod - pc) / pc * 100)[rth].max())
        vol_rth = float(v[rth].sum())
        dvol = float((v[rth] * c[rth]).sum())
        fl = g.get('float_shares')
        float_rot = round(vol_rth / fl, 3) if fl and fl > 0 else np.nan

        nmins = news.get((tk, date), [])
        hmins = halts.get((tk, date), [])
        pm, latepm = pmliq.get((tk, date), (np.nan, np.nan))

        rows.append(dict(
            date=date, ticker=tk, gap_max=round(gap_max, 1),
            float_shares=fl, inst_pct=g.get('inst_pct'), market_cap=mcap.get((tk, date)),
            dvol_session=round(dvol), float_rot=float_rot,
            pm_dvol=pm, latepm_dvol=latepm,
            has_news=int(bool(nmins)), news_premkt=int(any(m < RTH0 for m in nmins)), n_news=len(nmins),
            halt_count=len(hmins), first_halt_min=(min(hmins) if hmins else np.nan), halted=int(bool(hmins)),
        ))

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"{len(df)} ticker-jours · {df.date.nunique()} séances -> {OUT}")
    print(f"  news: {df.has_news.sum()} jours avec news ({df.news_premkt.sum()} premkt) | "
          f"halts: {df.halted.sum()} jours haltés | float_rot connu: {df.float_rot.notna().sum()}")
    print(f"  gap>=30: {(df.gap_max>=30).sum()} | dont news {int(df[df.gap_max>=30].has_news.sum())} | "
          f"dont halted {int(df[df.gap_max>=30].halted.sum())}")


if __name__ == '__main__':
    main()
