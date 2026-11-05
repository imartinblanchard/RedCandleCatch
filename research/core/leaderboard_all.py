#!/usr/bin/env python3
"""LEADERBOARD UNIFIÉ — un SEUL tableau fiable, trié par robustesse réelle, nettoyé tout seul.

Rassemble toutes les stratégies (candidates curées + TOP des recherches nightly), les mesure
TOUTES avec la MÊME fonction (live_lab.leaderboard.portfolio, 2%, univers freq-filtré = ce qu'on
trade), calcule leur PERSISTANCE walk-forward (fréquence de présence dans le top au fil des séances
= le séparateur vrai-edge / bruit), ENLÈVE les obsolètes (non-robustes & non-persistantes), et trie
par un SCORE composite qui combine persistance + CPTE + win. 100% automatique (relancé au cron).

Score = 0.45·persistance + 0.35·CPTE + 0.20·win (normalisés). La persistance mène : on a vu
(04/11) qu'un beau win/CPTE in-sample — obv_divergence 84%, trail5/2 — s'effondre dans le temps
(6%/18% de persistance) alors que vwap_reclaim tient (100%). Le tri ne se laisse plus piéger.

Usage : python research/core/leaderboard_all.py [--top 100] [--status deployed|candidate]
         [--keep-obsolete] [--no-persist] (rapide, saute le walk-forward)
Sorties : leaderboard_all_latest.csv (tableau unifié) + leaderboard_all_history.csv (suivi curées).
⚠️ Données live courtes = BRUIT ; la persistance atténue, ne supprime pas. Lire n + OOS."""
import os, sys, argparse, datetime as dt
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from research.live_lab import backtest as bt
from research.live_lab.leaderboard import portfolio
from research.indicator_lab import engine as E
from research.indicator_lab.engine import liquid_groups
# rebuild des configs des lignes de recherche (source unique, partagée avec track_robust)
from research.live_lab.studies.track_robust import repli_P, indic_cfg

from research.live_lab.candidates import CANDIDATES as REPLI
from research.indicator_lab.candidates import CANDIDATES as INDIC
REGISTRIES = [REPLI, INDIC]

def _pm(x):                              # seuil PM de la ligne (CSV ancien sans la colonne -> 0.20)
    try: return float(x['pm_thr'])
    except (KeyError, ValueError, TypeError): return 0.20


SEARCHES = [('repli', os.path.join(ROOT, 'research/live_lab/results/strategy_search_full_results.csv'),
             lambda x: f"{x['gap']}/{x['heures']}/r{x['repli']}/cap{x['capit']}/{x['exit']}/{x['indic']}/pm{int(_pm(x)*100)}",
             lambda x: (lambda P: (lambda u, P=P: bt.simulate(u, P, slip=True), P['stop_pct']))(repli_P(x))),
            ('indic', os.path.join(ROOT, 'research/indicator_lab/results/indicator_search_results.csv'),
             lambda x: f"{x['archetype']}/rv{x['rvol']}/{x['heure']}/{x['exit']}/pm{int(_pm(x)*100)}",
             lambda x: (lambda c: (lambda u, c=c: E.simulate(u, c['archetype'], c['P']),
                                   c['P'].get('stop_pct', 0.10)))(indic_cfg(x)))]
TY = 252
PER_FAMILY = 48                         # top-N robustes de chaque recherche à injecter
MIN_DAYS, TOPK = 10, 8                  # persistance : fenêtres >= MIN_DAYS, top-K/jour = persistant
WEIGHTS = dict(persist=0.45, cpte=0.35, win=0.20)    # score composite (persistance en tête)


def _substat(a):
    a = np.asarray(a, float); n = len(a)
    if n < 2: return (n, a.mean() if n else 0.0, 0.0)
    e, sd = a.mean(), a.std(ddof=1)
    return (n, e, e / (sd / np.sqrt(n)) if sd > 0 else 0.0)


def collect_strats(status_filter):
    """Toutes les stratégies à classer : curées (Strategy) + top des recherches (configs rebuildées).
    Chacune -> dict{name, family, status, sim(universe)->trades, stop, notes}. Univers = freq-filtré."""
    S = []
    for reg in REGISTRIES:
        for s in reg:
            if status_filter and s.status != status_filter:
                continue
            # univers curé = 'freq-filtré' -> seuil PM par défaut 0.20 (celui du filtre déployé)
            S.append(dict(name=s.name, family=s.family, status=s.status, sim=s.sim, stop=s.stop,
                          pm_thr=0.20, notes=s.notes))
    if status_filter:
        return S
    for fam, path, namer, builder in SEARCHES:
        if not os.path.exists(path):
            continue
        d = pd.read_csv(path)
        d = d[d.robust].sort_values('cpte', ascending=False).head(PER_FAMILY)
        for _, x in d.iterrows():
            sim, stop = builder(x)
            S.append(dict(name=str(namer(x))[:52], family=fam, status='search', sim=sim, stop=stop,
                          pm_thr=_pm(x), notes='top recherche'))
    # dédup par nom (garde la 1re occurrence — une curée l'emporte sur une ligne search homonyme)
    seen, out = set(), []
    for s in S:
        if s['name'] in seen:
            continue
        seen.add(s['name']); out.append(s)
    return out


def persistence(strats, UNIV, dates):
    """Walk-forward : à chaque séance passée (fenêtre expansive), classe TOUTES les stratégies par
    CPTE sur l'univers connu à ce jour (CHACUNE sur son propre seuil PM) ; %persist = fréquence de
    présence dans le top-K. Séparateur vrai-edge / artefact-de-récence (indépendant de la data finale)."""
    ctrl = list(range(MIN_DAYS - 1, len(dates)))
    hits = {s['name']: 0 for s in strats}
    for i in ctrl:
        upto = dates[i]
        lsub = {thr: [g for g in gl if g['date'] <= upto] for thr, gl in UNIV.items()}   # univers/seuil à ce jour
        day = []
        for s in strats:
            t = s['sim'](lsub[s['pm_thr']])
            if t is None or not len(t):
                continue
            cp, _ = portfolio(t, 0.02, s['stop'])
            day.append((s['name'], cp))
        day.sort(key=lambda x: -x[1])
        for name, _ in day[:TOPK]:
            hits[name] += 1
    n = max(len(ctrl), 1)
    return {k: round(v / n * 100) for k, v in hits.items()}


def main(top, status_filter, keep_obsolete, do_persist):
    groups, dates = bt.load_groups()
    split = bt.oos_split(dates); tdays = [d for d in dates if split and d >= split]; mid = dates[len(dates) // 2]
    nd, ndo = len(dates), max(len(tdays), 1)
    strats = collect_strats(status_filter)
    thrs = sorted({s['pm_thr'] for s in strats})
    UNIV = {thr: liquid_groups(groups, thr=thr) for thr in thrs}     # univers par seuil PM (DIMENSION)

    if do_persist:
        persist = persistence(strats, UNIV, dates)
    else:                                # aperçu rapide : reprend la persistance du dernier run COMPLET
        prev = os.path.join(HERE, 'leaderboard_all_latest.csv')
        persist = {}
        if os.path.exists(prev):
            p = pd.read_csv(prev)
            if 'persist' in p and 'strategie' in p:
                persist = {k: v for k, v in zip(p.strategie, p.persist) if pd.notna(v)}
    rows = []
    for s in strats:
        t = s['sim'](UNIV[s['pm_thr']])              # CHAQUE stratégie sur son univers (seuil PM)
        if t is None or not len(t):
            continue
        pnl = t.pnl.to_numpy(); n = len(pnl)
        _, exp, tstat = _substat(pnl)
        _, e_h1, _ = _substat(t[t.date < mid].pnl.to_numpy())
        _, e_h2, _ = _substat(t[t.date >= mid].pnl.to_numpy())
        te = t[t.date >= split].pnl if split else pd.Series(dtype=float)
        e_trim = np.sort(pnl)[:-3].mean() if n > 3 else pnl.mean()
        cp, dd = portfolio(t, 0.02, s['stop']); cpo, _ = portfolio(t, 0.02, s['stop'], days=tdays)
        pz = persist.get(s['name'], np.nan)
        # robuste = positive sur les 2 moitiés + OOS + non-fragile + significative (proxy in-table)
        robust = bool(e_h1 > 0 and e_h2 > 0 and (not len(te) or te.mean() > 0) and e_trim > 0 and tstat >= 2.0)
        rows.append(dict(famille=s['family'], statut=s['status'], strategie=s['name'], univers=f"PM{int(s['pm_thr']*100)}%",
                         n=n, tr_day=round(n / t.date.nunique(), 1), exp=round(exp, 2), t=round(tstat, 1),
                         e_trim=round(e_trim, 2), exp_oos=round(te.mean(), 2) if len(te) else np.nan,
                         win=round((pnl > 0).mean() * 100), persist=pz, cpte=round(cp, 1), cpte_oos=round(cpo, 1),
                         an=round(cp * TY / nd), an_oos=round(cpo * TY / ndo), maxDD=round(dd, 1),
                         robust=robust, notes=s['notes']))
    r = pd.DataFrame(rows)

    # ── NETTOYAGE auto : enlève les obsolètes (ni robustes ni persistantes), garde toujours le déployé ──
    if not keep_obsolete and len(r):
        pz = r['persist'].fillna(0)
        keep = (r.statut == 'deployed') | r.robust | (pz >= 20)
        n_drop = int((~keep).sum())
        r = r[keep].copy()
    else:
        n_drop = 0

    # ── SCORE composite : persistance (tête) + CPTE + win, normalisés sur l'ensemble gardé ──
    def nm(c):
        x = r[c].astype(float)
        x = x.fillna(x.min() if x.notna().any() else 0.0)     # colonne tout-NaN (ex. --no-persist) -> 0, terme neutre
        return (x - x.min()) / (x.max() - x.min() + 1e-9)
    if len(r):
        r['score'] = (WEIGHTS['persist'] * nm('persist') + WEIGHTS['cpte'] * nm('cpte')
                      + WEIGHTS['win'] * nm('win')).round(3)
        r = r.sort_values('score', ascending=False).reset_index(drop=True)

    print(f"\nDonnées : {nd} séances live ({dates[0]}..{dates[-1]}) | sizing 2%, slip ON, univers freq-filtré")
    print(f"SCORE = {WEIGHTS['persist']}·persist + {WEIGHTS['cpte']}·CPTE + {WEIGHTS['win']}·win (normalisés). "
          f"persist = % du temps dans le top {TOPK} au fil des séances (vrai-edge vs bruit).")
    print(f"Nettoyage : {n_drop} obsolètes retirées (ni robustes ni persist>=20%, hors déployé). "
          f"{len(r)} stratégies classées. C_OOS/persist = SUIVI, décider sur l'ensemble.\n")
    h = (f"#  {'FAM':<6}{'STATUT':<9}{'STRATÉGIE':<40}{'n':>4}{'t/j':>5}{'exp':>7}{'t':>5}"
         f"{'win':>5}{'persist':>8}{'CPTE':>8}{'C_OOS':>8}{'DD':>6}{'score':>6}")
    print(h); print("─" * len(h))
    for i, x in r.head(top).iterrows():
        pz = '—' if pd.isna(x.persist) else f"{x.persist:.0f}%"
        print(f"{i+1:<2} {x.famille:<6}{x.statut:<9}{str(x.strategie)[:38]:<40}{x.n:>4}{x.tr_day:>5.1f}"
              f"{x.exp:>+6.2f}%{x.t:>5.1f}{x.win:>4.0f}%{pz:>8}{x.cpte:>+7.1f}%{x.cpte_oos:>+7.1f}%"
              f"{x.maxDD:>+5.1f}%{x.score:>6.2f}")

    r.to_csv(os.path.join(HERE, 'leaderboard_all_latest.csv'), index=False)
    hist = os.path.join(HERE, 'leaderboard_all_history.csv')
    run_id = dt.datetime.now().isoformat(timespec='seconds')
    h2 = r[r.statut != 'search'][['famille', 'statut', 'strategie', 'n', 'tr_day', 'exp', 'exp_oos',
            'win', 'persist', 'cpte', 'cpte_oos', 'maxDD', 'score']].copy()   # suivi longitudinal = curées
    h2.insert(0, 'couvre', f"{dates[0]}..{dates[-1]}"); h2.insert(0, 'n_days', nd); h2.insert(0, 'run', run_id)
    h2.to_csv(hist, mode='a', header=not os.path.exists(hist), index=False)
    print(f"\n→ leaderboard_all_latest.csv (tableau unifié trié) | leaderboard_all_history.csv (suivi curées)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=100)
    ap.add_argument('--status', default=None, help='filtrer : deployed | candidate | archived')
    ap.add_argument('--keep-obsolete', action='store_true', help='ne pas retirer les obsolètes')
    ap.add_argument('--no-persist', action='store_true', help='saute le walk-forward (rapide)')
    a = ap.parse_args(); main(a.top, a.status, a.keep_obsolete, not a.no_persist)
