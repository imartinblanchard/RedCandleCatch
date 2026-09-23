#!/usr/bin/env python3
"""PDF explicatif de la stratégie Repli & Capitulation (RedCandleCatch v3)."""
import os
from fpdf import FPDF
BLUE=(28,58,102); GREY=(95,95,95); LGREY=(236,238,241); GREEN=(20,120,45); RED=(170,35,35); GOLD=(150,110,20)
HERE=os.path.dirname(os.path.abspath(__file__))

class PDF(FPDF):
    def header(self):
        if self.page_no()==1: return
        self.set_font('Helvetica','I',8); self.set_text_color(*GREY)
        self.cell(0,6,'RedCandleCatch v3 - Repli & Capitulation',align='L')
        self.cell(0,6,f'p.{self.page_no()}',align='R',new_x='LMARGIN',new_y='NEXT'); self.ln(2)
    def footer(self):
        self.set_y(-12); self.set_font('Helvetica','I',7); self.set_text_color(*GREY)
        self.cell(0,6,'Genere par Claude Code - donnees Alpaca SIP (borne superieure, biais survivant) - 2026-09-23',align='C')

def h1(p,t): p.set_font('Helvetica','B',15); p.set_text_color(*BLUE); p.multi_cell(0,8,t,new_x='LMARGIN',new_y='NEXT'); p.ln(1)
def h2(p,t): p.ln(1); p.set_font('Helvetica','B',12); p.set_text_color(*BLUE); p.multi_cell(0,6.5,t,new_x='LMARGIN',new_y='NEXT'); p.ln(0.5)
def para(p,t,b=False): p.set_font('Helvetica','B' if b else '',10); p.set_text_color(20,20,20); p.multi_cell(0,5,t,new_x='LMARGIN',new_y='NEXT'); p.ln(0.8)
def bullet(p,t):
    p.set_font('Helvetica','',10); p.set_text_color(20,20,20); p.cell(5,5,'-'); p.multi_cell(0,5,t,new_x='LMARGIN',new_y='NEXT')
def rule(p,label,val,color=(20,20,20)):
    p.set_font('Helvetica','B',10); p.set_text_color(*BLUE); p.cell(46,6,label)
    p.set_font('Helvetica','',10); p.set_text_color(*color); p.multi_cell(0,6,val,new_x='LMARGIN',new_y='NEXT')
def table(p,headers,rows,widths,aligns=None):
    aligns=aligns or ['L']*len(headers)
    p.set_font('Helvetica','B',9); p.set_fill_color(*BLUE); p.set_text_color(255,255,255)
    for hh,w,a in zip(headers,widths,aligns): p.cell(w,6.5,hh,align=a,fill=True)
    p.ln(); p.set_font('Helvetica','',9); p.set_text_color(20,20,20)
    for i,r in enumerate(rows):
        fill=i%2==1
        if fill: p.set_fill_color(*LGREY)
        for cell,w,a in zip(r,widths,aligns):
            col=(20,20,20)
            if cell.endswith('++'): col=GREEN; cell=cell[:-2]
            elif cell.endswith('--'): col=RED; cell=cell[:-2]
            p.set_text_color(*col); p.cell(w,6,cell,align=a,fill=fill); p.set_text_color(20,20,20)
        p.ln()
    p.ln(2)

pdf=PDF(); pdf.set_auto_page_break(True,margin=15); pdf.add_page()
pdf.ln(26)
pdf.set_font('Helvetica','B',12); pdf.set_text_color(*GOLD)
pdf.multi_cell(0,7,'REDCANDLECATCH v3',align='C',new_x='LMARGIN',new_y='NEXT')
pdf.set_font('Helvetica','B',26); pdf.set_text_color(*BLUE)
pdf.multi_cell(0,13,'Repli & Capitulation',align='C',new_x='LMARGIN',new_y='NEXT')
pdf.ln(3); pdf.set_font('Helvetica','',12); pdf.set_text_color(60,60,60)
pdf.multi_cell(0,6,"Acheter le repli d'un petit gappeur quand les vendeurs capitulent",align='C',new_x='LMARGIN',new_y='NEXT')
pdf.ln(16)
pdf.set_font('Helvetica','B',11); pdf.set_text_color(*RED)
pdf.multi_cell(0,6,'LA THESE EN UNE PHRASE',align='C',new_x='LMARGIN',new_y='NEXT')
pdf.set_font('Helvetica','',11); pdf.set_text_color(20,20,20)
pdf.multi_cell(0,6,"On ne trade pas le gap ni un mini-dip. On attend qu'un titre qui a gappe de 5-10%\n"
                   "fasse un sommet, RECULE d'au moins 8% depuis ce sommet, et que le volume ACCELERE\n"
                   "dans la descente (= capitulation / panique vendeuse). On achete ce creux, stop -10%,\n"
                   "et on tient jusqu'a 15:55. L'edge : le rebond apres la capitulation.",align='C',new_x='LMARGIN',new_y='NEXT')
pdf.ln(10); pdf.set_font('Helvetica','I',9); pdf.set_text_color(*GREY)
pdf.multi_cell(0,5,"Ne dun d'une observation de Martin (23/09) : les gappers reculent ~8% de leur sommet avant de rebondir.",align='C',new_x='LMARGIN',new_y='NEXT')

# 1. L'idee
pdf.add_page()
h1(pdf,'1. L idee et d ou elle vient')
para(pdf,"Le bot precedent achetait un 'dip' d'une seule bougie (-1,5%). L'audit a montre que cet edge "
         "etait un artefact (look-ahead) : mesure proprement, il est nul. En cherchant mieux, deux "
         "observations de Martin ont tout debloque :")
bullet(pdf,"Le vrai creux n'est pas le premier mini-dip : le titre RECULE ~8% depuis son sommet du jour avant de rebondir.")
bullet(pdf,"Le repli n'est pas une bougie mais un MOUVEMENT de plusieurs bougies -> ce qui compte c'est le VOLUME pendant la descente.")
para(pdf,"En testant sur 8 mois (point-in-time, sans look-ahead, valide hors-echantillon), ces deux idees "
         "donnent l'edge le plus solide de toute la recherche.")
h2(pdf,'Pourquoi ca marche (l intuition)')
bullet(pdf,"Petit gap (5-10%) = mouvement gerable, pas une parabolique. Les gros gaps (30%+) s'effondrent : PERDANTS.")
bullet(pdf,"Repli profond (8%+) = on achete la peur, pas la force. Meilleur prix, rebond plus probable.")
bullet(pdf,"Volume qui ACCELERE dans la descente = capitulation : les derniers vendeurs paniques sortent -> epuisement -> rebond violent. Un repli a volume mou = pas de capitulation -> rebond faible.")

# 2. Les regles exactes
pdf.add_page()
h1(pdf,'2. Les regles exactes')
h2(pdf,'Univers (qui on regarde)')
rule(pdf,'Gap','5 a 10% (plus-haut du jour vs cloture veille). PAS 10-20, PAS les gros gaps.')
rule(pdf,'Prix','3 a 20 $')
rule(pdf,'Seance','Regulier (post-ouverture). 1 seule position par titre et par jour.')
h2(pdf,'Entree (quand on achete)')
para(pdf,'Les 4 conditions doivent etre reunies sur une bougie 1-min cloturee :',True)
bullet(pdf,"1. REPLI : le prix est retombe d'au moins 8% sous le plus-haut du jour (HOD).")
bullet(pdf,"2. GAP OK : le gap est encore dans 5-10% a cet instant (recheck).")
bullet(pdf,"3. CAPITULATION : pendant la descente (du sommet au creux), le volume ACCELERE "
           "(volume moyen de la 2e moitie du repli > 1,3x celui de la 1re moitie ; repli d'au moins 4 bougies).")
bullet(pdf,"4. LIQUIDITE : le repli a brasse au moins 300 K$ cumules (executable).")
para(pdf,"Achat en LIMITE marketable au prix du signal (fill immediat, slippage plafonne, marche aussi hors seance).")
h2(pdf,'Sortie (quand on vend)')
bullet(pdf,"STOP fixe a -10% du prix d'entree (ordre StopLimit, executable en pre-marche).")
bullet(pdf,"Sinon : on TIENT jusqu'a 15:55, puis sortie forcee (vente limite GTC).")
bullet(pdf,"PAS de take-profit fixe, PAS de trailing : les tests montrent qu'ils COUPENT les gagnants trop tot. On laisse courir.")
h2(pdf,'Taille de position (sizing)')
para(pdf,"Base sur le risque : on risque 1% du compte par trade. Comme le stop est a -10%, la position "
         "= 1%/10% = 10% du compte. Un trade gagnant a +2R = +2% de compte ; un stop = -1% de compte.")

# 3. Les preuves
pdf.add_page()
h1(pdf,'3. Les preuves (hors-echantillon)')
para(pdf,"Train = dec-avril, Test = mai-aout (donnees jamais vues a la construction). Prix 3-20, gap 5-10.")
h2(pdf,'L entree sur repli bat le mini-dip')
table(pdf,['Entree','exp/trade (TEST)','t'],
      [['dip -1,5% (ancien)','+0,61%','+3,2'],
       ['repli 8% du HOD','+0,91%','+4,0++'],
       ['repli 12% du HOD','+1,96%','+4,0++']],
      [70,50,40])
h2(pdf,'Le filtre CAPITULATION (le coeur) tient train ET test')
table(pdf,['Volume du repli','TRAIN','TEST'],
      [['decroissant','+0,14%','+0,26%'],
       ['plat','+0,11%','+0,17%'],
       ['CROISSANT (capitulation)','+1,97% (t4,9)','+2,21% (t5,6)++']],
      [70,45,45])
para(pdf,"Le filtre TRIPLE l'edge par trade (de ~0,8% a ~2,2%) et il est SOLIDE dans les deux moities "
         "(t~5) : ce n'est pas du sur-ajustement.")
h2(pdf,'Ce qu on EVITE (teste, perdant)')
bullet(pdf,"Gros gaps 30-100% : -1 a -7%/trade (t=-9). Acheter le repli d'une parabolique = catastrophe.")
bullet(pdf,"Trailing stop et take-profit fixe : coupent les gagnants -> moins bon que tenir jusqu'a 15:55.")
bullet(pdf,"Stop -5% serre : semblait mieux en R mais SUR-AJUSTE (train +0,14% / test +1,51%) -> ecarte.")

# 4. Reserves
pdf.add_page()
h1(pdf,'4. Reserves (a lire absolument)')
para(pdf,"Les backtests sont une BORNE SUPERIEURE OPTIMISTE. NE PAS croire les rendements absolus.",True)
bullet(pdf,"Biais du survivant : Alpaca ne sert pas les titres radies -> l'echantillon ignore les pires blow-ups.")
bullet(pdf,"Slippage optimise (~0,3%) et fills parfaits supposes : sur des microcaps le reel est pire.")
bullet(pdf,"Les rendements portefeuille (+500%/8 mois) sont IRREALISTES (compounding de microcaps avec fills "
           "parfaits). Ce qui est reel = l'EDGE valide et le FILTRE, pas le chiffre en dollars.")
bullet(pdf,"P&L en % brut, 1 action au demarrage : les commissions rendent le mode 1-action perdant en $ "
           "(sert a debusquer les bugs). Le vrai test = le %.")
h2(pdf,'Le plan')
bullet(pdf,"On deploie en LIVE 1-action a partir de demain matin (forward-test reel).")
bullet(pdf,"On surveille : les entrees (repli + capitulation se declenchent-elles ?), les fills, le P&L reel vs attendu.")
bullet(pdf,"Si le forward-test confirme l'edge, on augmente la taille progressivement.")
h2(pdf,'Resume en une ligne')
pdf.set_font('Helvetica','B',11); pdf.set_text_color(*GREEN)
pdf.multi_cell(0,6,"Gap 5-10% -> repli >=8% du sommet -> volume qui accelere (capitulation) -> achat, "
                   "stop -10%, tenir jusqu'a 15:55.",new_x='LMARGIN',new_y='NEXT')

out=os.path.join(HERE,'STRATEGIE_repli_capitulation.pdf'); pdf.output(out); print('PDF ->',out)
