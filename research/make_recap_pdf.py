#!/usr/bin/env python3
"""Génère un PDF récap de la stratégie RedCandleCatch + conclusions de recherche. Sortie :
research/recap_strategie.pdf. Utilise fpdf (comme make_top10_pdf). Texte latin-1 safe."""
import os, datetime
from fpdf import FPDF

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recap_strategie.pdf')
NAVY, GREY, RED, BLUE = (23, 42, 77), (110, 110, 110), (150, 40, 40), (30, 60, 120)


def S(t):
    for a, b in [('—', '-'), ('–', '-'), ('≥', '>='), ('≤', '<='), ('→', '->'), ('×', 'x'),
                 ('’', "'"), ('…', '...'), ('•', '-'), ('«', '"'), ('»', '"'), ('⭐', '*'),
                 ('≈', '~'), ('🟥', ''), ('🟦', ''), ('🎯', ''), ('⚠️', '[!]'), ('✅', '[ok]')]:
        t = t.replace(a, b)
    return t.encode('latin-1', 'replace').decode('latin-1')


class PDF(FPDF):
    def footer(self):
        self.set_y(-12); self.set_font('Helvetica', 'I', 8); self.set_text_color(*GREY)
        self.cell(0, 6, S("RedCandleCatch - recap strategie - page %d - P&L brut, 1 action, forward-test" % self.page_no()), 0, 0, 'C')
        self.set_text_color(0)


def H1(p, t):
    p.ln(2); p.set_font('Helvetica', 'B', 13); p.set_fill_color(*NAVY); p.set_text_color(255)
    p.cell(0, 8, S('  ' + t), 0, 1, 'L', fill=True); p.set_text_color(0); p.ln(1)


def H2(p, t, color=BLUE):
    p.ln(1); p.set_font('Helvetica', 'B', 11); p.set_text_color(*color)
    p.cell(0, 6, S(t), 0, 1); p.set_text_color(0)


def body(p, t, size=10, style=''):
    p.set_font('Helvetica', style, size); p.multi_cell(0, 5, S(t));


def bullet(p, t, indent=4):
    p.set_font('Helvetica', '', 10); p.set_x(p.l_margin + indent)
    p.multi_cell(0, 5, S('- ' + t))


def note(p, t):
    p.ln(1); p.set_font('Helvetica', 'I', 9); p.set_text_color(*GREY)
    p.multi_cell(0, 4.5, S(t)); p.set_text_color(0)


def main():
    p = PDF(); p.set_auto_page_break(True, 15); p.add_page(); p.set_left_margin(14); p.set_right_margin(14)
    p.set_font('Helvetica', 'B', 18); p.cell(0, 10, S('RedCandleCatch - Strategie & Recherche'), 0, 1)
    p.set_font('Helvetica', 'I', 10); p.set_text_color(*GREY)
    p.cell(0, 6, S('Recap du %s - bot de trading intraday, gappers small-cap' % datetime.date.today().strftime('%d/%m/%Y')), 0, 1)
    p.set_text_color(0)

    H1(p, '1. LA STRATEGIE LIVE (le bot)')
    body(p, "Deux facons d'entrer sur des gappers small-cap LIQUIDES, en parallele, stop -10%, "
             "sortie forcee 15:55, 1 action/trade, 1 position/ticker/jour.")
    H2(p, 'Univers & filtres (communs aux 2 tracks)')
    bullet(p, "Scanner : small-caps qui gappent, gap 3-50%, prix 3-20$ (large, pour la collecte de donnees).")
    bullet(p, "FILTRE QUALITE / frequence (la cle) : PM-liquidite >= 20% -> le titre doit avoir trade "
               "au moins 20% des minutes 8:00-9:30 (~18/90). Causal, connu avant l'ouverture.")
    bullet(p, "Liquidite d'entree : dollar-volume du repli >= 300 K$ (garde-fou ; redondant une fois la PM-liq active).")
    bullet(p, "Prix 3-20$. 1 action/trade, 1 position/ticker/jour (forward-test).")

    H2(p, 'Track 1 - liq-eod (repli / achat du dip)', RED)
    bullet(p, "Gap 5-50% (plus-haut du jour vs cloture veille).")
    bullet(p, "Entree des 10:00, sur un repli de 12% depuis le plus-haut du jour.")
    bullet(p, "Le plus-haut doit etre fait EN SEANCE (pas en pre-marche).")
    bullet(p, "Anti-couteau : montee RTH >= 2% + gap franc a l'open >= 1% (evite les titres qui saignent).")
    bullet(p, "Sortie : STOP -10% -> sinon HOLD jusqu'a la cloture (jamais de trailing), forcee 15:55.")

    H2(p, 'Track 2 - vwap_reclaim rvol>=60 (la strategie trouvee en recherche)', BLUE)
    bullet(p, "1re heure (9:30-10:30).")
    bullet(p, "Signal : la cloture repasse AU-DESSUS du VWAP (reprise) + rvol >= 60 (volume de la minute "
               "= 60x la moyenne depuis l'ouverture) + bougie verte.")
    bullet(p, "Meme filtre PM-liquidite, prix 3-20$.")
    bullet(p, "Sortie : STOP -10% -> a +10% bascule en TRAIL 2%, forcee 15:55.")
    note(p, "Overlap ~1% avec liq-eod -> vraie 2e strategie complementaire. Detecteur prouve identique "
            "au backtest (101/101). In-sample (seuil rvol choisi sur les donnees) -> le run 1-action = son forward-test.")

    H1(p, '2. CE QUE LA RECHERCHE A CONCLU (01/11/2026)')
    H2(p, 'Swing trading (explore en profondeur, puis ECARTE)')
    bullet(p, "Teste : indicateurs sur ETF, momentum rotation, saisonnalite, univers volatils, multi-actifs, "
               "RSI(2) mean-reversion - sur donnees non-biaisees et jusqu'a 77 ans d'historique.")
    bullet(p, "Conclusion : le timing REDUIT le risque (drawdown) mais ne BAT PAS le buy & hold en rendement "
               "sur instruments liquides. Le seul 'gagnant' en rendement (momentum) etait gonfle par le biais du survivant.")
    bullet(p, "Simulation realiste 10 000$ (RSI2 sur ETF volatils, avec frais) : 15 000$ vs 28 300$ en buy & hold. "
               "Gagne seulement sur le drawdown (-15% vs -52%).")
    H2(p, 'Value / Buffett (screen fait)')
    bullet(p, "Screen fondamental qualite+valeur (yfinance) = bon outil de WATCHLIST, pas backtestable proprement "
               "(fondamentaux point-in-time + faillis = donnees payantes qu'on n'a pas).")
    H2(p, "Le vrai edge actif = le bot gappers")
    bullet(p, "L'edge de rendement vit dans les niches volatiles court-terme (gappers), PAS dans le swing sur indices. "
               "C'est pour ca qu'on se concentre sur le bot.")

    H1(p, '3. REGLAGES VERIFIES (sweep 01/11)')
    H2(p, 'Effet des deux filtres de liquidite sur liq-eod')
    p.set_font('Helvetica', 'B', 9); p.set_fill_color(*NAVY); p.set_text_color(255)
    for w, h in [(40, 'Seuil PM-liq'), (30, 'exp/tr'), (25, 'win%'), (30, 'nb trades')]:
        p.cell(w, 6, S(h), 1, 0, 'C', fill=True)
    p.ln(); p.set_text_color(0); p.set_font('Helvetica', '', 9)
    for pm, e, w_, n, cur in [('OFF (0)', '+2,18%', '48%', '144', False), ('0,10', '+3,29%', '62%', '32', False),
                              ('0,20 (ACTUEL)', '+5,24%', '72%', '25', True), ('0,30', '+6,43%', '72%', '18', False),
                              ('0,40', '+5,37%', '71%', '14', False), ('0,50', '+5,82%', '77%', '13', False)]:
        p.set_fill_color(225, 235, 250) if cur else p.set_fill_color(255, 255, 255)
        for w, v in [(40, pm), (30, e), (25, w_), (30, n)]:
            p.cell(w, 5.5, S(v), 1, 0, 'C', fill=cur)
        p.ln()
    note(p, "Durcir la PM-liquidite ameliore la qualite (exp/tr et win%) mais reduit le nb de trades. "
            "Le dollar-volume du repli (300K) est INOPERANT une fois la PM-liq active (meme resultat de 0 a 1M). "
            "Decision : garder PM-liq 0,20 / dvol 300K (bon compromis ; ecart 0,2 vs 0,3 dans le bruit, petit n).")

    H1(p, '4. ETAT DU SYSTEME')
    bullet(p, "Code pret : les 2 tracks + le filtre qualite sont en place et compilent.")
    bullet(p, "IB Gateway OK (port 4001). A relancer le terminator chaque jour de bourse a plat.")
    bullet(p, "Journal tague par strategie (colonne 'strat') ; leaderboard unifie auto chaque soir (18:20).")
    note(p, "[!] Backtest = borne SUPERIEURE ; le live (1 action) est le vrai juge. Le filtre PM-liquidite "
            "est l'amelioration censee reduire l'ecart backtest/live (prendre des titres liquides). "
            "Tout chiffre de recherche = hypothese sur petit echantillon, a confirmer en live.")

    p.output(OUT)
    print(f"PDF genere : {OUT}")


if __name__ == '__main__':
    main()
