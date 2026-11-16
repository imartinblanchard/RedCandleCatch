#!/usr/bin/env python3
"""LE leaderboard (unifié). Réunit TOUTES les familles de stratégies dont les indicateurs sont
calculables FIABLE en live (prix : OHLC d'une bougie clôturée ; PAS de volume temps réel) :
  - repli  : achat du repli depuis le HOD (moteur research/live_lab/backtest.py) — dont la DÉPLOYÉE.
  - indic  : archétypes d'indicateurs de PRIX (moteur research/price_lab) — lus du price_search.
Mesure tout avec la MÊME fonction (leaderboard.portfolio, 2%), même univers (PM-liquidité), classe
par CPTE + robustesse. PAS de gate "open%" : la live-faisabilité est garantie EN AMONT (choix des
indicateurs), ce n'est plus un cas particulier. open%/entrée = colonnes d'INFO seulement.
Sortie : research/leaderboard_latest.csv."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.price_lab import engine as E

PRICE_CSV = os.path.join(HERE, 'price_lab', 'results', 'price_search_results.csv')
OUT = os.path.join(HERE, 'leaderboard_latest.csv')
PER_PRICE = 40                          # top-N robustes de la recherche indicateurs à injecter

# ── famille REPLI : candidates (dont la DÉPLOYÉE) — P-updates sur bt.LIVE, moteur live_lab ──
REPLI = [
    ('repli-tp20 3-10/midi/r8/tp20/s8 [DÉPLOYÉE]',
     dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, retrace_pct=0.08, capit_ratio=-1,
          hod_in_rth=False, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    ('repli 3-10/midi/r8/eod/s8',
     dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, retrace_pct=0.08, capit_ratio=-1,
          hod_in_rth=False, exit_mode='eod', stop_pct=0.08)),
    ('repli 5-20/midi/r8/tp20/s8',
     dict(gap_min=5, gap_max=20, entry_start=570, entry_end=720, retrace_pct=0.08, capit_ratio=-1,
          hod_in_rth=False, exit_mode='tp', tp_pct=0.20, stop_pct=0.08)),
    ('repli 5-50/10:00/r12/hodRTH/eod',
     dict(gap_min=5, gap_max=50, entry_start=600, retrace_pct=0.12, capit_ratio=-1,
          hod_in_rth=True, exit_mode='eod', stop_pct=0.10)),
    ('repli 3-10/midi/r10/tp30/s8',
     dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, retrace_pct=0.10, capit_ratio=-1,
          hod_in_rth=False, exit_mode='tp', tp_pct=0.30, stop_pct=0.08)),
]


def _stats(t, stop, dates, split, tdays, mid):
    pnl = t.pnl.to_numpy(); n = len(pnl)
    sd = pnl.std(ddof=1) if n > 1 else 0
    te = t[t.date >= split].pnl if split else t.pnl
    h1 = t[t.date < mid].pnl; h2 = t[t.date >= mid].pnl
    cp, dd = portfolio(t, 0.02, stop); cpo, _ = portfolio(t, 0.02, stop, days=tdays)
    em = t['entry_min']
    tt = pnl.mean() / (sd / np.sqrt(n)) if sd > 0 else 0
    etrim = np.sort(pnl)[:-3].mean() if n > 3 else pnl.mean()
    # ROBUSTESSE sur TOUT l'échantillon (OOS retiré des décisions, cf règle : OOS = info/suivi only) :
    # significatif (t) + non-fragile (e_trim) + régulier (les 2 moitiés positives).
    robust = bool(h1.mean() > 0 and h2.mean() > 0 and etrim > 0 and tt >= 2.3)
    return dict(n=n, trj=round(n / t.date.nunique(), 1), exp=round(pnl.mean(), 2), t=round(tt, 1),
                win=round((pnl > 0).mean() * 100), entry_med=bt.hhmm(int(em.median())),
                open_pct=round((em <= 575).mean() * 100), cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                maxDD=round(dd, 1), robust=robust)


def main():
    groups, dates = bt.load_groups(); liq = E.liquid_groups(groups, thr=0.20)
    split = bt.oos_split(dates); tdays = [d for d in dates if d >= split]; mid = dates[len(dates) // 2]
    rows = []
    # 1) repli (dont la déployée)
    for name, upd in REPLI:
        P = dict(bt.LIVE); P.update(upd)
        t = bt.simulate(liq, P, slip=True)
        if len(t) < 10:
            continue
        rows.append(dict(famille='repli', strategie=name, **_stats(t, P['stop_pct'], dates, split, tdays, mid)))
    # 2) indicateurs de prix : top robustes du price_search (métriques déjà calculées, même moteur)
    if os.path.exists(PRICE_CSV):
        d = pd.read_csv(PRICE_CSV)
        # robustesse RECALCULÉE sans l'OOS (e_te ignoré) : t + e_trim + 2 moitiés, comme le repli.
        d = d[(d.e_h1 > 0) & (d.e_h2 > 0) & (d.e_trim > 0) & (d.t >= 2.3)]
        d = d.sort_values('cpte', ascending=False).drop_duplicates(
            subset=['archetype', 'gap', 'heure', 'params', 'exit']).head(PER_PRICE)
        for _, x in d.iterrows():
            rows.append(dict(famille='indic', strategie=f"{x.archetype} {x.gap} {x.heure} {x.params} {x['exit']}"[:52],
                             n=int(x.n), trj=round(x.trj, 1), exp=round(x.exp, 2), t=round(x.t, 1), win=round(x.win),
                             entry_med=x.entry_med, open_pct=int(x.open_pct), cpte=round(x.cpte, 1),
                             cpte_oos=round(x.cpte_oos, 1), maxDD=round(x.maxDD, 1), robust=bool(x.robust)))
    r = pd.DataFrame(rows).sort_values('cpte', ascending=False).reset_index(drop=True)
    r.to_csv(OUT, index=False)
    print(f"\n{len(dates)} séances, univers PM-liquidité={len(liq)} tj | sizing 2%, slip ON. "
          f"Indicateurs live-OK uniquement (prix). open%/entrée = INFO (pas un filtre).\n")
    h = (f"#  {'FAM':<6}{'STRATÉGIE':<54}{'n':>4}{'t/j':>5}{'exp':>7}{'t':>5}{'win':>5}"
         f"{'entrée':>7}{'open%':>6}{'CPTE':>8}{'C_OOS':>7}")
    print(h); print('─' * len(h))
    for i, x in r.head(40).iterrows():
        print(f"{i+1:<2} {x.famille:<6}{str(x.strategie)[:52]:<54}{x.n:>4}{x.trj:>5.1f}{x.exp:>+6.2f}%"
              f"{x.t:>5.1f}{x.win:>4.0f}%{x.entry_med:>7}{x.open_pct:>5.0f}%{x.cpte:>+7.1f}%{x.cpte_oos:>+6.1f}%")
    print(f"\n→ {OUT}")


if __name__ == '__main__':
    main()
