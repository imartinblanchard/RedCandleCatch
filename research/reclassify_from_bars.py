#!/usr/bin/env python3
"""
Classement ROBUSTE PM vs post-open à partir des BOUGIES (pas du champ `added`).

Le champ `added` = quand le dashboard a VU le ticker -> dépend de l'heure de démarrage
du scanner (jours contaminés). Ici on ignore `added` et on regarde la DATA : à quel
moment le prix a-t-il franchi le seuil de gap d'éligibilité (+10% vs clôture veille) ?
  - 1re minute où gap >= GAP_MIN  AVANT 09:30  -> gapper PRÉ-MARCHÉ (PM)
  - 1re minute où gap >= GAP_MIN  À/APRÈS 09:30 -> runner POST-OUVERTURE

prev_close = dernière clôture journalière Alpaca strictement avant le jour.
"""
import os
from datetime import datetime, timedelta
import pandas as pd

from bot.alpaca_scanner import _get_bars, ET

COLLECTED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'data', 'collected')
BARS_DIR = os.path.join(COLLECTED, 'bars')
GAP_MIN = 0.10          # seuil d'éligibilité (même que redcandlecatch_scan)
RTH = 570               # 09:30 en minutes
_pc_cache = {}


def prev_close(tk, date):
    k = (tk, date)
    if k in _pc_cache:
        return _pc_cache[k]
    day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=ET)
    try:
        d = _get_bars(f'/v2/stocks/{tk}/bars', {
            'timeframe': '1Day',
            'start': (day - timedelta(days=10)).isoformat(),
            'end': day.isoformat(), 'adjustment': 'raw', 'limit': 15})
        bars = [b for b in (d.get('bars') or []) if b['t'][:10] < date]
        pc = bars[-1]['c'] if bars else None
    except Exception:
        pc = None
    _pc_cache[k] = pc
    return pc


def to_min(s):
    return int(s[:2]) * 60 + int(s[3:5])


def classify(tk, date, g):
    """-> ('PM'|'post-open'|'inconnu', minute de 1er franchissement, gap max)."""
    pc = prev_close(tk, date)
    if not pc:
        return 'inconnu', None, None
    g = g.sort_values('datetime')
    mins = g['datetime'].map(to_min).values
    gap = (g['h'].values - pc) / pc          # gap intrabar au plus haut
    cross = [(m, gp) for m, gp in zip(mins, gap) if gp >= GAP_MIN]
    gmax = float(gap.max())
    if not cross:
        return 'inconnu', None, gmax          # n'a jamais atteint +10% dans les barres
    first = cross[0][0]
    return ('PM' if first < RTH else 'post-open'), first, gmax


def build(only_day=None):
    elig = pd.read_csv(os.path.join(COLLECTED, 'eligibles.csv'))
    old = {(r.date, r.ticker): ('PM' if r.is_premarket else 'post-open')
           for r in elig.itertuples()}
    rows = []
    files = [f for f in sorted(os.listdir(BARS_DIR)) if f.endswith('.parquet')]
    if only_day:
        files = [f for f in files if f[:-8] == only_day]
    for f in files:
        date = f[:-8]
        df = pd.read_parquet(os.path.join(BARS_DIR, f))
        for tk, g in df.groupby('ticker', sort=False):
            lab, first, gmax = classify(tk, date, g.reset_index(drop=True))
            rows.append({'date': date, 'ticker': tk, 'gap_session': lab,
                         'cross_min': first, 'gap_max_pct': round(gmax * 100, 1) if gmax else None,
                         'old_label': old.get((date, tk))})
    return pd.DataFrame(rows)


if __name__ == '__main__':
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else None
    r = build(day)
    # comparaison ancien (added) vs nouveau (bars)
    r['changed'] = r['gap_session'] != r['old_label']
    hhmm = lambda m: f'{int(m)//60:02d}:{int(m)%60:02d}' if pd.notna(m) else '--'
    r['cross'] = r['cross_min'].map(hhmm)
    print(r[['date', 'ticker', 'old_label', 'gap_session', 'cross', 'gap_max_pct', 'changed']].to_string(index=False))
    print(f"\n{r['changed'].sum()}/{len(r)} tickers RECLASSÉS  |  inconnu: {(r.gap_session=='inconnu').sum()}")
