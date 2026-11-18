# PIPELINE DE RECHERCHE POINT-IN-TIME (valable en live)

> But : tester les stratégies **comme le bot pouvait réellement les trader**, pour éliminer
> le biais de sélection de l'univers qui gonfle les edges en backtest.
> Autorité : décidé avec Martin le 18/11/2026. Voir aussi la mémoire `pipeline-point-in-time-added`.

## Le problème qu'on corrige

La recherche actuelle (`strategy_gen` sur `bars-*.parquet` complet) lit les bougies **depuis
l'open**, sans tenir compte de l'heure où le titre a vraiment été détecté. Résultat : on « achète
le gagnant d'avance ». Preuve mesurée le 18/11 : la population des titres qui touchent **gap 3-5 %**
fait déjà **+5,6 %/jour (open→close) avec seulement 11 % de faders** — sans aucune stratégie.
L'edge est dans la **population collectée**, pas dans le signal. Indicateurs et logique de sortie
sont causaux (vérifié) ; le gonflement vient du **biais de sélection de l'univers**, présent
in-sample ET OOS → aucun filtre statistique (congruence, no-open, fréquence) ne l'attrape.

**Seul remède : l'univers point-in-time** décrit ci-dessous.

## Règle d'or

> **On ne trade un titre qu'à partir du moment où on l'a réellement vu.**
> - Ancre globale : `added` (`HH:MM`, dans `tradable-DATE.json`) = quand le dashboard l'a vu
>   passer les filtres de base.
> - Ancre **par bande** (pour les tests de l'étape 6) : l'heure où son gap a franchi le seuil de
>   cette bande (`band_arrival_time`, toujours ≥ `added`).
>
> Le dashboard scanne toutes les **60 s** → ces heures sont précises à ~1 min, alignées sur les bougies.

## Le pipeline

### 1. Collecte — tous les gappers
`data/collected_live/gappers-DATE.json` — TOUS les gappers scannés 3-500 %. *(existe)*

### 2. Filtre de base — univers tradable
`data/computed/tradable-DATE.json` — sous-ensemble passant gap 3-13 %, prix 3-20 $,
float 5M-50M, exclusions (reverse-split / rachat-cible). Contient le champ **`added`** par titre. *(existe)*

### 3. Heure d'arrivée du gap — par titre
Champ **`added`** (`HH:MM`) de `tradable-DATE.json`. C'est l'ancre point-in-time. *(existe)*

### 4. Construction des fichiers de gappers PAR BANDE  *(à bâtir)*
Découper les titres de `tradable-` en **fichiers par bande de gap**, chacun gardant **l'heure
d'arrivée dans cette bande**.

- **Le gap bouge pendant la journée → un titre peut apparaître dans PLUSIEURS fichiers de bande.**
  Exemple : un titre qui gappe **3 % à 10:00** va dans le fichier bande 3 % (arrivée 10:00) ; si
  le **même titre** atteint **8 % à 11:00**, il va AUSSI dans le fichier bande 8 % (arrivée 11:00).
- Pour chaque bande, on enregistre **l'heure à laquelle le titre est entré dans cette bande**
  (1re minute où son gap franchit le seuil de la bande). Cette heure est l'ancre point-in-time
  **propre à cette bande** (et jamais avant son `added` global, par construction).
- Bandes basses visées : `3-5, 5-7, 7-10, 10-14, 14-20` (+ hautes si besoin).
- Sortie : un fichier par bande, chaque ligne = `ticker, date, band, band_arrival_time`,
  joint aux bougies 1-min correspondantes.

### 5. Filtre de fréquence PM
En parallèle, appliquer le gate de fréquence pré-marché (pm_frac 8:00-9:30 ≥ 20 %, cf mémoire
`filtre-frequence-pm-audit`) : on ne garde que les titres qui se qualifient encore. *(logique existe)*

### 6. Test des stratégies, point-in-time, par bande  *(à bâtir)*
Rejouer la recherche de stratégies (gap × signaux × sortie × stop × liquidité) **sur chaque
fichier de bande**, avec la contrainte : **entrée autorisée seulement à partir de l'heure
d'arrivée du titre DANS CETTE bande** (son `band_arrival_time`). Un même titre peut donc être
testé dans plusieurs bandes, chacune avec sa propre heure de départ. Chaque bande est testée sur
son propre fichier et son niveau de gap.

### 7. Tableau de résultats
Construire un tableau classé (par robustesse / P&L compte OOS), **groupé par bande de gap**,
à partir des tests point-in-time. C'est la base propre pour choisir quoi déployer.

## Ce qui existe déjà vs à bâtir

| Étape | Fichier / logique | État |
|---|---|---|
| 1. Tous les gappers | `gappers-DATE.json` | ✅ |
| 2. Filtre de base | `tradable-DATE.json` | ✅ |
| 3. Heure d'arrivée | champ `added` | ✅ |
| 4. Fichiers par bande (+ heure) | — | 🔨 à bâtir |
| 5. Filtre fréquence PM | pm_frac ≥ 20 % | ✅ logique |
| 6. Test stratégies point-in-time | entrée ≥ `added`, par bande | 🔨 à bâtir |
| 7. Tableau de résultats par bande | — | 🔨 à bâtir |

## Rappel méthodo

Le juge final reste le **forward/live** (`nightly_real_leaderboard` + journal réel du bot).
Le point-in-time rapproche le backtest du live, il ne le remplace pas. Un petit échantillon
*représentatif* vaut mieux qu'un gros échantillon d'un *faux* univers.
