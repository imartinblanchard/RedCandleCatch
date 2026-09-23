#!/usr/bin/env python3
"""Génère le PDF de synthèse de la recherche RedCandleCatch (session 2026-09-22)."""
import os
from fpdf import FPDF

BLUE = (30, 60, 110); GREY = (90, 90, 90); LGREY = (235, 237, 240)
GREEN = (20, 120, 40); RED = (170, 30, 30)
HERE = os.path.dirname(os.path.abspath(__file__))


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('Helvetica', 'I', 8); self.set_text_color(*GREY)
        self.cell(0, 6, 'RedCandleCatch - Synthese recherche - 2026-09-22', align='L')
        self.cell(0, 6, f'p.{self.page_no()}', align='R', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def footer(self):
        self.set_y(-12); self.set_font('Helvetica', 'I', 7); self.set_text_color(*GREY)
        self.cell(0, 6, 'Genere par Claude Code - donnees Alpaca SIP (borne superieure, biais survivant)', align='C')


def h1(pdf, t):
    pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(*BLUE)
    pdf.multi_cell(0, 8, t, new_x='LMARGIN', new_y='NEXT'); pdf.ln(1)

def h2(pdf, t):
    pdf.ln(1); pdf.set_font('Helvetica', 'B', 12); pdf.set_text_color(*BLUE)
    pdf.multi_cell(0, 6.5, t, new_x='LMARGIN', new_y='NEXT'); pdf.ln(0.5)

def para(pdf, t, bold=False):
    pdf.set_font('Helvetica', 'B' if bold else '', 10); pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 5, t, new_x='LMARGIN', new_y='NEXT'); pdf.ln(0.8)

def bullet(pdf, t):
    pdf.set_font('Helvetica', '', 10); pdf.set_text_color(20, 20, 20)
    x = pdf.get_x()
    pdf.cell(5, 5, '-')
    pdf.multi_cell(0, 5, t, new_x='LMARGIN', new_y='NEXT')

def table(pdf, headers, rows, widths, aligns=None):
    aligns = aligns or ['L'] * len(headers)
    pdf.set_font('Helvetica', 'B', 9); pdf.set_fill_color(*BLUE); pdf.set_text_color(255, 255, 255)
    for hh, w, a in zip(headers, widths, aligns):
        pdf.cell(w, 6.5, hh, border=0, align=a, fill=True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 9); pdf.set_text_color(20, 20, 20)
    for i, r in enumerate(rows):
        fill = i % 2 == 1
        if fill: pdf.set_fill_color(*LGREY)
        for cell, w, a in zip(r, widths, aligns):
            col = (20, 20, 20)
            if cell.endswith('++'): col = GREEN; cell = cell[:-2]
            elif cell.endswith('--'): col = RED; cell = cell[:-2]
            pdf.set_text_color(*col)
            pdf.cell(w, 6, cell, border=0, align=a, fill=fill)
            pdf.set_text_color(20, 20, 20)
        pdf.ln()
    pdf.ln(2)


pdf = PDF(); pdf.set_auto_page_break(True, margin=15); pdf.add_page()

# --- Cover ---
pdf.ln(30)
pdf.set_font('Helvetica', 'B', 24); pdf.set_text_color(*BLUE)
pdf.multi_cell(0, 12, 'RedCandleCatch', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(20, 20, 20)
pdf.multi_cell(0, 9, 'Synthese de recherche - rebuild point-in-time', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.ln(4)
pdf.set_font('Helvetica', '', 11); pdf.set_text_color(*GREY)
pdf.multi_cell(0, 6, 'Session du 22 septembre 2026', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.ln(20)
pdf.set_draw_color(*BLUE); pdf.set_line_width(0.5)
pdf.set_font('Helvetica', 'B', 11); pdf.set_text_color(*RED)
pdf.multi_cell(0, 6, 'CONCLUSION EN UNE LIGNE', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.set_font('Helvetica', '', 11); pdf.set_text_color(20, 20, 20)
pdf.multi_cell(0, 6, "L'edge post-open affiche (+2,19%) etait un artefact de look-ahead. Le vrai edge,\n"
                     "valide hors echantillon, est ailleurs : post-open gap 5-10% (pas 10-20). Les gros\n"
                     "gaps perdent. Le dip d'entree est indispensable. Le PM a un edge mais l'execution\n"
                     "reste a prouver.", align='C', new_x='LMARGIN', new_y='NEXT')

# --- 1. Contexte ---
pdf.add_page()
h1(pdf, '1. Ce qu on cherchait, ce qu on a trouve')
para(pdf, "Point de depart : doute de Martin sur la fiabilite des backtests (biais du survivant) et "
          "constat live que la strategie post-open ne performait pas comme le backtest le promettait. "
          "On a audite la methode de recherche, trouve deux defauts majeurs, puis reconstruit un "
          "dataset propre (point-in-time) pour obtenir de vrais chiffres.")

h2(pdf, 'Les deux defauts prouves de l ancienne recherche')
para(pdf, 'Defaut 1 - LOOK-AHEAD (fatal).', bold=True)
para(pdf, "Le backtest entrait sur le 1er dip des 09:30 SANS attendre que le titre soit eligible. "
          "Pour un titre eligible seulement a 10:30, il achetait son dip de 09:35 en 'sachant' d'avance "
          "qu'il serait un gapper 10-20 a midi. Diagnostic : 40% des trades entraient AVANT l'eligibilite, "
          "avec +7,24%/tr, win 92%, pf 26, t=30 (impossible en reel). En corrigeant : -1,38%/tr (t=-6,4).")
para(pdf, 'Defaut 2 - EXCLUSION DES RUNAWAYS.', bold=True)
para(pdf, "La selection gardait un titre si son plus-haut matinal restait dans 10-20%. Tout titre qui "
          "depassait 20% avant midi etait jete - or ce sont justement les forts runners tardifs. "
          "Population amputee de ses meilleurs (et pires) coups.")

h2(pdf, 'Le rebuild propre (point-in-time)')
bullet(pdf, "Screen daily de tout l'univers (11 500 titres) : gap 5-500%, prix 0,50-50$ -> 82 473 ticker-jours candidats.")
bullet(pdf, "Fetch des bougies 1-min (165 dates, 409 Mo, dec 2025 -> aout 2026).")
bullet(pdf, "Rejeu EPISODIQUE et CAUSAL : eligibilite = 1re minute ou le plus-haut courant entre dans la bande ; "
            "entree = dip APRES l'eligibilite (jamais avant -> zero look-ahead) ; runners >20% GARDES.")
bullet(pdf, "Grille de sortie (activation x trailing) calculee en une passe ; dip / gap% / heure = simples tranches.")
para(pdf, "Validation du moteur : le baseline PM neuf (+2,06%) reproduit l'ancien candles.parquet (+2,15%). OK.")

# --- 2. Resultats principaux ---
pdf.add_page()
h1(pdf, '2. Resultats principaux (point-in-time, OOS)')

h2(pdf, 'Les 3 populations (config deployee, prix 3-20$)')
table(pdf, ['Population', 'exp/tr', 't', 'OOS test', 'Verdict'],
      [['PM (dip 5%)', '+2,06%', '+4,42', '+1,30% (t=2,1)', 'edge reel++'],
       ['post-open FRAIS (dip 1,5%)', '-0,24%', '-1,29', '-0,27%', 'pas d edge--'],
       ['post-open RE-GAP (cas DCOY)', '-0,31%', '-1,52', '+0,20% (t=0,7)', 'instable--']],
      [70, 22, 18, 34, 36])
para(pdf, "L'edge post-open 'frais' (+2,19% autrefois annonce) est confirme FANTOME : mesure honnetement "
          "il est ~nul/negatif. C'est la population que le bot live trade actuellement.")

h2(pdf, 'Quel gap% performe le mieux (LA decouverte)')
para(pdf, 'Post-open, dip 3% trail 2% :', bold=True)
table(pdf, ['Bande gap', 'n', 'exp', 't', 'Verdict'],
      [['5-10 %', '429', '+1,03%', '+2,87', 'GAGNE (OOS ok)++'],
       ['10-15 %', '295', '-0,33%', '-0,74', 'plat/perd--'],
       ['15-20 %', '226', '+0,36%', '+0,66', 'casse OOS--'],
       ['20-30 %', '357', '-0,60%', '-1,30', 'perd--'],
       ['30-50 %', '498', '-1,20%', '-2,52', 'perd net--'],
       ['50-100 %', '570', '-1,06%', '-2,38', 'perd net--'],
       ['100-500 %', '415', '+0,41%', '+0,65', 'bruit--']],
      [40, 20, 24, 22, 60])
para(pdf, "La SEULE bande post-open gagnante et robuste OOS est 5-10% - PAS la bande 10-20 deployee. "
          "Les gros gaps (30-100%) perdent nettement. On tradait la mauvaise bande.")

# --- 3. OOS validation ---
pdf.add_page()
h1(pdf, '3. Validation hors echantillon (train / test)')
h2(pdf, 'Post-open gap 5-10% - TIENT dans les deux moities')
table(pdf, ['Combo', 'TRAIN', 'TEST', 'Verdict'],
      [['dip 1,5% / trail 2%', '+0,43% (t=2,6)', '+0,68% (t=4,0)', 'TIENT++'],
       ['dip 2% / trail 2%', '+0,60% (t=2,3)', '+0,79% (t=3,0)', 'TIENT++'],
       ['dip 3% / trail 2%', '+0,81% (t=1,6)', '+1,22% (t=2,4)', 'TIENT++']],
      [46, 44, 44, 32])
para(pdf, "Les 9 combos dip x trail tiennent dans train ET test. Edge modeste (+0,4 a +1,2%/tr) mais "
          "reel et executable en seance (RTH, pas de spread pre-marche).")

h2(pdf, 'PM petits gaps 5-15% - tres fort OOS mais execution suspecte')
table(pdf, ['Combo', 'TRAIN', 'TEST', 'Verdict'],
      [['dip 1,5% / trail 2%', '+3,51% (t=10,2)', '+2,61% (t=6,3)', 'TIENT++'],
       ['dip 3% / trail 2%', '+4,51% (t=9,2)', '+3,49% (t=5,3)', 'TIENT++']],
      [46, 44, 44, 32])
para(pdf, "Statistiquement solide (donc pas du look-ahead) MAIS win ~90% = artefact de microstructure "
          "pre-marche (bougies eparses, le stop -10% ne se declenche presque jamais ; spreads/fills PM "
          "non modelises). A NE PAS croire avant d'avoir chiffre les couts d'execution PM.")

# --- 4. Autres tests ---
pdf.add_page()
h1(pdf, '4. Autres tests (dip, entree, sortie)')

h2(pdf, 'Profondeur du dip')
bullet(pdf, "Post-open : dip profond (>5%) DETRUIT l'echantillon (un petit gappeur ne fait pas de bougie -8%). "
            "L'edge vit aux dips LEGERS (1,5-2%).")
bullet(pdf, "PM : dip profond explose l'expectancy in-sample (+9 a +15%) MAIS le test tombe a 3-0 trades. "
            "Mirage invalidable. Zone fiable : dip 1,5-5%.")

h2(pdf, 'Entree immediate (sans dip) vs entree sur dip')
table(pdf, ['Entree (post-open 5-10%)', 'exp', 't', 'TEST'],
      [['IMMEDIATE (a l eligibilite)', '-0,33%', '-7,39', '-0,25% (t=-4,0)--'],
       ['DIP -1,5%', '+0,03%', '+0,16', '+0,11% (t=0,5)++']],
      [70, 24, 22, 44])
para(pdf, "Entrer sans attendre le dip PERD franchement (t=-7,4, enorme echantillon, tient OOS). "
          "Aucune sortie ne le sauve. => L'edge de la strategie EST le dip (le pullback), pas le momentum. "
          "Acheter la bougie qui pousse dans la bande = acheter la force -> ca retombe.")

h2(pdf, 'Sortie : take-profit fixe vs laisser courir')
bullet(pdf, "Les take-profit fixes (+3%, +5%) coupent les gagnants trop tot -> ils DETRUISENT l'edge.")
bullet(pdf, "Laisser courir (trailing 2% ou simple stop -10% + hold EOD) est nettement meilleur.")
bullet(pdf, "Heure d'eligibilite (runners tardifs >10:30) : n'aide PAS (tous buckets plats, non signif.).")

# --- 5. Reserves & reco ---
pdf.add_page()
h1(pdf, '5. Reserves et prochaines etapes')
h2(pdf, 'Reserves (a garder en tete)')
bullet(pdf, "Biais du survivant IRREDUCTIBLE : Alpaca ne sert aucune barre pour les titres radies "
            "(2732 inactifs testes = 0 barre). Tous les chiffres sont une BORNE SUPERIEURE.")
bullet(pdf, "Chiffres bruts, 1 action/trade (commissions non incluses).")
bullet(pdf, "Execution PM non modelisee (spreads, fills, halts) - l'edge PM est le plus optimiste.")
bullet(pdf, "L'ampleur de l'edge post-open 5-10% est sensible a la definition exacte de la poche "
            "(+0,1% a +0,7% selon 'premier dip du jour' vs 'premier dip in-band') -> a figer.")

h2(pdf, 'Pistes')
para(pdf, 'A - Piste deployable (la plus propre) :', bold=True)
bullet(pdf, "Basculer la bande post-open du bot de 10-20% vers ~5-10%, dip 1,5-2%, trail 2%. "
            "Forward-test PAPER avant tout passage live.")
para(pdf, 'B - A verifier avant d y croire :', bold=True)
bullet(pdf, "Chiffrer l'edge PM net de couts d'execution pre-marche realistes.")
bullet(pdf, "Figer une definition unique de la poche 5-10% et la re-valider OOS.")

h2(pdf, 'Fichiers')
para(pdf, "Pipeline : research/pit_gappers/{screen,fetch,replay,grid,grid_analyze,oos,entry_variants}_pit.py "
          "+ data/{candidates.json, bars/, trades_grid.parquet}.")

out = os.path.join(HERE, 'RESUME_recherche_2026-09-22.pdf')
pdf.output(out)
print('PDF ->', out)
