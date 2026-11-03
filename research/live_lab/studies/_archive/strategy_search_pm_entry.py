#!/usr/bin/env python3
"""Étape 2 (PM entry) : autorise les entrées DÈS 04:00, gatées par K minutes consécutives de
trades (idée Martin 29/10). Le gate causal = recent_active_min=1.0 / window=K (les K dernières
minutes TOUTES actives = K min consécutives). On neutralise les filtres anti-couteau (runup/
gap-open) qui se calculent sur l'open RTH et n'ont pas de sens en PM.

Dimensions : fenêtre d'entrée x K x repli x HOD x sortie. On rapporte aussi l'HEURE MÉDIANE
d'entrée (pour voir si ça entre vraiment tôt) + stabilité (e_trim sans 3 meilleurs, maxDD) + CPTE.
collected_live uniquement.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio

N_MIN = 15                      # seuil bas : setup très sélectif, on s'attend à peu de trades
WINDOWS = [('PM04-RTH', 240, 955), ('PM04-0930', 240, 570), ('RTH', 570, 955)]
KGATE = [('gate-off', 0, 10), ('K15', 1.0, 15), ('K30', 1.0, 30), ('K45', 1.0, 45)]  # (label, recent_active_min, window)
RETR = [0.08, 0.12]
HOD = [('', False), ('hodRTH', True)]
EXITS = [('eod', dict(exit_mode='eod')),
         ('trail10/2', dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.02))]
OUT = os.path.join(HERE, '..', 'results', 'strategy_search_pm_entry_results.csv')


def hhmm(m):
    return f"{int(m)//60:02d}:{int(m)%60:02d}" if m == m else "--"


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, a.mean() if n else 0.0, 0.0)
    e = a.mean(); sd = a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]
    mid = dates[len(dates) // 2]
    combos = list(itertools.product(WINDOWS, KGATE, RETR, HOD, EXITS))
    print(f"{len(dates)} séances, OOS≥{split} | {len(combos)} combos", flush=True)
    rows = []; t0 = time.time()
    for (wl, es, ee), (kl, ram, raw), rp, (hl, hv), (exl, exu) in combos:
        P = dict(bt.LIVE); P.update(exu)
        P.update(gap_min=5.0, gap_max=50.0, entry_start=es, entry_end=ee, retrace_pct=rp,
                 capit_ratio=-1, hod_in_rth=hv, require_green=False, vwap_side=None,
                 recent_active_min=ram, recent_active_window=raw,
                 runup_min=0, gap_open_min=None, gap_now_min=None)   # anti-couteau neutralisé (PM)
        t = bt.simulate(groups, P, slip=True)
        n = len(t)
        if n < N_MIN:
            rows.append(dict(fenetre=wl, gate=kl, repli=rp, hod=hl or '-', sortie=exl, n=n,
                             trj=round(n / max(t.date.nunique(), 1), 1) if n else 0,
                             h_med='--', exp=np.nan, t=np.nan, pf=np.nan, win=np.nan,
                             e_trim=np.nan, maxDD=np.nan, cpte=np.nan, cpte_oos=np.nan))
            continue
        pnl = t.pnl.to_numpy(); srt = np.sort(pnl)
        _, exp, tt = substat(pnl)
        e_trim = srt[:-3].mean() if n > 3 else pnl.mean()
        _, e_h1, _ = substat(t[t.date < mid].pnl.to_numpy())
        _, e_h2, _ = substat(t[t.date >= mid].pnl.to_numpy())
        _, e_te, _ = substat(t[t.date >= split].pnl.to_numpy())
        pf = pnl[pnl > 0].sum() / (-pnl[pnl < 0].sum() or 1e-9)
        cpte, dd = portfolio(t, 0.02, P['stop_pct'])
        cpte_o, _ = portfolio(t, 0.02, P['stop_pct'], days=tdays)
        rows.append(dict(fenetre=wl, gate=kl, repli=rp, hod=hl or '-', sortie=exl, n=n,
                         trj=round(n / t.date.nunique(), 1), h_med=hhmm(t.entry_min.median()),
                         exp=round(exp, 2), t=round(tt, 2), pf=round(pf, 2), win=round((pnl > 0).mean() * 100),
                         e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2),
                         e_trim=round(e_trim, 2), maxDD=round(dd, 1), cpte=round(cpte, 1), cpte_oos=round(cpte_o, 1)))
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    print(f"FINI en {(time.time()-t0)/60:.1f}min. CSV -> {OUT}\n", flush=True)
    cols = ['fenetre', 'gate', 'repli', 'hod', 'sortie', 'n', 'trj', 'h_med', 'exp', 't', 'pf',
            'win', 'e_trim', 'maxDD', 'cpte', 'cpte_oos']
    have = r[r.n >= N_MIN].sort_values('cpte', ascending=False)
    print(f"===== Combos avec n>={N_MIN} ({len(have)}) — par CPTE =====", flush=True)
    print((have[cols].to_string(index=False) if len(have) else "  AUCUN combo n>=15 (le gate PM est trop sélectif)"), flush=True)
    print("\n===== Combien d'entrées PM (avant 09:30) par combo n>=15 =====", flush=True)
    print("  (h_med < 09:30 => des entrées réellement pré-marché)", flush=True)


if __name__ == '__main__':
    main()
