#!/usr/bin/env python3
"""Search paramétrique PRICE-ONLY : pour chaque archétype, balaie bande de gap × fenêtre d'entrée ×
seuils propres × SORTIE, et classe par CPTE + robustesse + REPRODUCTIBILITÉ (entrées pas à l'open).
100% prix (aucun volume). Univers PM-liquidité. Entrées détectées UNE fois, sorties balayées par-dessus.
Sortie : results/price_search_results.csv.  ⚠️ petit n : lire robustesse (t, 2 moitiés, OOS), pas un gagnant isolé."""
import os, sys, time, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E, signals as S

N_MIN = 20
OPEN_MAX = 40                                   # reproductibilité : <= X% d'entrées à l'ouverture (<=9:35)
GAPS = [('all', (-100, 9999)), ('3-10', (3, 10)), ('10-20', (10, 20)), ('5-20', (5, 20))]
STARTS = {'9:30': 570, '10:00': 600, '10:30': 630}
ENDS = {'midi': 720, '15:55': 955}
EXITS = {'tp15': dict(exit_mode='tp', tp_pct=0.15), 'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'tp30': dict(exit_mode='tp', tp_pct=0.30), 'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05),
         'eod': dict(exit_mode='eod')}
STOPS = [0.08, 0.10]
# variantes de SEUILS propres à chaque archétype ({} = défauts)
PARAMS = {
    'rsi_bounce': [{'rsi_lo': 30}, {'rsi_lo': 20}], 'williams_bounce': [{'wr_lo': -80}, {'wr_lo': -90}],
    'bb_breakout': [{'squeeze_bw': 0.04}, {'squeeze_bw': 0.06}], 'atr_breakout': [{'atr_k': 1.0}, {'atr_k': 1.5}],
    'keltner_breakout': [{'kelt_mult': 2.0}, {'kelt_mult': 2.5}], 'rsi_divergence': [{'div_win': 20}, {'div_win': 30}],
    'donchian_breakout': [{'don_win': 20}, {'don_win': 30}], 'higher_high_momentum': [{'hh_win': 3}, {'hh_win': 4}],
    'orb_breakout': [{'orb_win': 15}, {'orb_win': 30}], 'macd_cross': [{}], 'ema9_pullback': [{}],
    'bullish_engulfing': [{}], 'sma_reclaim': [{}], 'supertrend_flip': [{}],
}
OUT = os.path.join(HERE, 'results', 'price_search_results.csv')


def substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, a.mean() if n else 0.0, 0.0)
    e, sd = a.mean(), a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def main():
    names = sys.argv[1:] or list(S.REGISTRY)
    groups, dates = bt.load_groups(); liq = E.liquid_groups(groups, thr=0.20)
    split = bt.oos_split(dates); tdays = [d for d in dates if d >= split]; mid = dates[len(dates) // 2]
    wins = [(f"{sl}>{el}", ss, ee) for (sl, ss), (el, ee) in itertools.product(STARTS.items(), ENDS.items()) if ss < ee]
    ncfg = sum(len(PARAMS.get(n, [{}])) for n in names) * len(GAPS) * len(wins)
    print(f"{len(dates)} séances, univers liquide={len(liq)} tj. {ncfg} configs d'ENTRÉE × "
          f"{len(EXITS)*len(STOPS)} sorties. 100% PRIX.\n", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = []; t0 = time.time(); k = 0
    for name in names:
        for pv in PARAMS.get(name, [{}]):
            for (gl, (gmin, gmax)), (wl, ws, we) in itertools.product(GAPS, wins):
                k += 1
                if k % 50 == 0:
                    pd.DataFrame(rows).to_csv(OUT, index=False)
                    print(f"  {k}/{ncfg} ({(time.time()-t0)/60:.0f}min) — {len(rows)} combos", flush=True)
                Pe = dict(gap_min=gmin, gap_max=gmax, entry_start=ws, entry_end=we, **pv)
                ents = E.entries(liq, name, Pe)
                if len(ents) < N_MIN:
                    continue
                em = np.array([int(ind['mins'][i]) for _, ind, i in ents])
                open_pct = round((em <= 575).mean() * 100); entry_med = bt.hhmm(int(np.median(em)))
                pstr = ','.join(f"{a}{b}" for a, b in pv.items()) or '—'
                for exl, ex in EXITS.items():
                    for stp in STOPS:
                        t = E.trades_from(ents, {**ex, 'stop_pct': stp})
                        if len(t) < N_MIN:
                            continue
                        pnl = t.pnl.to_numpy(); _, exp, tt = substat(pnl)
                        _, e_h1, _ = substat(t[t.date < mid].pnl.to_numpy())
                        _, e_h2, _ = substat(t[t.date >= mid].pnl.to_numpy())
                        _, e_te, _ = substat(t[t.date >= split].pnl.to_numpy())
                        _, e_trim, _ = substat(np.sort(pnl)[:-3] if len(pnl) > 3 else pnl)
                        cp, dd = E.portfolio(t, 0.02, stp); cpo, _ = E.portfolio(t, 0.02, stp, days=tdays)
                        rows.append(dict(archetype=name, gap=gl, heure=wl, params=pstr, exit=f"{exl}/s{int(stp*100)}",
                                         n=len(pnl), trj=round(len(pnl) / t.date.nunique(), 1), exp=round(exp, 2),
                                         t=round(tt, 2), e_trim=round(e_trim, 2), win=round((pnl > 0).mean() * 100),
                                         e_h1=round(e_h1, 2), e_h2=round(e_h2, 2), e_te=round(e_te, 2),
                                         entry_med=entry_med, open_pct=open_pct, maxDD=round(dd, 1),
                                         cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                                         robust=bool(e_h1 > 0 and e_h2 > 0 and e_te > 0 and e_trim > 0 and tt >= 2.3),
                                         reproductible=bool(open_pct <= OPEN_MAX)))
        print(f"  {name} fini ({k}/{ncfg}, {len(rows)} combos)", flush=True)
    r = pd.DataFrame(rows); r.to_csv(OUT, index=False)
    good = r[r.robust & r.reproductible]
    print(f"\nFINI {(time.time()-t0)/60:.0f}min. {len(r)} combos. {int(r.robust.sum())} robustes, "
          f"{len(good)} robustes ET reproductibles.\n", flush=True)
    cols = ['archetype', 'gap', 'heure', 'params', 'exit', 'n', 'trj', 'exp', 't', 'win', 'entry_med', 'open_pct', 'cpte', 'cpte_oos']
    if len(good):
        print("===== TOP 25 (robustes + reproductibles) par CPTE =====", flush=True)
        print(good.sort_values('cpte', ascending=False).head(25)[cols].to_string(index=False), flush=True)
    print(f"\nCSV: {OUT}", flush=True)


if __name__ == '__main__':
    main()
