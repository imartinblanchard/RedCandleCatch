#!/usr/bin/env python3
"""GÉNÉRATEUR de stratégies : au lieu d'un menu fixe d'archétypes, ASSEMBLE des règles d'achat
à partir de ~24 briques (conditions par bougie), combos de 1 ou 2 briques, et les teste toutes
sur l'univers LARGE (bars-*.parquet) × gap × fenêtre × sortie × stop × liquidité. Classe par
ROBUSTESSE (OOS + 2 moitiés + t). Réutilise le moteur price_lab (engine/indicators/backtest).

⚠️ ÉNORME risque de faux positifs (45 j × ~500k configs) : ne RIEN prendre pour argent comptant,
lire la robustesse. Le nightly re-testera la liste courte sur la data accumulée.

Usage : python -m research.live_lab.strategy_gen            (recherche complète)
        python -m research.live_lab.strategy_gen --calib    (mesure la vitesse sur un échantillon)
        python -m research.live_lab.strategy_gen --validate (prouve que (rsi^20 & green) == archétype rsi_bounce)
"""
import os, sys, time, itertools, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import backtest as bt
from research.price_lab import engine as E

PM_LO, PM_HI = 480, 570
GAPS = [('3-5', 3, 5), ('5-7', 5, 7), ('7-10', 7, 10), ('10-14', 10, 14), ('14-20', 14, 20),
        ('20-30', 20, 30), ('30-50', 30, 50), ('50-70', 50, 70), ('70-90', 70, 90),
        ('90-120', 90, 120), ('120-160', 120, 160), ('160-220', 160, 220), ('220-500', 220, 500),
        ('all', -100, 9999)]
WINS = [('9:30>midi', 570, 720), ('9:30>15:55', 570, 955)]
EXITS = {'tp15': dict(exit_mode='tp', tp_pct=0.15), 'tp20': dict(exit_mode='tp', tp_pct=0.20),
         'trail10/5': dict(exit_mode='trail', activate_pct=0.10, trail_pct=0.05), 'eod': dict(exit_mode='eod')}
STOPS = [0.08, 0.10]
LIQ = [('none', None, None), ('pm0.20', 'pm', 0.20), ('pm0.35', 'pm', 0.35),
       ('act30>=10', 'entry', ('act_30', 10)), ('act30>=15', 'entry', ('act_30', 15)),
       ('dvol30>=100k', 'entry', ('dvol_30', 100_000)), ('dvol30>=200k', 'entry', ('dvol_30', 200_000))]
N_MIN = 30
OUT = os.path.join(HERE, 'results', 'strategy_gen-results.csv')


def _cross_up(x, thr):
    x = np.asarray(x, float); out = np.zeros(len(x), bool)
    out[1:] = (x[:-1] < thr) & (x[1:] >= thr); return out


def _rising(c, n):
    c = np.asarray(c, float); inc = np.zeros(len(c), bool); inc[1:] = c[1:] > c[:-1]
    run = np.zeros(len(c), int)
    for i in range(len(c)):
        run[i] = run[i - 1] + 1 if (i > 0 and inc[i]) else (1 if inc[i] else 0)
    return run >= n


# ~24 BRIQUES : nom -> fonction(ind) -> tableau booléen par bougie (CAUSAL)
PRIMS = {
    'rsi<30':    lambda d: d['rsi'] < 30,
    'rsi^20':    lambda d: _cross_up(d['rsi'], 20),
    'rsi^30':    lambda d: _cross_up(d['rsi'], 30),
    'rsi>50':    lambda d: d['rsi'] > 50,
    'stoch<20':  lambda d: d['stoch_k'] < 20,
    'stoch^20':  lambda d: _cross_up(d['stoch_k'], 20),
    'will<-80':  lambda d: d['wr'] < -80,
    'cci<-100':  lambda d: d['cci'] < -100,
    'cci>100':   lambda d: d['cci'] > 100,
    'c<bbLo':    lambda d: d['c'] < d['bb_lo'],
    'c>bbUp':    lambda d: d['c'] > d['bb_up'],
    'c>ema9':    lambda d: d['c'] > d['ema9'],
    'c>ema20':   lambda d: d['c'] > d['ema20'],
    'c>ema50':   lambda d: d['c'] > d['ema50'],
    'ema9>ema20': lambda d: d['ema9'] > d['ema20'],
    'c>sma20':   lambda d: d['c'] > d['sma20'],
    'roc>0':     lambda d: d['roc'] > 0,
    'macd>0':    lambda d: d['macd_hist'] > 0,
    'macd^0':    lambda d: _cross_up(d['macd_hist'], 0),
    'newHOD':    lambda d: d['h'] >= d['hod'],
    'c>prevH':   lambda d: np.concatenate(([False], d['c'][1:] > d['h'][:-1])),
    'hh2':       lambda d: _rising(d['c'], 2),
    'hh3':       lambda d: _rising(d['c'], 3),
    'green':     lambda d: d['green'],
}
NAMES = list(PRIMS)


def prep(groups):
    """Précalcule, par ticker-jour : arrays utiles + les 24 briques booléennes (une seule fois)."""
    P = []
    for g in groups:
        ind = E._ind(g)
        prims = np.stack([np.asarray(PRIMS[n](ind), bool) for n in NAMES])   # (24, nbars)
        P.append(dict(g=g, mins=np.asarray(ind['mins']), c=np.asarray(ind['c'], float),
                      gap=np.asarray(ind['gap'], float), act_30=ind['act_30'], dvol_30=ind['dvol_30'],
                      pm=sum(1 for mn, vv in zip(ind['mins'], ind['v']) if PM_LO <= mn < PM_HI and vv > 0) / (PM_HI - PM_LO),
                      prims=prims))
    return P


def entries(prepped, ci, cj, gmin, gmax, ws, we, liqkind, liqarg):
    """Liste (elem, i) : 1re bougie passant gap/prix/fenêtre/liquidité ET les briques ci(&cj)."""
    out = []
    for e in prepped:
        if liqkind == 'pm' and e['pm'] < liqarg:
            continue
        mask = e['prims'][ci] if cj is None else (e['prims'][ci] & e['prims'][cj])
        gate = ((e['mins'] >= ws) & (e['mins'] <= we) & (e['c'] >= 3.0) & (e['c'] <= 20.0) &
                (e['gap'] >= gmin) & (e['gap'] <= gmax) & mask)
        if liqkind == 'entry':
            gate = gate & (e[liqarg[0]] >= liqarg[1])
        idx = np.argmax(gate)
        if gate[idx]:
            out.append((e, int(idx)))
    return out


def eval_exits(ents, dates, split):
    """Pour un jeu d'entrées, balaie sorties×stops -> lignes de résultat robustes/non."""
    rows = []
    for exl, ex_ in EXITS.items():
        for stp in STOPS:
            Q = dict(E.DEFAULTS); Q.update(ex_); Q['stop_pct'] = stp
            recs = [dict(ticker=e['g']['tk'], date=e['g']['date'], entry_min=int(e['mins'][i]),
                         entry=round(float(e['c'][i]), 4), gap=round(float(e['gap'][i]), 1),
                         pnl=round(bt._pnl(e['g'], i, Q, True), 3)) for e, i in ents]
            df = pd.DataFrame(recs)
            if len(df) < N_MIN:
                continue
            r = E.evaluate(df, dates, split, stop_pct=stp)
            if not r:
                continue
            r['robust'] = bool(r['e_h1'] > 0 and r['e_h2'] > 0 and r['t'] >= 2 and r['cpte_oos'] > 0)
            rows.append((exl, stp, r))
    return rows


def combos():
    singles = [(i, None) for i in range(len(NAMES))]
    pairs = [(i, j) for i, j in itertools.combinations(range(len(NAMES)), 2)]
    return singles + pairs


def main(mode):
    groups, dates = bt.load_groups()
    ex = E.excluded_set()
    groups = [g for g in groups if (g['tk'], g['date']) not in ex]
    split = bt.oos_split(dates)
    t0 = time.time(); prepped = prep(groups); t_prep = time.time() - t0
    cmb = combos()
    ncfg = len(cmb) * len(GAPS) * len(WINS) * len(LIQ) * len(EXITS) * len(STOPS)
    print(f"univers {len(groups)} ticker-jours · {len(dates)} séances · OOS {split}", flush=True)
    print(f"briques {len(NAMES)} · combos {len(cmb)} (1-2) · configs totales {ncfg:,} · prep {t_prep:.0f}s", flush=True)

    if mode == 'validate':
        ci, cj = NAMES.index('rsi^20'), NAMES.index('green')
        ents = entries(prepped, ci, cj, 3, 10, 570, 720, None, None)
        arche = E.entries(E.liquid_groups(groups, thr=0.0) if False else groups, 'rsi_bounce',
                          dict(gap_min=3, gap_max=10, entry_start=570, entry_end=720, rsi_lo=20))
        a = sorted((e['g']['tk'], e['g']['date'], i) for e, i in ents)
        b = sorted((g['tk'], g['date'], i) for g, ind, i in arche)
        print(f"(rsi^20 & green) gap3-10 : généré {len(a)} vs archétype rsi_bounce {len(b)} -> "
              f"{'✅ IDENTIQUE' if a == b else '⚠️ DIFFÉRENT'}")
        return

    # échantillon pour calibrer le temps : 1 combo complet (toutes dims) -> extrapolation
    sample = cmb[:1] if mode == 'calib' else cmb
    t1 = time.time(); done = 0; rows = []
    for ci, cj in sample:
        for (gl, gmin, gmax), (wl, ws, we) in itertools.product(GAPS, WINS):
            for liql, lk, la in LIQ:
                ents = entries(prepped, ci, cj, gmin, gmax, ws, we, lk, la)
                for exl, stp, r in eval_exits(ents, dates, split):
                    nm = NAMES[ci] + ('' if cj is None else ' & ' + NAMES[cj])
                    rows.append(dict(regle=nm, gap=gl, heure=wl, liq=liql, exit=f'{exl}/s{int(stp*100)}',
                                     **{c: r[c] for c in ['n', 'trj', 'exp', 't', 'win', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust']}))
                done += len(EXITS) * len(STOPS)
    dt = time.time() - t1
    if mode == 'calib':
        per = dt / max(done, 1)
        tot = per * ncfg
        print(f"\ncalibration : {done} configs en {dt:.1f}s -> {per*1000:.1f} ms/config")
        print(f"ESTIMATION recherche complète ({ncfg:,} configs) : {tot/3600:.1f} h  (~{tot/3600/24:.1f} jours) + prep {t_prep:.0f}s")
        return
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\n{done} configs testées en {dt/3600:.1f}h -> {OUT} ({len(rows)} gardées n>={N_MIN})")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--calib', action='store_true')
    ap.add_argument('--validate', action='store_true')
    a = ap.parse_args()
    main('calib' if a.calib else 'validate' if a.validate else 'full')
