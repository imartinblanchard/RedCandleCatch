#!/usr/bin/env python3
"""LEADERBOARD UNIFIÉ — toutes les familles de stratégies dans une seule table.

Agrégateur neutre : ramasse les CANDIDATES de chaque labo (contrat research/core/strategy.py),
résout leur univers, et mesure TOUT avec la MÊME fonction (live_lab.leaderboard.portfolio, 2%).
N'importe RIEN du bot live ni du cron ; ne modifie aucun fichier existant.

Ajouter une famille future :
  1) créer le labo (son moteur), 2) y mettre un `candidates.py` avec une liste CANDIDATES,
  3) l'enregistrer dans REGISTRIES ci-dessous (1 ligne). Rien d'autre à toucher.

Usage : python research/core/leaderboard_all.py [--top 40] [--status deployed|candidate]
Sorties : research/core/leaderboard_all_latest.csv + leaderboard_all_history.csv.
⚠️ Données live = peu de séances = BRUIT ; plusieurs candidates sont in-sample. Lire n + OOS."""
import os, sys, argparse, datetime as dt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab.engine import liquid_groups

# ── familles enregistrées : chaque labo expose une liste CANDIDATES (contrat Strategy) ──
from research.live_lab.candidates import CANDIDATES as REPLI
from research.indicator_lab.candidates import CANDIDATES as INDIC
REGISTRIES = [REPLI, INDIC]       # ← ajouter une famille = ajouter sa liste ici

# ── univers nommés : résolus ici, donc affichables et réutilisables ──
UNIVERSES = {'complet': lambda g: g, 'freq-filtré': liquid_groups}
TY = 252


def main(top, status_filter):
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    nd, ndo = len(dates), max(len(tdays), 1)
    str600 = {}                      # cache des univers résolus (évite de refiltrer)
    rows = []
    for reg in REGISTRIES:
        for s in reg:
            if status_filter and s.status != status_filter:
                continue
            if s.universe not in str600:
                str600[s.universe] = UNIVERSES[s.universe](groups)
            t = s.sim(str600[s.universe])
            if t is None or not len(t):
                continue
            pnl = t.pnl.to_numpy(); n = len(pnl)
            te = t[t.date >= split].pnl if split else pd.Series(dtype=float)
            cp, dd = portfolio(t, 0.02, s.stop); cpo, _ = portfolio(t, 0.02, s.stop, days=tdays)
            tstat = pnl.mean() / (pnl.std(ddof=1) / np.sqrt(n)) if n > 1 and pnl.std() > 0 else 0.0   # significativité
            e_trim = np.sort(pnl)[:-3].mean() if n > 3 else pnl.mean()                                # non-fragile (sans 3 meilleurs)
            rows.append(dict(famille=s.family, statut=s.status, strategie=s.name, univers=s.universe,
                             n=n, tr_day=round(n / t.date.nunique(), 1), exp=round(pnl.mean(), 2),
                             t=round(tstat, 1), e_trim=round(e_trim, 2),
                             exp_oos=round(te.mean(), 2) if len(te) else np.nan,
                             win=round((pnl > 0).mean() * 100), cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                             an=round(cp * TY / nd), an_oos=round(cpo * TY / ndo), maxDD=round(dd, 1),
                             notes=s.notes))
    r = pd.DataFrame(rows).sort_values('cpte', ascending=False).reset_index(drop=True)

    print(f"\nDonnées : {nd} séances live ({dates[0]}..{dates[-1]}) | sizing 2%, slip ON")
    print(f"ROBUSTESSE (full, toutes séances) : t = significativité (|t|>2 ~ solide) ; "
          f"eTrim = exp/tr SANS les 3 meilleurs trades (non-fragile). C_OOS = CPTE sur les {ndo} dernières")
    print(f"séances = BRUIT (petit échantillon), simple SUIVI, ne PAS décider dessus. ~AN/CPTE_OOS/eOOS dans le CSV.\n")
    h = (f"#  {'FAM':<6}{'STATUT':<10}{'STRATÉGIE':<40}{'UNIV':<12}{'n':>4}{'t/j':>5}{'exp':>7}"
         f"{'t':>5}{'eTrim':>7}{'win':>5}{'CPTE':>7}{'C_OOS':>7}{'DD':>6}")
    print(h); print("─" * len(h))
    for i, x in r.head(top).iterrows():
        print(f"{i+1:<2} {x.famille:<6}{x.statut:<10}{x.strategie:<40}{x.univers:<12}{x.n:>4}{x.tr_day:>5.1f}"
              f"{x.exp:>+6.2f}%{x.t:>5.1f}{x.e_trim:>+6.2f}%{x.win:>4.0f}%{x.cpte:>+6.1f}%{x.cpte_oos:>+6.1f}%"
              f"{x.maxDD:>+5.1f}%")

    r.to_csv(os.path.join(HERE, 'leaderboard_all_latest.csv'), index=False)
    hist = os.path.join(HERE, 'leaderboard_all_history.csv')
    run_id = dt.datetime.now().isoformat(timespec='seconds')
    h2 = r[['famille', 'statut', 'strategie', 'univers', 'n', 'tr_day', 'exp', 'exp_oos',
            'cpte', 'cpte_oos', 'maxDD']].copy()
    h2.insert(0, 'couvre', f"{dates[0]}..{dates[-1]}"); h2.insert(0, 'n_days', nd); h2.insert(0, 'run', run_id)
    h2.to_csv(hist, mode='a', header=not os.path.exists(hist), index=False)
    print(f"\n→ leaderboard_all_latest.csv (classement complet) | leaderboard_all_history.csv (suivi longitudinal)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--status', default=None, help='filtrer : deployed | candidate | archived')
    a = ap.parse_args(); main(a.top, a.status)
