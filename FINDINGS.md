# FINDINGS.md — Journal des découvertes (recherche & décisions)

Historique daté de ce qu'on a **appris et validé**, avec les preuves chiffrées et le
script qui les reproduit. But : qu'un repreneur comprenne **pourquoi** le bot est
construit ainsi, sans relire tout le code ni deviner. Ordre : le plus récent en haut.

Docs liées : **[STRATEGY.md](STRATEGY.md)** (la stratégie live), **[CLAUDE.md](CLAUDE.md)**
(architecture), **[research/README.md](research/README.md)** (données & scripts).

> ⚠️ **Tous les chiffres de backtest sont une borne SUPÉRIEURE optimiste.** Trois biais
> se cumulent (voir §Biais) : survivant + fills parfaits supposés + P&L brut hors
> commissions. Le classement des variantes est fiable ; les niveaux absolus non. Le
> seul juge non biaisé est le **forward-test paper** en cours.

---

## 2026-09-15 — 🐛 Bug du `peak` : la bougie d'entrée fausse MFE + activation (CORRIGÉ)
**Découvert en analysant le trade live CSAI (15/09) : sortie TRAIL −3,51% avec un MFE
journalisé de +7,22% — incohérent.**

Cause : dans `_manage`, `pos['peak'] = max(peak, cb['h'])` avec `cb = bars[-2]`. Sur le
cycle suivant l'entrée, `cb` est **encore la bougie d'entrée (dip)**, dont le HIGH est le
spike d'AVANT le dip (CSAI 09:30 : high 4,00 puis close 3,73 = l'entrée). Le peak captait
donc 4,00 → deux effets :
1. **MFE faussé** : +7,22% affiché alors que le vrai max APRÈS l'entrée était +0,5% (high 3,75).
2. **Activation prématurée** : `peak(4,00) ≥ entry×1,05 (3,917)` → bascule phase 2 (TRAIL 2%)
   immédiate sur un FAUX +5%, au lieu de garder le stop fixe −10%. CSAI s'est fait sortir
   serré à −3,51% sur ce faux signal.

**Conséquence majeure : le live ≠ le backtest.** L'`engine.py` ne prend le peak qu'à partir
de `i+1` (bougies après l'entrée) ; le live incluait la bougie d'entrée → activations
prématurées → **le live était handicapé vs les chiffres backtest.**

**Fix (15/09)** : ne mettre à jour `peak` que si `cb['t'] > entry_time` (bougies strictement
après l'entrée). Aligne le live sur le backtest. ✅ Ce trade a aussi confirmé que le fix
trailing du 14/09 fonctionne en réel (sortie propre, pas de position à nu).

## 2026-09-15 — Grille dip×trail par tranche de gap
**But : trouver la meilleure entrée/sortie (dip, trail) à chaque niveau de gap, tout le
reste fixe (stop 10, act 5, prix 3-20, PM-high).** Script : `research/test_gap_buckets_sweep.py`.

Constats robustes :
1. **Trail 2% domine partout** (tighter = mieux, confirme le paramètre dominant).
2. **Gaps bas (10-30%) : un dip plus profond (6-8%) bat le dip 5%.** Meilleur candidat
   dans la tranche live 10-20 : **dip 6% / trail 2% → +2,15%/tr, pf 2,0, t=6,4, n=445**
   (vs live 5%/2% : +1,72%, t=6,4). Amélioration sérieuse.
3. **Étendre aux gros gaps ne donne PAS de nouvel edge robuste** : 30-40/40-50/70-100/
   100-300 = échantillons fins, t<2 ; **50-60 est NÉGATIF** avec la config live (−0,78%,
   pf 0,82). Seule poche : 60-70% (dip 5%/trail 2-4%, +1,8 à +2,1%, t≈2). L'edge reste
   **concentré dans les gaps bas**, cohérent avec [config gap 10-20 ≫ ≥50].

⚠️ Optimisation in-sample (max par tranche sur 36 combos) → sur-ajustement possible malgré
le filtre robuste (t≥2, n≥30).

**➡️ DÉPLOYÉ le 15/09** : `DIP` passé de 0.05 à **0.06** dans `redcandlecatch_terminator.py`
(décision de Martin). ⚠️ **OOS (train/test) toujours À FAIRE** pour confirmer que ce
n'est pas du sur-ajustement — prochaine étape recommandée avant d'y ajouter foi.

## 2026-09-14 — PM-high ≫ open-gap pour la sélection (question TRANCHÉE)
**Décision : mesurer le gap sur le plus-haut du pré-marché est décisivement meilleur
que le mesurer à l'open 9:30. Le bot live a raison.**

Script : `research/test_gap_def.py` (calcule les deux définitions par ticker-jour et
rejoue la stratégie live).

Tranche 10-20% (celle du bot) :
| Sélection | n | exp/tr | pf | t-stat |
|-----------|---|--------|-----|--------|
| OPEN-gap 10-20 | 318 | +0,53% | 1,17 | 1,2 (non significatif) |
| **PM-high 10-20 (LIVE)** | 645 | **+1,66%** | **1,76** | **6,1** |

Vrai sur toutes les tranches (tout 10-300 : open +0,32%/pf1,10 vs PM +1,05%/pf1,39/t5,9).
**Preuve de la thèse** — les « runners fadés » (PM 10-20 mais open < 5%, i.e. montés en
PM puis déjà retombés à l'open) : n=387, exp **+1,84%**, pf **1,90**, t=5,4. C'est le
cœur de l'edge, et l'open-gap les rate entièrement.
Réserve : univers parquet déjà pré-screené → niveaux absolus à relativiser, mais le
CLASSEMENT et la concentration sur les runners fadés sont robustes.

## 2026-09-14 — Autoriser une 2e entrée/ticker/jour (mesuré, PAS encore déployé)
**Constat : la 1re ré-entrée est aussi bonne que la première ; au-delà ça dilue.**

Script : `research/test_multi_entry.py` (config live, ré-entrées après chaque sortie).
| Rang d'entrée | n | exp/tr | pf | t-stat |
|---------------|---|--------|-----|--------|
| 1re | 700 | +1,64% | 1,74 | 6,2 |
| **2e** | 176 | **+1,63%** | 1,71 | **3,1** |
| 3e | 84 | +0,66% | 1,23 | 0,8 (non significatif) |
| 6e | 22 | +5,53% (win 100%) | 1e11 | — (**artefact**, à ignorer) |

Une 2e entrée arrive 1 jour sur 4 (176/700), ajoute +287% cumulé (+25%). La 3e+ est
**perdante nette** après commissions (~2% A/R sur micro-ordres > +0,66% brut).
**Reco : passer `self.done` (1/jour) à un compteur ≤ 2/jour.** Pas implémenté (en attente).

## 2026-09-14 — 🐛 Bug trailing stop « Invalid Price » → position à nu (CORRIGÉ)
**Cause (confirmée par test réel) : passer `trailStopPrice` ET `trailingPercent`
ensemble à un ordre TRAIL IBKR → rejet err 201 « Invalid Price ». L'ordre meurt, la
réconciliation reboucle, la position reste SANS protection.**

Preuve : `research/test_trail_order.py` (A = les deux champs → rejeté ; C = percent seul
→ passe la validation prix) puis `research/test_trail_covered.py` (achat 1 action → TRAIL
percent-seul → **PreSubmitted = accepté**). Hypothèse initiale « sous-penny » FAUSSE
(FTFT est SmallCap, minTick 0.0001).
**Fix appliqué dans `_trailing_stop`** : ne fournir que `trailingPercent`, IBKR calcule
le stop initial depuis le marché. ⚠️ N'agit qu'au **redémarrage** du bot. Détails :
mémoire `reconciliation-protections`.

## 2026-09-14 — Filtres de tradabilité (volume PM / minutes actives) : DÉSACTIVÉS
Testé : un filtre « volume PM ≥ 100k » fait TOMBER l'edge (n=157, +0,66%/tr, t=1,10, non
significatif) vs sans filtre (n=701, +1,89%/tr, t=7,15). Les titres à faible volume PM
sont en fait **meilleurs**. Le nb de minutes actives seul était mieux (minutes≥60 :
+1,26%, t=2,94) mais reste inférieur à « aucun filtre ». Conclusion : **le live
n'applique aucun filtre secondaire**, exactement comme le backtest. Voir les commentaires
de `bot/redcandlecatch_scan.py` (constantes `ENABLE_*` toutes à False).

## 2026-09-11 — Fenêtre de mesure PM 08:59 vs 09:29 : non-problème
Étendre la mesure du gap jusqu'à 09:29 (comme le live) vs 08:59 (screener) ne change le
gap que dans 7,3% des cas (le pic PM est en général avant 9h) ; 1,2% des ticker-jours
changent de tranche. La stratégie fait même un poil mieux avec la fenêtre live (+1,97%
vs +1,89%). Script : `research/test_pm_window.py`. Aucun alignement nécessaire.

## 2026-09-11 — Config validée : gap 10-20% ≫ gap ≥50%
La tranche 10-20% bat nettement le ≥50% : **9/9 mois gagnants, t-stat 4,01 vs 2,03**. Le
≥50% concentrait 92% de son profit sur mai-juin (fragile). D'où la config live gap 10-20.
Voir mémoire `config-candidate-gap1020`. Config two-phase associée : dip −5%, stop −10%,
activation +5%, trail 2%.

## 2026-09-11 — 🛡️ Réconciliation des protections (bug critique corrigé)
Les 3 premiers vrais fills (TNON +21%, DBGI −9%, AENT −2%) étaient **SANS aucune
protection** : le stop n'était posé qu'à l'ouverture, jamais reposé après un
redémarrage. Correctif (modèle « broker = source de vérité ») : `protected_symbols()`
+ bloc de réconciliation à chaque cycle. + le journal enregistre le vrai prix de fill,
pas le prix du signal. Voir mémoire `reconciliation-protections`.

## 2026-09-09 — Anti-pump (rel-vol) : DÉSACTIVÉ
Les titres « pumpés » (rvol 50+) sont GAGNANTS en long (+0,54%/tr, 62% des trades). Le
filtre anti-pump venait du projet short et **nuisait** au long. Désactivé.

---

## Biais connus des données de backtest (à garder en tête sur TOUT chiffre)
1. **Biais du survivant** (RÉEL, non mesurable) : l'univers vient des titres actifs
   aujourd'hui ; les radiés/faillis sont absents (Alpaca ne sert pas leur historique).
   ~18% de l'univers manque. Frappe précisément la stratégie (un titre en route vers la
   radiation enchaîne les stops). **Gonfle toujours les résultats.**
2. **Fills parfaits supposés** : les stops sortent tous pile au niveau ; le réel sera pire.
3. **P&L BRUT hors commissions** : IBKR ~1%/côté sur micro-ordres. À 1 action le mode est
   volontairement perdant (sert à trouver les bugs). Voir mémoire `commissions-tuent-1-action`.
4. **Univers pré-screené** : les niveaux absolus portent la sélection de `gappers.json`.
5. **Granularité** : le screener PM utilise des bougies 1H (le live du 1-min).

**Conséquence : les backtests sont une borne supérieure, pas une prévision. Le
forward-test paper est le seul juge non biaisé.** Détails : mémoire `biais-donnees-backtest`.
