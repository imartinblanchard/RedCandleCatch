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
          ('sortie trail 10/2',     dict(exit_mode='trail')),
          ('sortie TP+20%',         dict(exit_mode='tp')),
          ('skip open + repli 12%', dict(entry_start=600, retrace_pct=0.12))]
    return V

RISKS = [0.005, 0.01, 0.02]        # sizing par le risque : % du capital risqué par trade
MAXPOS, POSCAP, EXPCAP = 10, 0.20, 1.0


def portfolio(t, risk, stop_pct):
    """Profit % et maxDD. Position = min(risk/stop, POSCAP) de l'equity ; hold-to-EOD ;
    slots/jour = min(MAXPOS, plafond d'exposition). Compounding quotidien."""
    if not len(t):
        return 0.0, 0.0
    posfrac = min(risk / stop_pct, POSCAP)
    slots = min(MAXPOS, int(EXPCAP / posfrac + 1e-9))      # nb max de positions simultanées/jour
    eq = 1.0; curve = [1.0]
    for d, day in t.sort_values('entry_min').groupby('date'):
        taken = day.head(slots)
        eq += eq * posfrac * (taken.pnl / 100.0).sum()
        curve.append(eq)
    curve = np.array(curve); peak = np.maximum.accumulate(curve)
    return (eq - 1) * 100, ((curve - peak) / peak).min() * 100


def main(top):
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates)
    rows = []
    for label, upd in variants():
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        exp = t.pnl.mean() if n else 0.0
        te = t[t.date >= split].pnl if (split and n) else pd.Series(dtype=float)
        exp_te = te.mean() if len(te) else np.nan
        for risk in RISKS:
            prof, dd = portfolio(t, risk, P['stop_pct'])
            rows.append(dict(strategie=label, risque=f"{risk*100:.1f}%", profit=prof, maxDD=dd,
                             n=n, exp_tr=exp, exp_test=exp_te, n_test=len(te)))
    r = pd.DataFrame(rows).sort_values('profit', ascending=False).reset_index(drop=True)

    print(f"\nDonnées : {len(dates)} séances live ({dates[0]}..{dates[-1]}) | split OOS >= {split}")
    print(f"Sizing : risque/trade, stop du variant, max {MAXPOS} pos, hold-to-EOD, slippage ON")
    print(f"\n#  {'STRATÉGIE':<30} {'RISQ':>5} {'PROFIT':>8} {'maxDD':>7} {'n':>4} {'exp/tr':>7} {'test':>7}")
    print("─" * 82)
    for i, x in r.head(top).iterrows():
        te = f"{x.exp_test:+.2f}%" if pd.notna(x.exp_test) else "  n/a"
        print(f"{i+1:<2} {x.strategie:<30} {x.risque:>5} {x.profit:>+7.1f}% {x.maxDD:>+6.1f}% "
              f"{x.n:>4} {x.exp_tr:>+6.2f}% {te:>7}")

    # sorties CSV : classement complet + historique (suivi dans le temps)
    r.to_csv(os.path.join(HERE, 'leaderboard_latest.csv'), index=False)
    best = r.iloc[0]
    hist = os.path.join(HERE, 'leaderboard_history.csv')
    line = dict(run=dt.datetime.now().isoformat(timespec='seconds'), n_days=len(dates),
                couvre=f"{dates[0]}..{dates[-1]}", top1=best.strategie, top1_risque=best.risque,
                top1_profit=round(best.profit, 2), live_baseline_exp=round(rows[0]['exp_tr'], 3))
    pd.DataFrame([line]).to_csv(hist, mode='a', header=not os.path.exists(hist), index=False)
    print(f"\n→ classement complet : leaderboard_latest.csv | historique : leaderboard_history.csv")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=10)
    main(ap.parse_args().top)
