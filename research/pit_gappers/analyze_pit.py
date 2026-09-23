#!/usr/bin/env python3
"""PIT rebuild — Phase 4 : lecture de data/trades.parquet (sans look-ahead, épisodique).

Segmentations clés :
  - PM               : entrée en pré-marché (phase=PM).
  - post-open FRAIS  : éligible pour la 1re fois APRÈS 09:30 (elig_phase=post-open),
                       jamais gappé en PM. = les vrais runners post-open.
  - post-open RE-GAP : dip post-open sur un titre éligible depuis le PM (elig_phase=PM,
                       phase=post-open) = le cas DCOY que le bot live JETTE aujourd'hui.
Sweeps : dip, bande de prix, heure d'éligibilité, OOS. Une entrée/ticker-jour (1re qualifiante).
"""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, 'data')
t = pd.read_parquet(os.path.join(DATA, 'trades.parquet'))
TEST_START = '2026-05-01'          # OOS : train déc-avr / test mai-août


def first_per_day(df):
    """1 entrée/ticker-jour : la 1re bougie de dip qualifiante (par heure)."""
    return df.sort_values('entry_min').groupby(['ticker', 'date'], as_index=False).first()


def stats(a):
    a = np.asarray(a, float); n = len(a)
    if n == 0:
        return None
    exp = a.mean(); win = (a > 0).mean() * 100
    pf = a[a > 0].sum() / (-a[a < 0].sum() or 1e-9)
    tt = exp / (a.std(ddof=1) / np.sqrt(n)) if n > 1 and a.std(ddof=1) > 0 else 0
    return dict(n=n, exp=exp, win=win, pf=pf, t=tt, total=a.sum())


def show(label, df, dip, pmin, pmax, split_date=None):
    """Filtre dip/prix, prend 1/jour, affiche (et OOS si split_date)."""
    d = df[(df['dip_pct'] <= -dip * 100) & (df['entry_price'] >= pmin) & (df['entry_price'] <= pmax)]
    d = first_per_day(d)
    def line(tag, dd):
        s = stats(dd['pnl_pct'])
        if s is None:
            print(f"  {tag:<34} (0)"); return
        print(f"  {tag:<34} n={s['n']:>5} exp={s['exp']:>+6.2f}% win={s['win']:>4.0f}% "
              f"pf={s['pf']:>4.2f} t={s['t']:>6.2f} tot={s['total']:>+8.0f}%")
    print(f"\n### {label} (dip≤-{dip*100:.1f}%, prix {pmin}-{pmax}$) ###")
    line("ALL", d)
    if split_date:
        line("  TRAIN (déc-avr)", d[d['date'] < split_date])
        line("  TEST  (mai-août)", d[d['date'] >= split_date])


def populations(df):
    pm = df[df['phase'] == 'PM']
    po_fresh = df[(df['phase'] == 'post-open') & (df['elig_phase'] == 'post-open')]
    po_regap = df[(df['phase'] == 'post-open') & (df['elig_phase'] == 'PM')]
    return {'PM': pm, 'post-open FRAIS': po_fresh, 'post-open RE-GAP (jeté par le bot)': po_regap}


print(f"trades: {len(t)} | dates {t['date'].min()}..{t['date'].max()} | "
      f"elig_in_band impose la bande 10-20 au 1er franchissement")
band = t[t['elig_in_band']]         # entrées dont l'éligibilité a atterri DANS 10-20

print("\n" + "=" * 70)
print("HEADLINE — 3 populations, config déployée (post-open dip1.5/act10, PM dip5/act5)")
print("=" * 70)
for name, pop in populations(band).items():
    dip = 0.05 if name == 'PM' else 0.015
    show(name, pop, dip=dip, pmin=3.0, pmax=20.0, split_date=TEST_START)

print("\n" + "=" * 70)
print("SWEEP DIP — post-open FRAIS, prix 3-20$")
print("=" * 70)
pof = populations(band)['post-open FRAIS']
for dip in (0.015, 0.02, 0.03, 0.05):
    s = stats(first_per_day(pof[(pof['dip_pct'] <= -dip*100) &
              (pof['entry_price'].between(3, 20))])['pnl_pct'])
    if s: print(f"  dip {dip*100:>4.1f}% : n={s['n']:>5} exp={s['exp']:>+6.2f}% win={s['win']:>4.0f}% "
                f"pf={s['pf']:>4.2f} t={s['t']:>6.2f}")

print("\n" + "=" * 70)
print("BANDE DE PRIX — post-open FRAIS, dip 1.5%")
print("=" * 70)
for lo, hi in [(0.5, 3), (3, 20), (20, 50)]:
    s = stats(first_per_day(pof[(pof['dip_pct'] <= -1.5) &
              (pof['entry_price'].between(lo, hi))])['pnl_pct'])
    flag = " ⚠️penny-spreads" if lo < 3 else (" ⚠️jamais tradé" if lo >= 20 else "")
    if s: print(f"  {lo}-{hi}$ : n={s['n']:>5} exp={s['exp']:>+6.2f}% win={s['win']:>4.0f}% "
                f"pf={s['pf']:>4.2f} t={s['t']:>6.2f}{flag}")

print("\n" + "=" * 70)
print("HEURE D'ÉLIGIBILITÉ — post-open FRAIS, dip 1.5%, prix 3-20$ (la question >10:30)")
print("=" * 70)
buckets = [(570, 585, '09:30-09:45'), (585, 600, '09:45-10:00'), (600, 630, '10:00-10:30'),
           (630, 690, '10:30-11:30'), (690, 780, '11:30-13:00'), (780, 960, '13:00+')]
sel = first_per_day(pof[(pof['dip_pct'] <= -1.5) & (pof['entry_price'].between(3, 20))])
for lo, hi, lab in buckets:
    s = stats(sel[(sel['elig_min'] >= lo) & (sel['elig_min'] < hi)]['pnl_pct'])
    if s: print(f"  éligible {lab:<12} n={s['n']:>4} exp={s['exp']:>+6.2f}% win={s['win']:>4.0f}% "
                f"pf={s['pf']:>4.2f} t={s['t']:>6.2f}")

print("\n(look-ahead = 0 par construction : toute entrée survient à un minute >= éligibilité)")
