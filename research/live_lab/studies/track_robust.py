#!/usr/bin/env python3
"""PERSISTANCE walk-forward des 2 FAMILLES : rejoue la MÊME analyse à CHAQUE séance passée (fenêtre
expansive, point-in-time) sur les combos ROBUSTES des 2 recherches complètes, pour voir lesquelles
RESTENT en haut au fil des jours (= vraies) vs apparaissent/disparaissent (= bruit du multiple-testing).
  - REPLI     : strategy_search_full_results.csv, re-simulé via bt (univers complet).
  - INDICATEURS : indicator_search_results.csv, re-simulé via E (univers freq-filtré).
Sortie : robust_persistence.csv (famille, combo, %topK, rang/metrics finaux). Relancé chaque soir au cron."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E

REPLI_CSV = os.path.join(HERE, '..', 'results', 'strategy_search_full_results.csv')
INDIC_CSV = os.path.join(HERE, '..', '..', 'indicator_lab', 'results', 'indicator_search_results.csv')
OUT = os.path.join(HERE, '..', 'results', 'robust_persistence.csv')
STARTS = {'9:30': 570, '9:45': 585, '10:00': 600, '10:30': 630}
ENDS = {'midi': 720, '15:55': 955, '10:30': 630}
GAPMAP = {'all': (-100, 9999), '0-50': (0, 50), '50+': (50, 9999)}
MIN_DAYS, TOPK, N_TRACK = 10, 8, 18


def _exit_into(P, exit_str, stop=0.10):
    """'tr10/2/s8' (repli) ou 'trail10/2'/'tp30'/'eod' (indic)."""
    s = str(exit_str)
    if '/s' in s:
        s, stp = s.rsplit('/', 1); stop = int(stp.lstrip('s')) / 100.0
    P['stop_pct'] = stop
    s = s.replace('trail', 'tr')
    if s == 'eod': P['exit_mode'] = 'eod'
    elif s.startswith('tr'):
        a, t = s[2:].split('/'); P.update(exit_mode='trail', activate_pct=int(a) / 100.0, trail_pct=int(t) / 100.0)
    elif s.startswith('tp'): P.update(exit_mode='tp', tp_pct=int(s[2:]) / 100.0)


def repli_P(row):
    P = dict(bt.LIVE)
    gmin, gmax = (float(x) for x in str(row['gap']).split('-'))
    esl, eel = str(row['heures']).split('>'); ind = str(row['indic'])
    P.update(gap_min=gmin, gap_max=gmax, entry_start=STARTS[esl], entry_end=ENDS[eel],
             retrace_pct=float(row['repli']), capit_ratio=float(row['capit']),
             hod_in_rth='hodRTH' in ind, require_green='green' in ind,
             vwap_side='below' if 'vw<' in ind else None,
             recent_active_min=0.8 if 'rAct' in ind else 0.0, recent_active_window=10)
    _exit_into(P, row['exit'])
    return P


def indic_cfg(row):
    gmin, gmax = GAPMAP[str(row['gap'])]
    esl, eel = str(row['heure']).split('>')
    P = dict(gap_min=gmin, gap_max=gmax, entry_start=STARTS[esl], entry_end=ENDS[eel], rvol_gate=float(row['rvol']))
    _exit_into(P, row['exit'])
    return dict(archetype=str(row['archetype']), P=P)


def _pm(r):                              # seuil PM de la ligne (CSV ancien sans la colonne -> 0.20)
    try: return float(r['pm_thr'])
    except (KeyError, ValueError, TypeError): return 0.20


def _let(r):                             # forme du symbole (CSV ancien sans la colonne -> 'all')
    try:
        v = str(r['letters']); return v if v in ('all', '4L') else 'all'
    except (KeyError, ValueError, TypeError): return 'all'


def _lsfx(let):
    return f"/{let}" if let != 'all' else ''


def pick(csv, key, n):
    if not os.path.exists(csv): return []
    d = pd.read_csv(csv)
    d = d[d.robust & (d.t >= 2.3)].sort_values('cpte', ascending=False).drop_duplicates(subset=['n', 'exp', 'cpte'])
    return [(key(row), row) for _, row in d.head(n).iterrows()]


def main():
    groups, dates = bt.load_groups()
    rl = pick(REPLI_CSV, lambda r: f"[R] {r['gap']}/{r['heures']}/r{r['repli']}/cap{r['capit']}/{r['exit']}/{r['indic']}/pm{int(_pm(r)*100)}{_lsfx(_let(r))}", N_TRACK)
    il = pick(INDIC_CSV, lambda r: f"[I] {r['archetype']}/{r['gap']}/rv{r['rvol']}/{r['heure']}/{r['exit']}/pm{int(_pm(r)*100)}{_lsfx(_let(r))}", N_TRACK)
    combos = ([('repli', lbl, repli_P(r), (_pm(r), _let(r))) for lbl, r in rl]
              + [('indic', lbl, indic_cfg(r), (_pm(r), _let(r))) for lbl, r in il])
    keys = {c[3] for c in combos} or {(0.20, 'all')}
    base = {thr: E.liquid_groups(groups, thr=thr) for thr in {k[0] for k in keys}}
    UNIV = {(thr, let): E.shape_groups(base[thr], let) for (thr, let) in keys}    # univers par (seuil PM × forme)
    print(f"{len(dates)} séances. Persistance walk-forward : {len(rl)} repli + {len(il)} indic "
          f"(top-{TOPK}=persistant), {len(keys)} univers (seuil PM × forme), séances {MIN_DAYS}->{len(dates)}.\n", flush=True)
    hist = []
    for i in range(MIN_DAYS - 1, len(dates)):
        upto = dates[i]
        lsub = {key: [g for g in gl if g['date'] <= upto] for key, gl in UNIV.items()}   # univers/(seuil,forme) à ce jour
        day = []
        for fam, lbl, cfg, key in combos:
            u = lsub[key]
            t = bt.simulate(u, cfg, slip=True) if fam == 'repli' else E.simulate(u, cfg['archetype'], cfg['P'])
            if not len(t): continue
            stop = cfg['stop_pct'] if fam == 'repli' else cfg['P'].get('stop_pct', 0.10)
            cp, _ = portfolio(t, 0.02, stop)
            day.append((fam, lbl, cp, round(t.pnl.mean(), 2)))
        day.sort(key=lambda x: -x[2])
        for rank, (fam, lbl, cp, exp) in enumerate(day, 1):
            hist.append(dict(upto=upto, n_days=i + 1, famille=fam, combo=lbl, rank=rank, cpte=round(cp, 1), exp=exp))
    h = pd.DataFrame(hist); h.to_csv(OUT, index=False)
    chk = h.n_days.nunique(); last = h[h.upto == dates[-1]].set_index('combo')
    persist = (h[h['rank'] <= TOPK].groupby('combo').size() / chk * 100).round().sort_values(ascending=False)
    print(f"PERSISTANCE sur {chk} points de contrôle (toutes familles mêlées, classées par CPTE chaque jour) :")
    print(f"  {'combo':<58}{'%top'+str(TOPK):>7}{'rang_fin':>9}{'exp':>7}")
    for name, pct in persist.head(22).items():
        rk = int(last.loc[name, 'rank']) if name in last.index else '-'
        ex = last.loc[name, 'exp'] if name in last.index else 0
        print(f"  {name[:58]:<58}{pct:>6.0f}%{str(rk):>9}{ex:>+7.2f}")
    print(f"\n-> %top{TOPK} élevé = RESTE en haut au fil des séances (robuste). [R]=repli [I]=indicateurs.")
    print(f"CSV : {OUT}")


if __name__ == '__main__':
    main()
