#!/usr/bin/env python3
"""BILLBOARD nightly (incrémental). Chaque soir :
  1. teste TOUTES les configs (~300k : 24 briques × combos 1-2 × fenêtre × liq × sortie × stop)
     sur LA SEULE journée du jour, point-in-time (entrée >= band_arrival), par bande ;
  2. APPEND les stats suffisantes du jour -> daily-stats.parquet (immuable, jamais recalculé) ;
  3. RECOMPOSE billboard.csv depuis TOUT le log (cumul + robustesse, toutes nos colonnes) + gagnante du jour.

Rapide (une journée). Le gros search_bands (découverte) reste un one-off manuel.
Usage : python -m research.live_lab.nightly_billboard            (jour courant ET)
        python -m research.live_lab.nightly_billboard --date 2026-11-19
"""
import os, sys, glob, argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from research.live_lab import strategy_gen as sg
from research.live_lab import backtest as bt
from research.live_lab import leaderboard as lb        # portfolio() : sizing contraint capital
from research.price_lab import engine as E

BANDS_DIR = os.path.join(HERE, 'bands')
LOG = os.path.join(HERE, 'results', 'daily-stats.parquet')
BOARD = os.path.join(HERE, 'results', 'billboard.csv')


def entries_pit(band_prepped, ci, cj, ws, we, lk, la):
    out = []
    for e, amin in band_prepped:
        if lk == 'pm' and e['pm'] < la:
            continue
        mask = e['prims'][ci] if cj is None else (e['prims'][ci] & e['prims'][cj])
        gate = ((e['mins'] >= max(ws, amin)) & (e['mins'] <= we) & (e['c'] >= 3.0) & (e['c'] <= 20.0) & mask)
        if lk == 'entry':
            gate = gate & (e[la[0]] >= la[1])
        j = int(np.argmax(gate))
        if gate[j]:
            out.append((e, j))
    return out


def compute_day(day):
    """Stats suffisantes par config pour LA journée `day`. -> DataFrame (une ligne/config qui a tradé)."""
    groups, _ = bt.load_groups()
    ex = E.excluded_set()
    gday = [g for g in groups if g['date'] == day and (g['tk'], g['date']) not in ex]
    if not gday:
        print(f"[{day}] aucun ticker-jour -> rien", flush=True); return pd.DataFrame()
    prepped = sg.prep(gday)
    idx = {(e['g']['tk'], e['g']['date']): e for e in prepped}
    cmb = sg.combos()
    rows = []
    for bf in sorted(glob.glob(os.path.join(BANDS_DIR, 'band-*.parquet'))):
        band = os.path.basename(bf)[len('band-'):-len('.parquet')]
        bdf = pd.read_parquet(bf); bdf = bdf[bdf.date == day]
        bp = [(idx[(t, d)], int(a)) for t, d, a in zip(bdf.ticker, bdf.date, bdf.band_arrival_min) if (t, d) in idx]
        if not bp:
            continue
        for ci, cj in cmb:
            nm = sg.NAMES[ci] + ('' if cj is None else ' & ' + sg.NAMES[cj])
            for wl, ws, we in sg.WINS:
                for liql, lk, la in sg.LIQ:
                    ents = entries_pit(bp, ci, cj, ws, we, lk, la)
                    if not ents:
                        continue
                    ems = np.array([int(e['mins'][i]) for e, i in ents])
                    for exl, ex_ in sg.EXITS.items():
                        for stp in sg.STOPS:
                            Q = dict(E.DEFAULTS); Q.update(ex_); Q['stop_pct'] = stp
                            pnl = np.array([bt._pnl(e['g'], i, Q, True) for e, i in ents], float)
                            rows.append(dict(date=day, regle=nm, band=band, heure=wl, liq=liql,
                                             exit=f'{exl}/s{int(stp*100)}', n=len(pnl),
                                             sum_pnl=float(pnl.sum()), sumsq_pnl=float((pnl**2).sum()),
                                             n_win=int((pnl > 0).sum()), open_n=int((ems <= 575).sum()),
                                             sum_win=float(pnl[pnl > 0].sum()),       # R:R : somme des gains
                                             sum_loss=float(pnl[pnl <= 0].sum()),     # R:R : somme des pertes
                                             entry_med=int(np.median(ems))))
    return pd.DataFrame(rows)


def rebuild_board():
    """Agrège TOUT daily-stats.parquet par config -> billboard (cumul + robustesse)."""
    log = pd.read_parquet(LOG)
    dates = sorted(log.date.unique()); split = bt.oos_split(dates); mid = dates[len(dates) // 2]
    KEY = ['regle', 'band', 'heure', 'liq', 'exit']
    out = []
    for key, g in log.groupby(KEY):
        n = int(g.n.sum())
        if n < sg.N_MIN:
            continue
        sm = g.sum_pnl.sum(); ssq = g.sumsq_pnl.sum()
        exp = sm / n; var = max((ssq - sm * sm / n) / (n - 1), 0) if n > 1 else 0
        sd = var ** 0.5; t = exp / (sd / np.sqrt(n)) if sd > 0 else 0
        win = 100 * g.n_win.sum() / n; open_pct = 100 * g.open_n.sum() / n
        nw = int(g.n_win.sum()); nl = n - nw                 # R:R réalisé (gain moy / perte moy)
        gm = g.sum_win.sum() / nw if nw else 0.0; pm_ = g.sum_loss.sum() / nl if nl else 0.0
        rr = gm / abs(pm_) if pm_ < 0 else 0.0
        be = abs(pm_) / (gm + abs(pm_)) * 100 if (gm + abs(pm_)) > 0 else 0.0   # win% seuil rentabilité
        gh1 = g[g.date < mid]; gh2 = g[g.date >= mid]; gte = g[g.date >= split] if split else g
        eh1 = gh1.sum_pnl.sum() / gh1.n.sum() if gh1.n.sum() else 0
        eh2 = gh2.sum_pnl.sum() / gh2.n.sum() if gh2.n.sum() else 0
        ete = gte.sum_pnl.sum() / gte.n.sum() if gte.n.sum() else 0
        # cpte/maxDD : courbe d'équité JOUR par jour (approx sans cap MAXPOS)
        stp = float(g.exit.iloc[0].split('/s')[1]) / 100
        avg_day = n / g.date.nunique(); posfrac = min(min(0.02 / stp, lb.POSCAP), lb.EXPCAP / avg_day)
        daily = g.groupby('date').sum_pnl.sum().reindex(dates).fillna(0.0)
        eq = 1.0; curve = [1.0]
        for d in dates:
            eq += eq * posfrac * (daily[d] / 100.0); curve.append(eq)
        curve = np.array(curve); peak = np.maximum.accumulate(curve)
        cpte = (eq - 1) * 100; maxdd = ((curve - peak) / peak).min() * 100
        tdays = [d for d in dates if split and d >= split]
        eqo = 1.0
        for d in tdays:
            eqo += eqo * posfrac * (daily[d] / 100.0)
        robust = bool(eh1 > 0 and eh2 > 0 and t >= 2 and (eqo - 1) > 0)
        out.append(dict(regle=key[0], band=key[1], heure=key[2], liq=key[3], exit=key[4],
                        n=n, trj=round(avg_day, 1), exp=round(exp, 2), t=round(t, 2), win=round(win),
                        gain_moy=round(gm, 2), perte_moy=round(pm_, 2), rr=round(rr, 2), breakeven=round(be),
                        open_pct=round(open_pct), somme=round(sm, 1), cpte=round(cpte, 1),
                        cpte_oos=round((eqo - 1) * 100, 1), e_h1=round(eh1, 2), e_h2=round(eh2, 2),
                        maxDD=round(maxdd, 1), robust=robust, jours=g.date.nunique(), dernier=g.date.max()))
    cols = ['regle', 'band', 'heure', 'liq', 'exit', 'n', 'trj', 'exp', 't', 'win',
            'gain_moy', 'perte_moy', 'rr', 'breakeven', 'open_pct',
            'somme', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'robust', 'jours', 'dernier']
    board = pd.DataFrame(out, columns=cols)
    if len(board):
        board = board.sort_values(['robust', 't'], ascending=False)
    board.to_csv(BOARD, index=False)
    return board, dates


def main(day):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    today = compute_day(day)
    if len(today):
        if os.path.exists(LOG):
            old = pd.read_parquet(LOG); old = old[old.date != day]        # idempotent : remplace le jour
            today = pd.concat([old, today], ignore_index=True)
        today.to_parquet(LOG, index=False)
        print(f"[{day}] {len(today[today.date == day])} configs ont tradé -> loggées dans daily-stats", flush=True)
    else:
        print(f"[{day}] aucune config tradée ce jour", flush=True)
        if not os.path.exists(LOG):
            return
    board, dates = rebuild_board()
    nrob = int(board.robust.sum()) if len(board) else 0
    print(f"\nBILLBOARD recomposé : {len(board)} configs (n>={sg.N_MIN} cumulé) · {nrob} robustes · "
          f"{len(dates)} jours -> {BOARD}", flush=True)
    # gagnante du jour (meilleur sum_pnl du jour, n>=3)
    dd = pd.read_parquet(LOG); dd = dd[(dd.date == day) & (dd.n >= 3)]
    if len(dd):
        w = dd.sort_values('sum_pnl', ascending=False).iloc[0]
        print(f"🏆 gagnante du {day} : {w.regle} [{w.band}] {w.exit} "
              f"(n={int(w.n)}, somme={w.sum_pnl:.1f}%, exp={w.sum_pnl/w.n:.2f}%)", flush=True)
    print("\n=== TOP 10 billboard (robustesse) ===")
    cols = ['regle', 'band', 'heure', 'liq', 'exit', 'n', 'trj', 'exp', 't', 'win', 'rr', 'breakeven',
            'open_pct', 'cpte', 'cpte_oos', 'e_h1', 'e_h2', 'maxDD', 'jours']
    pd.set_option('display.width', 240, 'display.max_columns', 40)
    print(board[board.robust].head(10)[cols].to_string(index=False)
          if (len(board) and board.robust.any()) else "(pas encore de config robuste — le board se remplit au fil des jours)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ZoneInfo('America/New_York')).date().isoformat())
    a = ap.parse_args()
    main(a.date)
