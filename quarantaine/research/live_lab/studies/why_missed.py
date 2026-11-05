#!/usr/bin/env python3
"""Pourquoi le bot a raté les 16 gagnants que le backtest prend (écart de sélection) ?

Pour chaque (date, ticker) raté : était-il ÉLIGIBLE (eligible-*.json) ? le bot a-t-il VU
un repli (signals-*.csv) et avec quelle décision/valeurs temps réel (pb_dvol, capit) ?
Catégorise : vu-skippé-liquidité / vu-skippé-capit / éligible-mais-pas-de-repli-détecté /
jamais-éligible. Dit si l'écart est RÉCUPÉRABLE (assouplir un seuil) ou irréductible.
"""
import os, json
import pandas as pd

# les 16 backtest-only (date, ticker, heure d'entrée backtest) issus de diagnose_gap
MISSED = [
    ('2026-10-07', 'BOLT', '15:23'), ('2026-10-07', 'JDZG', '14:21'),
    ('2026-10-08', 'LEXX', '10:08'), ('2026-10-08', 'STDN', '11:21'),
    ('2026-10-09', 'AIAI', '12:26'), ('2026-10-09', 'BBGI', '11:47'),
    ('2026-10-09', 'FOIL', '11:42'), ('2026-10-09', 'LSE', '15:47'),
    ('2026-10-15', 'MF', '10:24'), ('2026-10-15', 'OPNW', '09:50'),
    ('2026-10-15', 'PIII', '09:39'), ('2026-10-15', 'TP', '11:14'),
    ('2026-10-16', 'TANH', '10:47'), ('2026-10-16', 'UCAR', '12:12'),
    ('2026-10-21', 'FGRU', '15:54'), ('2026-10-21', 'LIMN', '09:49'),
]
EDIR = 'data/computed'
SDIR = 'data/collected_live'


def main():
    cats = {}
    print(f"{'date':<11}{'tk':<6}{'élig?':<6}{'vu?':<5}{'décision live':<22}{'pb_dvol':>9}{'capit':>7}{'retr':>6}")
    print('-' * 72)
    for date, tk, _ in MISSED:
        # éligible ?
        ef = f'{EDIR}/redcandlecatch-eligible-{date}.json'
        elig = tk in json.load(open(ef)) if os.path.exists(ef) else None
        # vu dans les signals ?
        sf = f'{SDIR}/signals-{date}.csv'
        dec, pbd, cap, retr, vu = '', '', '', '', False
        if os.path.exists(sf):
            s = pd.read_csv(sf)
            rows = s[s.ticker == tk]
            if len(rows):
                vu = True
                # on prend la MEILLEURE tentative (pb_dvol max = la plus proche de passer la liquidité)
                best = rows.loc[rows.pb_dvol.idxmax()]
                dec, pbd, cap, retr = best.decision, int(best.pb_dvol), best.capit_ratio, best.retrace
        # catégorie
        if elig is False or (elig is None):
            c = 'jamais-éligible' if elig is False else 'élig-inconnue'
        elif not vu:
            c = 'éligible-mais-repli-non-détecté'
        elif 'illiquide' in str(dec):
            c = 'vu-skippé-LIQUIDITÉ'
        elif 'capit' in str(dec):
            c = 'vu-skippé-CAPIT'
        elif 'ENTER' in str(dec):
            c = 'ENTER (pris en réel ?!)'
        else:
            c = f'vu-{dec}'
        cats[c] = cats.get(c, 0) + 1
        print(f"{date:<11}{tk:<6}{str(elig):<6}{str(vu):<5}{str(dec):<22}{pbd:>9}{str(cap):>7}{str(retr):>6}")

    print('\n=== RÉPARTITION ===')
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {n:>2}  {c}")
    print("\nNote : 07-09/10 = époque de transition config (gap-open durci le 09/10) -> comparer surtout 15-21/10.")


if __name__ == '__main__':
    main()
