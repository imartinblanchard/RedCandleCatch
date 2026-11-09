#!/usr/bin/env python3
"""Reconstruit la FRÉQUENCE PM (filtre d'univers du bot live : latepm/ PM-liq >= 0,20) pour
tous les tickers ÉLIGIBLES d'un jour, et dit qui passe / qui est recalé. Même définition que
le terminator (redcandlecatch_terminator._pm_liq) : minutes 8:00-9:30 ET avec un trade / 90.

Besoin de data/collected_live/bars-YYYY-MM-DD.parquet (fetch à 16:20 ET) + l'eligible du jour.
Reconstruction a posteriori — le bot, lui, LOGGE désormais la valeur en direct dans
pm_decisions-YYYY-MM-DD.csv (source de vérité). Ici on couvre AUSSI les séances déjà passées.

Usage : python -m research.price_lab.pm_freq_audit [--date YYYY-MM-DD]
"""
import os, sys, json, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

ET = ZoneInfo('America/New_York')
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'collected_live')
ELIG = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'data', 'computed')
PM_LO, PM_HI = 480, 570        # 8:00 -> 9:30 ET
THR = 0.20


def main(day):
    bars_p = os.path.join(DATA, f'bars-{day}.parquet')
    if not os.path.exists(bars_p):
        print(f"❌ {bars_p} absent (fetch bars pas encore fait pour {day}).")
        return
    df = pd.read_parquet(bars_p)
    mins = df['datetime'].str.slice(0, 2).astype(int) * 60 + df['datetime'].str.slice(3, 5).astype(int)
    pm = df[(mins >= PM_LO) & (mins < PM_HI) & (df['v'] > 0)]
    # minutes PM distinctes actives par ticker
    freq = pm.groupby('ticker')['datetime'].nunique().to_dict()

    elig_p = os.path.join(ELIG, f'redcandlecatch-eligible-{day}.json')
    elig = json.load(open(elig_p)) if os.path.exists(elig_p) else {}

    # ce qui a été réellement tradé ce jour (journal)
    traded = set()
    jp = os.path.join(ELIG, 'redcandlecatch-journal.csv')
    if os.path.exists(jp):
        j = pd.read_csv(jp)
        traded = set(j[j.date == day].ticker) if 'date' in j else set()

    rows = []
    for tk, meta in elig.items():
        act = freq.get(tk, 0)
        fr = act / (PM_HI - PM_LO)
        rows.append(dict(ticker=tk, gap=meta.get('gap'), price=meta.get('price'),
                         vol_r=meta.get('volume_rating'), added=meta.get('added'),
                         pm_active=act, pm_frac=round(fr, 3),
                         passe=('OUI' if fr >= THR else 'non'),
                         tradé=('✓' if tk in traded else '')))
    res = pd.DataFrame(rows).sort_values('pm_frac', ascending=False)
    out = os.path.join(HERE, 'results', f'pm_freq_audit-{day}.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    res.to_csv(out, index=False)

    npass = (res.pm_frac >= THR).sum()
    print(f"[{day}] {len(res)} éligibles | PASSENT le filtre PM>={THR:.0%} : {npass} | recalés : {len(res)-npass}")
    print(f"   -> {out}\n")
    show = res.head(25)
    print(show.to_string(index=False))
    gool = res[res.ticker == 'GOOL']
    if len(gool):
        print(f"\nGOOL : pm_active={int(gool.pm_active.iloc[0])}/90 -> pm_frac={gool.pm_frac.iloc[0]:.0%} "
              f"({'PASSE' if gool.pm_frac.iloc[0] >= THR else 'RECALÉ'} le seuil {THR:.0%})")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ET).date().isoformat())
    a = ap.parse_args()
    main(a.date)
