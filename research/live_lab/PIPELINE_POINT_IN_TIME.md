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

### 4. Construction des fichiers de gappers PAR BANDE — `research/live_lab/build_bands.py` *(✅ fait)*
Découper les titres de `tradable-` en **fichiers par bande de gap**, chacun gardant **l'heure
d'arrivée dans cette bande**.

> **Script** : `build_bands.py`. Lit `tradable-DATE.json` (+ `added`) ∩ `bars-DATE.parquet` + `meta-`
> (prev_close). gap HOD par minute = `(max-high-courant − prev_close)/prev_close`. Entrées ≥ `added`,
> 1re minute dans chaque bande. **Sortie : `research/live_lab/bands/band-<lo>-<hi>.parquet`**
> (`ticker, date, band, band_arrival_min, band_arrival_ts`). Lecture seule sur la data. 11-16 exclu.

- **Le gap bouge pendant la journée → un titre peut apparaître dans PLUSIEURS fichiers de bande.**
  Exemple : un titre qui gappe **3 % à 10:00** va dans le fichier bande 3 % (arrivée 10:00) ; si
  le **même titre** atteint **8 % à 11:00**, il va AUSSI dans le fichier bande 8 % (arrivée 11:00).
- Pour chaque bande, on enregistre **l'heure à laquelle le titre est entré dans cette bande**
  (1re minute où son gap franchit le seuil de la bande). Cette heure est l'ancre point-in-time
  **propre à cette bande** (et jamais avant son `added` global, par construction).
- **Bandes construites = TOUTES, 3-500 %** (alignées sur `collect_universe`) :
  basses `3-5, 5-7, 7-10, 10-14, 14-20` (edge visé) **+ hautes `20-30, 30-50, 50-100, 100-500`**
  (vue complète, ne rien masquer — même si l'edge est en bas, on garde la visibilité du haut).
- Sortie : un fichier par bande, chaque ligne = `ticker, date, band, band_arrival_time`,
  joint aux bougies 1-min correspondantes.

### 5. Filtre de fréquence PM
En parallèle, appliquer le gate de fréquence pré-marché (pm_frac 8:00-9:30 ≥ 20 %, cf mémoire
`filtre-frequence-pm-audit`) : on ne garde que les titres qui se qualifient encore. *(logique existe)*

### 6. Test des stratégies, point-in-time, par bande — `research/live_lab/search_bands.py` *(🔨 à bâtir)*
Re-jouer le **générateur complet** (portée B) **sur chaque fichier de bande**, avec la contrainte
point-in-time.

> **Script** : `search_bands.py` (adapte `strategy_gen.py`). Pour chaque bande :
> - univers = les ticker-jours du `band-<lo>-<hi>.parquet` ; bougies depuis `bars-DATE.parquet`.
> - **contrainte clé** : pour chaque ticker-jour, **1re entrée ≥ son `band_arrival_min`** (fenêtre
>   effective = `max(band_arrival, début_fenêtre) → fin`). Un même titre est testé dans chaque
>   bande qu'il atteint, avec sa propre heure de départ.
> - **PAS de re-gate sur le gap** : le fichier de bande EST l'appartenance (évite le piège monotone).
> - **Briques** : les ~24 du moteur (`strategy_gen.PRIMS`), combos de 1-2 → ~500k configs.
>   × fenêtres × liquidité (`pm`/`act_30`/`dvol_30`) × sorties (`tp/trail/eod`) × stops. Prix 3-20.
> - **Enregistrer `open_pct` + `entry_med`** (que `strategy_gen` oubliait) → vérifier que le
>   point-in-time repousse bien les entrées (anti buy-the-open).
> - **Robustesse** : OOS + 2 moitiés + `t ≥ 2` + `cpte_oos > 0`. ⚠️ 500k configs = faux positifs
>   massifs → lire la robustesse, JAMAIS un gagnant isolé.
> - **Crash-safe** : checkpoint par bande (append CSV + `done`), cache du prep (comme `strategy_gen`).
> - **Sortie : `research/live_lab/results/search_bands-results.csv`** (colonne `band`).

### 7. Tableau de résultats — leaderboard par bande *(🔨 à bâtir)*
Classer `search_bands-results.csv` **par robustesse**, **groupé par bande**, en appliquant les
filtres anti-artefact (fréquence tradable `trj ≤ 10`, `open_pct` bas, congruence OOS). Sortie :
`research/live_lab/results/leaderboard-bandes.csv`. C'est la base propre pour choisir quoi déployer
— puis validation **forward/live** avant tout déploiement.

## Ce qui existe déjà vs à bâtir

| Étape | Fichier / logique | État |
|---|---|---|
| 1. Tous les gappers | `gappers-DATE.json` | ✅ |
| 2. Filtre de base | `tradable-DATE.json` | ✅ |
| 3. Heure d'arrivée | champ `added` | ✅ |
| 4. Fichiers par bande (+ heure) | `build_bands.py` → `bands/band-*.parquet` | ✅ fait |
| 5. Filtre fréquence PM | pm_frac ≥ 20 % | ✅ logique |
| 6. Test stratégies point-in-time | `search_bands.py` (entrée ≥ `band_arrival`, par bande) | 🔨 à bâtir |
| 7. Tableau de résultats par bande | leaderboard sur `search_bands-results.csv` | 🔨 à bâtir |

## Script ↔ fichier ↔ étape (qui produit quoi)

> À tenir à jour : évite de se redemander « quel fichier vient de quoi » (cf. incident du 11-16,
> deux dashboards en parallèle le jour du renommage → `universe-`/`gappers-` coupés en deux).

| # | Étape | Produit par | Fichier(s) écrit(s) | Lit / source | Cadence |
|---|---|---|---|---|---|
| 1 | Tous les gappers | `redcandlecatch_dashboard.py` → `collect_universe.py` | `collected_live/gappers-DATE.json` (champs `band, first_seen, last_seen`) | scanner IBKR `TOP_PERC_GAIN` | live, 60 s |
| 2 | Filtre de base | `redcandlecatch_dashboard.py` → `redcandlecatch_scan.py` + `eligible.py` (`write_all`, sticky) | `computed/tradable-DATE.json` (champs `gap, price, float_shares, …, added`) | le scan + gappers | live, 60 s |
| 3 | Heure d'arrivée | *(champs des fichiers ci-dessus)* | `first_seen` (gappers) / `added` (tradable) | — | — |
| — | Bougies 1-min | `fetch_universe_bars.py` | `collected_live/bars-DATE.parquet` + `meta-DATE.json` | `gappers-DATE.json` + IBKR | jour même |
| — | News | `fetch_universe_news.py` | `collected_live/news-DATE.json` | `gappers-DATE.json` | jour même |
| — | Halts | `fetch_halts.py` | `collected_live/halts-DATE.json` | Nasdaq | cron 15 min |
| 4 | Fichiers par bande (+ heure) | `build_bands.py` ✅ | `research/live_lab/bands/band-<lo>-<hi>.parquet` | `tradable-` + `bars-` + `meta-` | one-shot |
| 5 | Filtre fréquence PM | logique pm_frac | *(gate, pas un fichier)* | bars / tradable | — |
| 6 | Test stratégies point-in-time | `search_bands.py` (adapte `strategy_gen`) 🔨 | `results/search_bands-results.csv` (col. `band`) | `bands/band-*.parquet` + `bars-` | one-shot, crash-safe |
| 7 | Tableau résultats par bande | leaderboard 🔨 | `results/leaderboard-bandes.csv` | `search_bands-results.csv` | — |
| ⚠️ | QUARANTAINE | `fetch_eligible_bars.py` | `bars_eligible-` / `meta_eligible-` | `tradable-` | **ne plus utiliser** (prev_close contaminé) |

**Règle anti-confusion** : un seul écriveur par fichier. Les noms live (`gappers-`, `tradable-`,
`bars-`, `meta-`, `news-`, `halts-`) sont produits par les scripts ci-dessus et par eux seuls.
Tout fichier d'un ancien nom (`universe-`, `redcandlecatch-eligible-`) est un reliquat → `quarantaine/`.

## Notes sur les données (éviter les malentendus)

**Schéma `bars-DATE.parquet`** : colonnes `ticker, date, datetime, o, h, l, c, v`.
- ⚠️ **`date`** = le JOUR (`YYYY-MM-DD`). **`datetime`** = l'HEURE SEULE (`HH:MM`), **sans date**.
  Pour la date d'une bougie, lire **`date`**, jamais parser `datetime` (sinon la lib y colle
  la date du jour → faux « tout est aujourd'hui »). `mins` se calcule par découpe de `datetime`
  (`HH:MM` → minutes) dans `load_groups`.
- `v` = volume en actions (déjà ×100 depuis les lots IBKR).
- Fiabilité : les bars sont tirés **le jour même** (`fetch_universe_bars`) → `prev_close` correct.
  On **ne re-fetch PAS le passé** (un backfill historique est plus fragile que la capture same-day
  et l'`endDateTime=''` actuel ne sait pas viser un jour passé). On repart propre **vers l'avant**.

**Couverture `tradable-` → `bars-`** : ~**62-86 %** des titres `tradable-` d'un jour ont des bougies
dans `bars-` (le reste = échecs de fetch IBKR : contrats non qualifiés / radiés). La recherche
point-in-time teste donc le **sous-ensemble couvert** — petit n assumé. Amélioration possible plus
tard via un re-fetch **ciblé** des manquants (après correction du fetch date-ancré), gain limité.

**Jour 11-16 exclu** : capture partielle (process arrêté à 07:20 le jour du renommage), on le drop.

**⚠️ `band_arrival` = `max(added, 1re-minute-gap-dans-la-bande)`** (pas juste le franchissement du gap).
`build_bands` gate les bougies par `mins >= added` AVANT de chercher l'entrée dans la bande. Donc
toutes les entrées de recherche sont **gatées par `added`** (point-in-time). Conséquences :
- **En live, le terminator ne voit un titre qu'à partir de son `added`** → c'est automatiquement correct.
- **Un `verify_live` (détecteur == backtest) DOIT rejouer le détecteur à partir de `added`, pas de
  l'ouverture.** Rejouer depuis l'open crée de FAUX écarts sur les **petites bandes** (ex. 5-7 : le gap
  atteint 5 % AVANT `added`, donc le détecteur « gap≥5 » tirerait trop tôt). Sur les **hautes bandes**
  (14-20+) le gap est atteint tard, après `added`, donc `added` ne mord pas → un verify naïf passe
  quand même (④ : 38/38). **Ce n'est NI un bug du détecteur NI des données corrompues** — c'est le
  gate `added` qu'il faut reproduire. (Incident 19/11 : n°1 bande 5-7 donnait 90 % faux, 100 % une fois
  le gate `added` ajouté au verify.) Cf [[pipeline-point-in-time-added]], [[verifier-en-reel-avant-deploiement]].

**⚠️ RSI/indicateurs SOUS-CHAUFFÉS (<16 bougies)** : la recherche (`strategy_gen`/`search_bands`)
calcule les indicateurs sur un tableau qui s'étend et **tire des signaux dès les 1res bougies** (ex.
RSI 0→57→100 avec 9 bougies). Les détecteurs live ont un garde `len < n+2 → None` (RSI(14) pas
réchauffé) → ils **rejettent** ces entrées, à juste titre. Conséquence : ~7 % des entrées des petites
bandes (ex. 5-7) sont des **signaux bruités non-reproductibles en live** → l'edge mesuré y est
légèrement **gonflé**. PISTE : ajouter un **gate de warmup** (min bougies) à la recherche pour qu'elle
colle aux détecteurs. (Découvert 19/11 en voulant déployer le n°1 bande 5-7 : reste 93 % même après le
gate `added`, le reste = entrées <16 bougies.)

## Rappel méthodo

Le juge final reste le **forward/live** (`nightly_real_leaderboard` + journal réel du bot).
Le point-in-time rapproche le backtest du live, il ne le remplace pas. Un petit échantillon
*représentatif* vaut mieux qu'un gros échantillon d'un *faux* univers.
