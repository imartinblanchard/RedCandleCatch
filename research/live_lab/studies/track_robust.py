#!/usr/bin/env python3
"""PERSISTANCE walk-forward : rejoue la MÊME analyse à CHAQUE séance passée (fenêtre expansive,
point-in-time) sur les combos ROBUSTES trouvés par strategy_search_full, pour voir lesquelles
RESTENT en haut au fil des jours (= vraies) vs apparaissent/disparaissent (= bruit).

Pour chaque jour D (de MIN_DAYS à la fin) : on ne garde que les séances <= D (chaque ticker-jour
avec SON univers), on simule les combos, on les classe par CPTE. Sortie : score de persistance
(part des jours où la combo était dans le top-K) + l'évolution + historique CSV.
Relancé chaque soir par le cron (rebuild complet, cheap sur le sous-ensemble robuste)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

RES = os.path.join(HERE, '..', 'results', 'strategy_search_full_results.csv')
OUT = os.path.join(HERE, '..', 'results', 'robust_persistence.csv')
STARTS = {'9:30': 570, '10:00': 600, '10:30': 630}
ENDS = {'midi': 720, '15:55': 955}
MIN_DAYS = 10            # on commence à classer quand on a au moins 10 séances
TOPK = 8                # "dans le top-K" = considéré persistant ce jour-là
N_TRACK = 25            # nb de combos robustes suivis


def build_P(row):
    P = dict(bt.LIVE)
    gmin, gmax = (float(x) for x in str(row['gap']).split('-'))
    esl, eel = str(row['heures']).split('>')
    ind = str(row['indic'])
    P.update(gap_min=gmin, gap_max=gmax, entry_start=STARTS[esl], entry_end=ENDS[eel],
             retrace_pct=float(row['repli']), capit_ratio=float(row['capit']),
             hod_in_rth='hodRTH' in ind, require_green='green' in ind,
             vwap_side='below' if 'vw<' in ind else None,
             recent_active_min=0.8 if 'rAct' in ind else 0.0, recent_active_window=10)
    s = row['sortie']
    if s == 'trail10/2': P.update(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
    elif s == 'tp20': P.update(exit_mode='tp', tp_pct=0.20)
    else: P.update(exit_mode='eod')
    return P


def label(row):
    return f"{row['gap']}/{row['heures']}/r{row['repli']}/cap{row['capit']}/{row['sortie']}/{row['indic']}"


def main():
    if not os.path.exists(RES):
        print(f"❌ {RES} absent — lance d'abord strategy_search_full."); return
    r = pd.read_csv(RES)
    rob = r[r.robust & (r.t >= 2.3)].sort_values('cpte', ascending=False)
    rob = rob.drop_duplicates(subset=['n', 'exp', 'pf', 'cpte']).head(N_TRACK)
    if not len(rob):
        print("Aucune combo robuste (t>=2.3) à suivre."); return
    combos = [(label(row), build_P(row)) for _, row in rob.iterrows()]
    groups, dates = bt.load_groups()
    print(f"{len(dates)} séances. Suivi walk-forward de {len(combos)} combos robustes "
          f"(top-{TOPK} = persistant), de la séance {MIN_DAYS} à {len(dates)}.\n", flush=True)

    hist = []
    for i in range(MIN_DAYS - 1, len(dates)):
        upto = dates[i]
        g_sub = [g for g in groups if g['date'] <= upto]
        day_rows = []
        for name, P in combos:
            t = bt.simulate(g_sub, P, slip=True)
            if not len(t):
                continue
            cp, _ = portfolio(t, 0.02, P['stop_pct'])
            day_rows.append((name, cp, round(t.pnl.mean(), 2), len(t)))
        day_rows.sort(key=lambda x: -x[1])
        for rank, (name, cp, exp, n) in enumerate(day_rows, 1):
            hist.append(dict(upto=upto, n_days=i + 1, combo=name, rank=rank, cpte=round(cp, 1), exp=exp, n=n))
    h = pd.DataFrame(hist)
    h.to_csv(OUT, index=False)

    # score de persistance = part des jours où la combo était dans le top-K
    chk = h.n_days.nunique()
    persist = (h[h['rank'] <= TOPK].groupby('combo').size() / chk * 100).round().sort_values(ascending=False)
    last = h[h.upto == dates[-1]].set_index('combo')
    print(f"PERSISTANCE sur {chk} points de contrôle (séances {MIN_DAYS}->{len(dates)}) :")
    print(f"  {'combo':<52}{'%top'+str(TOPK):>7}{'rang_final':>11}{'exp_fin':>8}")
    for name, pct in persist.head(20).items():
        rk = int(last.loc[name, 'rank']) if name in last.index else '-'
        ex = last.loc[name, 'exp'] if name in last.index else '-'
        print(f"  {name:<52}{pct:>6.0f}%{rk:>11}{ex:>+8.2f}")
    print(f"\n-> %top{TOPK} élevé = la combo RESTE en haut au fil des séances (robuste dans le temps).")
    print(f"   %top{TOPK} bas / en chute = elle n'apparaissait que sur certaines fenêtres (bruit).")
    print(f"CSV complet : {OUT}")


if __name__ == '__main__':
    main()
