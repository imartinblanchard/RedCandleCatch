#!/usr/bin/env python3
"""Génère un PDF détaillé des Top 10 stratégies candidates (recherche live).

Source : results/strategy_search_indic_results.csv. Classe par P&L COMPTE parmi les
candidates ÉQUILIBRÉES, dédup. Re-simule chaque config pour lister les TICKERS tradés
(format TradingView). Ajoute la stratégie « qualité » S1. Sortie : results/top10_strategies.pdf.
"""
import os, sys, datetime
import pandas as pd
from fpdf import FPDF

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
from research.live_lab import backtest as bt

RES = os.path.join(HERE, '..', 'results')
CSV = os.path.join(RES, 'strategy_search_indic_results.csv')
OUT = os.path.join(RES, 'top10_strategies.pdf')

START = {'9:30': 570, '10:00': 600, '10:30': 630}
END = {'15:55': 955, 'midi': 720}


def S(t):
    for a, b in [('—', '-'), ('–', '-'), ('≥', '>='), ('≤', '<='), ('→', '->'), ('×', 'x'),
                 ('’', "'"), ('…', '...'), ('•', '-'), ('»', '"'), ('«', '"'), ('€', 'EUR'),
                 ('⭐', '*'), ('✅', '[ok]'), ('≈', '~')]:
        t = t.replace(a, b)
    return t.encode('latin-1', 'replace').decode('latin-1')


def build_P(row):
    """Reconstruit le dict de params du moteur depuis une ligne de résultat."""
    P = dict(bt.LIVE)
    gmin, gmax = row['gap'].split('-')
    es, ee = row['heures'].split('>')
    P.update(gap_min=float(gmin), gap_max=float(gmax),
             entry_start=START[es], entry_end=END[ee],
             retrace_pct=float(row['repli']), capit_ratio=float(row['capit']))
    ex = row['sortie']
    if ex == 'trail10/2':
        P.update(exit_mode='trail', activate_pct=0.10, trail_pct=0.02)
    elif ex == 'tp20':
        P.update(exit_mode='tp', tp_pct=0.20)
    else:
        P.update(exit_mode='eod')
    ind = row['indic']
    P.update(hod_in_rth=('hodRTH' in ind), require_green=('green' in ind),
             vwap_side='below' if 'vw<' in ind else None)
    return P


def describe(row):
    gmin, gmax = row['gap'].split('-')
    es, ee = row['heures'].split('>')
    ee = '15:55' if ee == '15:55' else 'midi (12:00)'
    capit = 'AUCUN (desactive)' if row['capit'] == -1 else \
        f"volume moyen 2e moitie / 1re moitie du repli > {row['capit']}"
    indmap = {'hodRTH': 'le plus-haut du jour (origine du repli) doit etre fait EN SEANCE (pas en pre-marche)',
              'green': "la bougie d'entree doit etre VERTE (rebond confirme)",
              'vw<': "prix sous le VWAP a l'entree"}
    inds = [indmap.get(x, x) for x in row['indic'].split('+')] if row['indic'] != '—' else ['aucun']
    exitmap = {'trail10/2': "TRAIL 2% (s'active a +10% de gain), stop fixe -10%",
               'eod': "tenu jusqu'a la cloture (hold-to-EOD), stop fixe -10%",
               'tp20': "take-profit a +20% sinon cloture, stop fixe -10%"}
    rules = [
        f"Gap du jour {gmin}% a {gmax}% (plus-haut 04:00->midi vs cloture veille), prix 3-20$",
        f"Fenetre d'entree : {es} -> {ee}",
        f"Entree : 1er repli de {int(round(row['repli']*100))}% depuis le plus-haut du jour",
        f"Capitulation : {capit}",
        "Liquidite : volume cumule du repli >= 300 K$ (filtre ACTIF)",
        "Frequence : 1 entree par ticker et par jour (one-shot)",
    ] + [f"Indicateur : {i}" for i in inds]
    return rules, exitmap.get(row['sortie'], row['sortie'])


class PDF(FPDF):
    def footer(self):
        self.set_y(-12); self.set_font('Helvetica', 'I', 8); self.set_text_color(130)
        self.set_x(self.l_margin)
        self.cell(0, 6, S('hypotheses (19 seances live), non prouvees - page %d' % self.page_no()), 0, 0, 'C')
        self.set_text_color(0)


def MC(pdf, h, txt, indent=0, size=10, style='', fill=False):
    pdf.set_font('Helvetica', style, size)
    pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(0, h, S(txt), fill=bool(fill))


def stat_block(pdf, row):
    pairs = [('Trades / jour', f"{row['trj']}"), ('Nb trades (n)', f"{int(row['n'])}"),
             ('Gain / trade', f"{row['exp']:+.2f}%"), ('t-stat', f"{row['t']:+.2f}"),
             ('Profit factor', f"{row['pf']:.2f}"),
             ('1re moitie / 2e moitie', f"{row['e_h1']:+.2f}% / {row['e_h2']:+.2f}%"),
             ('OOS (jours de test)', f"{row['e_te']:+.2f}%"),
             ('P&L COMPTE 2% (periode complete)', f"{row['cpte']:+.1f}%"),
             ('P&L COMPTE 2% (OOS)', f"{row['cpte_oos']:+.1f}%")]
    for k, v in pairs:
        pdf.set_x(pdf.l_margin + 5)
        pdf.set_font('Helvetica', '', 9); pdf.set_text_color(90); pdf.cell(72, 5.6, S(k), 0, 0)
        pdf.set_font('Helvetica', 'B', 9); pdf.set_text_color(0); pdf.cell(35, 5.6, S(v), 0, 1)
    pdf.set_text_color(0)


def card(pdf, rank, row, title, tickers):
    if pdf.get_y() > 190:
        pdf.add_page()
    pdf.set_fill_color(238, 243, 250)
    pdf.set_font('Helvetica', 'B', 13); pdf.set_x(pdf.l_margin)
    pdf.cell(0, 9, S(f"#{rank}   {title}"), 0, 1, 'L', True)
    pdf.ln(2)
    rules, exit_desc = describe(row)
    MC(pdf, 6, "Regles d'entree :", style='B', size=10)
    for r in rules:
        MC(pdf, 5.5, '- ' + r, indent=5, size=10)
    MC(pdf, 6, "Sortie :", style='B', size=10)
    MC(pdf, 5.5, '- ' + exit_desc, indent=5, size=10)
    pdf.ln(1)
    MC(pdf, 6, "Performance (donnees live, slippage inclus) :", style='B', size=10)
    stat_block(pdf, row)
    pdf.ln(1)
    MC(pdf, 6, f"Tickers trades ({len(tickers)}) - a coller dans TradingView :", style='B', size=10)
    pdf.set_fill_color(245, 245, 240)
    pdf.set_font('Courier', '', 8.5); pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4.6, S(', '.join(tickers)), border=1, fill=True)
    pdf.ln(5)


def main():
    r = pd.read_csv(CSV)
    bal = r[(r.robust) & (r.e_h1 >= 0.8) & (r.e_h2 >= 0.8) & (r.e_te >= 0.8) & (r.t >= 2.3)].copy()
    bal = bal.sort_values('cpte', ascending=False).drop_duplicates(
        subset=['n', 'exp', 'pf', 'cpte', 'cpte_oos'], keep='first')
    top = bal.head(10).reset_index(drop=True)
    s1 = r[(r.gap == '5-10') & (r.repli == 0.08) & (r.capit == 2.0) &
           (r.sortie == 'trail10/2') & (r.indic == 'hodRTH')]
    s1 = s1.iloc[0] if len(s1) else None

    print("chargement des bars + simulation des configs pour lister les tickers...")
    groups, _ = bt.load_groups()

    def tickers_of(row):
        t = bt.simulate(groups, build_P(row), slip=True)
        return sorted(t.ticker.unique().tolist()) if len(t) else []

    top_tk = [tickers_of(row) for _, row in top.iterrows()]
    s1_tk = tickers_of(s1) if s1 is not None else []

    pdf = PDF('P', 'mm', 'A4'); pdf.set_auto_page_break(True, 15); pdf.add_page()
    pdf.ln(4)
    MC(pdf, 10, "Top 10 strategies candidates", style='B', size=20)
    pdf.set_text_color(90); MC(pdf, 7, "RedCandleCatch - recherche sur donnees LIVE", size=12)
    MC(pdf, 6, f"Genere le {datetime.date.today().isoformat()} - ~19 seances live (collected_live)", size=9)
    pdf.set_text_color(0); pdf.ln(3)

    pdf.set_fill_color(255, 243, 205)
    MC(pdf, 6, "AVERTISSEMENT - a lire en premier", style='B', size=10, fill=True)
    MC(pdf, 5.3,
       "Ce document liste des HYPOTHESES, PAS des strategies prouvees rentables. Elles viennent d'une "
       "recherche large (11 520 combinaisons) sur seulement ~19 seances de donnees live. Sur si peu de "
       "jours, tester des milliers de combos produit forcement des faux positifs. Garde-fous appliques "
       "(positif sur les 2 moities + jours de test hors-echantillon + non-fragile), mais le seul vrai "
       "juge reste le forward. Mode actuel : 1 action/trade (validation d'execution), volontairement "
       "perdant apres commissions. NE RIEN DEPLOYER sur la base de ce PDF seul.", size=9.5)
    pdf.ln(3)
    MC(pdf, 6, "ADN commun des candidates", style='B', size=11)
    for b in ["Sortie TRAIL 2% (active a +10%) : bat le hold-to-EOD sur le live (151 des 213 candidates equilibrees).",
              "HOD en seance : le plus-haut d'origine du repli doit etre fait en seance, pas en pre-marche.",
              "Repli de 8 a 12% depuis le plus-haut du jour, sur small-caps ayant gappe a la hausse.",
              "Liquidite (repli >= 300 K$) et 1 entree/ticker/jour : communs a toutes. La capitulation varie.",
              "Deux familles : gaps SERRES (5-10%, selectif ~2 trades/j) et gaps LARGES (5-50%, ~4-6 trades/j)."]:
        MC(pdf, 5.5, '- ' + b, indent=5, size=10)
    pdf.ln(2); pdf.set_text_color(90)
    MC(pdf, 5, "Lecture : Gain/trade = esperance par trade (slippage inclus). t-stat>2 = significatif in-sample. "
               "P&L COMPTE = rendement compose sous sizing contraint capital (depend du nb de trades/jour ET du "
               "risque 2%), periode complete et jours de test (OOS). Les tickers listes par strategie = ceux "
               "reellement tradees dans le backtest, pour verification sur TradingView.", size=9)
    pdf.set_text_color(0)

    # tableau recap
    pdf.add_page()
    MC(pdf, 9, "Tableau recapitulatif (classe par P&L compte)", style='B', size=13); pdf.ln(1)
    heads = ['#', 'Gap', 'Fenetre', 'Repli', 'Capit', 'Indicateur', 'Sortie', 'tr/j', 'g/tr', 't', 'CPTE', 'OOS']
    w = [6, 13, 23, 11, 10, 27, 17, 10, 13, 9, 14, 13]
    pdf.set_font('Helvetica', 'B', 7.5); pdf.set_fill_color(230); pdf.set_x(pdf.l_margin)
    for h, wi in zip(heads, w):
        pdf.cell(wi, 7, S(h), 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 7.5)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        capl = 'off' if row['capit'] == -1 else str(row['capit'])
        vals = [str(i), row['gap'], row['heures'], f"{int(round(row['repli']*100))}%", capl, row['indic'],
                row['sortie'], str(row['trj']), f"{row['exp']:+.2f}", f"{row['t']:.1f}",
                f"{row['cpte']:+.0f}%", f"{row['cpte_oos']:+.0f}%"]
        pdf.set_x(pdf.l_margin)
        for v, wi in zip(vals, w):
            pdf.cell(wi, 6, S(str(v)), 1, 0, 'C')
        pdf.ln()

    # fiches
    pdf.add_page(); MC(pdf, 10, "Fiches detaillees", style='B', size=15); pdf.ln(2)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        fam = 'gaps larges / frequence' if row['gap'] == '5-50' else \
              ('gaps serres / qualite' if row['gap'] in ('5-10', '3-10') else 'intermediaire')
        card(pdf, i, row, f"{row['gap']}  -  {fam}", top_tk[i - 1])

    if s1 is not None:
        pdf.add_page(); MC(pdf, 10, "Alternative : strategie 'qualite' S1", style='B', size=15)
        pdf.set_text_color(90)
        MC(pdf, 5.3, "Peu de trades (~2/j) mais la plus solide statistiquement (t=4.7, profit factor ~33, "
                     "esperance ~+5.6%/trade, tres stable). Rendement compte plus bas que les 'gaps larges' "
                     "car moins de trades a composer. La candidate la plus 'propre'.", size=9.5)
        pdf.set_text_color(0); pdf.ln(2)
        card(pdf, 'S1', s1, "Qualite - gap 5-10 / capitulation 2.0 / HOD en seance", s1_tk)

    pdf.output(OUT)
    print("PDF ecrit ->", OUT)


if __name__ == '__main__':
    main()
