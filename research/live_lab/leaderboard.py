#!/usr/bin/env python3
"""CLASSEMENT (leaderboard) des combos (stratégie × sizing) sur les données LIVE du moment.
Se recalcule à CHAQUE exécution -> à relancer quand on a accumulé de nouvelles séances.
Métrique = PROFIT PORTEFEUILLE % (sizing par le risque, hold-to-EOD) sur tous les jours live.

Usage : python research/live_lab/leaderboard.py            # top 10
        python research/live_lab/leaderboard.py --top 20
Sorties : research/live_lab/leaderboard_latest.csv  (classement complet du run)
          research/live_lab/leaderboard_history.csv (1 ligne/run : suivi dans le temps)

⚠️ Données live = PEU de séances = BRUIT. Le classement bouge beaucoup au début ; sa valeur
est la TENDANCE au fil de l'accumulation, pas le gagnant d'un run isolé. Toujours lire n + test.
"""
import os, sys, argparse, datetime as dt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import research.live_lab.backtest as bt

# ── VARIANTES DE STRATÉGIE (curées, pas une grille aveugle : évite le minage de bruit) ──
def variants():
    V = [('LIVE (repli8/capit/gap5-10/eod)', {})]
    V += [('skip open 10:00+',      dict(entry_start=600)),
          ('skip 1re h 10:30+',     dict(entry_start=630)),
          ('gap 5-8',               dict(gap_max=8.0)),
          ('gap 5-7',               dict(gap_max=7.0)),
          ('skip open + gap 5-8',   dict(entry_start=600, gap_max=8.0)),
          ('repli 10%',             dict(retrace_pct=0.10)),
          ('repli 12%',             dict(retrace_pct=0.12)),
          ('capit OFF',             dict(capit_ratio=-1)),
          ('stop 8%',               dict(stop_pct=0.08)),
          ('stop 12%',              dict(stop_pct=0.12)),
          ('bougie verte',          dict(require_green=True)),
          ('HOD en séance (RTH)',   dict(hod_in_rth=True)),
          ('au-dessus open',        dict(require_above_open=True)),
          ('run-up RTH >=2%',       dict(runup_min=2)),
          ('run-up RTH >=5%',       dict(runup_min=5)),
          ('au-dessus VWAP',        dict(vwap_side='above')),
          ('HOD-RTH + above-open',  dict(hod_in_rth=True, require_above_open=True)),
          ('sortie trail 10/2',     dict(exit_mode='trail')),
          ('sortie TP+20%',         dict(exit_mode='tp')),
          ('skip open + repli 12%', dict(entry_start=600, retrace_pct=0.12)),
          ('gap-open >0%',          dict(gap_open_min=0)),
          ('gap-open >=1%',         dict(gap_open_min=1)),
          ('gap-open>0 (desserré)', dict(gap_open_min=0)),                 # LIVE utilise maintenant >=1%
          ('run-up2 + above-open',  dict(runup_min=2, require_above_open=True)),
          # ── PISTES du sweep live 21-22/10 (à SURVEILLER semaine après semaine, cf pistes-sweep-live-21-10) ──
          ('⭐A-trail repli10/gap5-20/trail', dict(retrace_pct=0.10, gap_max=20.0, capit_ratio=1.3,
                                                   pullback_dvol_min=0, exit_mode='trail',
                                                   activate_pct=0.10, trail_pct=0.02)),
          ('⭐A repli10/gap5-20/eod',  dict(retrace_pct=0.10, gap_max=20.0, capit_ratio=1.3, pullback_dvol_min=0)),
          ('⭐B repli5/no-capit/trail', dict(retrace_pct=0.05, capit_ratio=-1, pullback_dvol_min=0,
                                             exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
          # ── CARNET recherche large 25/10 (cf carnet-strategies-candidates) — archétypes distincts ──
          ('⭐⭐S1 qualité 5-10/capit2/trail', dict(gap_min=5.0, gap_max=10.0, retrace_pct=0.08,
                                                    capit_ratio=2.0, exit_mode='trail',
                                                    activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐S2 hautefréq 5-50/10:30/noCapit/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=630,
                                                            retrace_pct=0.12, capit_ratio=-1, pullback_dvol_min=0,
                                                            exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐S3 tp20 5-50/10-midi/noCapit', dict(gap_min=5.0, gap_max=50.0, entry_start=600, entry_end=720,
                                                   retrace_pct=0.08, capit_ratio=-1, pullback_dvol_min=0,
                                                   exit_mode='tp', tp_pct=0.20)),
          # ── +INDICATEUR « HOD en séance » (25/10) : améliore toutes les bases, cf carnet ──
          ('⭐⭐⭐S1+HOD 5-10/capit2/hodRTH/trail', dict(gap_min=5.0, gap_max=10.0, retrace_pct=0.08,
                                                        capit_ratio=2.0, hod_in_rth=True, exit_mode='trail',
                                                        activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐⭐S2+HOD 5-50/10:30/noCapit/hodRTH/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=630,
                                                              retrace_pct=0.12, capit_ratio=-1, pullback_dvol_min=0,
                                                              hod_in_rth=True, exit_mode='trail',
                                                              activate_pct=0.10, trail_pct=0.02)),
          # ── TOP recherche COMPLÈTE 26/10 (famille gaps larges + HOD + bougie verte, cf carnet) ──
          ('⭐⭐⭐⭐F1 5-50/10:30/r8/hodRTH+green/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=630,
                                                            retrace_pct=0.08, capit_ratio=-1, hod_in_rth=True,
                                                            require_green=True, exit_mode='trail',
                                                            activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐⭐⭐F2 5-50/10:00/r10/hodRTH+green/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=600,
                                                             retrace_pct=0.10, capit_ratio=-1, hod_in_rth=True,
                                                             require_green=True, exit_mode='trail',
                                                             activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐⭐⭐F3 5-50/10:00/r12/hodRTH/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=600,
                                                       retrace_pct=0.12, capit_ratio=-1, hod_in_rth=True,
                                                       exit_mode='trail', activate_pct=0.10, trail_pct=0.02)),
          ('⭐⭐⭐⭐F4 5-50/10:30/r12/hodRTH+green/trail', dict(gap_min=5.0, gap_max=50.0, entry_start=630,
                                                             retrace_pct=0.12, capit_ratio=-1, hod_in_rth=True,
                                                             require_green=True, exit_mode='trail',
                                                             activate_pct=0.10, trail_pct=0.02)),
          # ── composante 'c' du trio c+j+k (j=F1, k=F3 déjà suivis) — cf meilleur-trio-strategies ──
          ('⭐⭐⭐⭐c 3-10/9:30/r8/cap1.6/hodRTH/trail', dict(gap_min=3.0, gap_max=10.0, entry_start=570,
                                                           retrace_pct=0.08, capit_ratio=1.6, hod_in_rth=True,
                                                           exit_mode='trail', activate_pct=0.10, trail_pct=0.02))]
    return V

RISKS = [0.005, 0.01, 0.02]        # sizing par le risque : % du capital risqué par trade
MAXPOS, POSCAP, EXPCAP = 10, 0.20, 1.0


def portfolio(t_all, risk, stop_pct, days=None):
    """Profit % et maxDD, sizing CONTRAINT PAR LE CAPITAL via la MOYENNE de trades/jour.
    On ne connaît pas d'avance le nb de trades d'une journée -> on fixe la taille selon la
    MOYENNE de trades/jour de la stratégie (budget EXPCAP partagé entre ces positions) :
        posfrac = min(risque/stop, EXPCAP / moyenne_trades_par_jour, POSCAP)   [FIXE]
    Une strat à 15 trades/j aura des positions ~5x plus petites qu'une à 3/j. La moyenne est
    toujours calculée sur TOUT l'échantillon (= la taille qu'on aurait choisie), puis appliquée
    aux jours demandés (days=... pour l'OOS). Compounding quotidien, max MAXPOS pos/jour."""
    if not len(t_all):
        return 0.0, 0.0
    risk_size = min(risk / stop_pct, POSCAP)
    avg_per_day = len(t_all) / t_all.date.nunique()        # moyenne de trades par jour (actif)
    posfrac = min(risk_size, EXPCAP / avg_per_day)         # TAILLE FIXE basée sur la moyenne
    t = t_all if days is None else t_all[t_all.date.isin(days)]
    eq = 1.0; curve = [1.0]
    for d, day in t.sort_values('entry_min').groupby('date'):
        taken = day.head(MAXPOS)
        eq += eq * posfrac * (taken.pnl / 100.0).sum()
        curve.append(eq)
    curve = np.array(curve); peak = np.maximum.accumulate(curve)
    return (eq - 1) * 100, ((curve - peak) / peak).min() * 100


def main(top):
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    test_days = [d for d in dates if split and d >= split]
    rows = []
    for label, upd in variants():
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        exp = t.pnl.mean() if n else 0.0
        tr_day = n / t.date.nunique() if n else 0.0        # moyenne de trades par jour (actif)
        te = t[t.date >= split].pnl if (split and n) else pd.Series(dtype=float)
        exp_te = te.mean() if len(te) else np.nan
        for risk in RISKS:
            prof, dd = portfolio(t, risk, P['stop_pct'])
            prof_oos, _ = portfolio(t, risk, P['stop_pct'], days=test_days)
            daily = prof / len(dates)                       # profit moyen par jour de bourse (FULL)
            daily_oos = prof_oos / max(len(test_days), 1)   # profit moyen/jour sur l'OOS
            posfrac = min(min(risk / P['stop_pct'], POSCAP), EXPCAP / tr_day) if tr_day else 0
            rows.append(dict(strategie=label, risque=f"{risk*100:.1f}%", size=posfrac * 100,
                             profit=prof, maxDD=dd, profit_oos=prof_oos, n=n, tr_day=tr_day,
                             n_test=len(te), exp_tr=exp, exp_test=exp_te,
                             m=daily * 21, q=daily * 63, y=daily * 252,       # proj. LINÉAIRE full (21/63/252 j)
                             y_oos=daily_oos * 252))                          # annualisé OOS (comparable à y)
    r = pd.DataFrame(rows)

    hdr = (f"\n#  {'STRATÉGIE':<28} {'RISQ':>5} {'SIZE':>5} {'PROFIT':>7} {'OOS':>6} {'exp/tr':>7} {'tr/j':>5} "
           f"| {'~MOIS':>6} {'~AN':>8} {'~AN_OOS':>8}")
    def show(df, title):
        print(title); print(hdr); print("─" * 104)
        for i, (_, x) in enumerate(df.head(top).iterrows()):
            print(f"{i+1:<2} {x.strategie:<28} {x.risque:>5} {x['size']:>4.0f}% {x.profit:>+6.1f}% {x.profit_oos:>+5.1f}% "
                  f"{x.exp_tr:>+6.2f}% {x.tr_day:>5.1f} | {x.m:>+5.0f}% {x.y:>+7.0f}% {x.y_oos:>+7.0f}%")

    print(f"\nDonnées : {len(dates)} séances live ({dates[0]}..{dates[-1]}) | split OOS >= {split} "
          f"({len(test_days)} j. de test)")
    print(f"Sizing : CONTRAINT CAPITAL (budget {EXPCAP:.0%}/jour partagé, max {MAXPOS} pos), hold-EOD, slip ON")
    print(f"⚠️  ~MOIS/~AN = projection LINÉAIRE du profit full (×21/252 j) ; ~AN_OOS = idem sur l'OOS seul "
          f"({len(test_days)} j). Comparer ~AN vs ~AN_OOS = POMMES-AVEC-POMMES (le PROFIT/OOS bruts couvrent")
    print(f"   des nb de jours différents, donc PAS comparables). Tout = FANTASME sur {len(dates)} j, PAS une prévision.")
    r = r.sort_values('profit', ascending=False).reset_index(drop=True)
    show(r, "\n╔═ TOP STRATÉGIES × SIZING (classé par profit ; colonne OOS = jours de test) ═╗")

    # sorties CSV : classement complet + historique (suivi dans le temps)
    r.to_csv(os.path.join(HERE, 'leaderboard_latest.csv'), index=False)
    best = r.iloc[0]
    hist = os.path.join(HERE, 'leaderboard_history.csv')
    line = dict(run=dt.datetime.now().isoformat(timespec='seconds'), n_days=len(dates),
                couvre=f"{dates[0]}..{dates[-1]}", top1=best.strategie, top1_risque=best.risque,
                top1_profit=round(best.profit, 2), live_baseline_exp=round(rows[0]['exp_tr'], 3))
    pd.DataFrame([line]).to_csv(hist, mode='a', header=not os.path.exists(hist), index=False)

    # historique PAR VARIANTE (suivi longitudinal, 1 ligne/variante/soir, sizing risque 2%)
    vh = os.path.join(HERE, 'variant_history.csv')
    run = dt.datetime.now().isoformat(timespec='seconds')
    per = r[r.risque == '2.0%'][['strategie', 'n', 'tr_day', 'exp_tr', 'exp_test', 'profit', 'profit_oos']].copy()
    per = per.round({'tr_day': 2, 'exp_tr': 3, 'exp_test': 3, 'profit': 2, 'profit_oos': 2})
    per.insert(0, 'couvre', f"{dates[0]}..{dates[-1]}")
    per.insert(0, 'n_days', len(dates))
    per.insert(0, 'run', run)
    per.to_csv(vh, mode='a', header=not os.path.exists(vh), index=False)
    print(f"\n→ classement complet : leaderboard_latest.csv | hist top1 : leaderboard_history.csv "
          f"| hist par variante : variant_history.csv")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=10)
    main(ap.parse_args().top)
