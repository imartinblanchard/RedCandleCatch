# STRATEGY.md — RedCandleCatch_SmallCap (stratégie LIVE, dip-buy momentum, LONG)

> Nom de la stratégie : **RedCandleCatch_SmallCap** (achat du dip sur gappers small-cap).
> Les modules sont nommés `redcandlecatch_*` (renommés le 19/09 ; anciennement `RedCandleCatch_*`).
> À ne pas confondre avec `redcandleCatch_snp500/` (expérience S&P 500 daily, classée).

La stratégie que le bot **`redcandlecatch_terminator`** trade réellement. Achète les
**replis (−5% / −1,5%)** de small-caps qui gappent à la hausse, protège avec un stop puis un
trailing stop, et sort avant la clôture. Pour l'historique daté des découvertes qui
justifient chaque paramètre, voir **[FINDINGS.md](FINDINGS.md)**. L'ancienne
stratégie VWAP-pullback (jamais mise en prod) est archivée dans
**[STRATEGY_VWAP_ARCHIVE.md](STRATEGY_VWAP_ARCHIVE.md)**.

> 🔄 **MISE À JOUR 2026-09-23 — fait autorité (rebuild point-in-time `research/pit_gappers/`).**
> L'ancien edge post-open (gap 10-20) était un **artefact de look-ahead** (le backtest entrait le
> dip AVANT que le titre soit éligible). Mesuré proprement il est nul. **Nouvelle règle live :**
> - **Bande de gap 5-10 %** (seule bande OOS-validée ; les gros gaps 30-100 % PERDENT).
> - **PM/post-open classé par l'heure du DIP** (pas `added`) + **recheck** : entrée seulement si le
>   gap est ENCORE dans 5-10 % au moment du dip (l'éligibilité étant sticky).
> - **Plancher de float 5M** (ultra-bas = seul segment perdant OOS ; inconnu passe).
> - **Entrée en LIMITE marketable** (l'edge +0,5 %/tr meurt à +0,5 % slippage → jamais d'ordre marché).
> - Inchangé : dip **1,5 %**, activation **+10 %**, trail **2 %**, stop **−10 %**, prix 3-20 $, `TRADE_PM=False`.
> Backtest règle exacte : **+0,46 %/tr (t=3,5), TEST +0,61 % (t=3,2)**, ~13 tr/j, tout en séance.
> Note PM : edge PM plus GROS (+2 à +4 %) et robuste au slippage (~2 %/côté) MAIS win ~90 % =
> artefact microstructure (stop qui ne se déclenche pas sur bougies éparses) → PM reste OFF, à
> chiffrer sérieusement avant activation. Le paragraphe ci-dessous décrit l'ANCIENNE config (historique).

> ⚠️ **Statut : forward-test PAPER en cours, edge validé IN-SAMPLE.** Les paramètres
> sont validés sur backtest (jan–août 2026) qui est une **borne supérieure optimiste**
> (biais du survivant + fills parfaits supposés + P&L brut hors commissions — voir
> [FINDINGS.md](FINDINGS.md)). Le mode `--live` passe de VRAIS ordres ; sans `--live`
> c'est du PAPER/journal. Taille actuelle : **1 action/trade** (test à risque minimal ;
> à 1 action les commissions rendent le mode volontairement perdant, il sert à
> débusquer les bugs, pas à gagner).

## Comment lancer

```bash
cd ~/dev/stock-journal-long
source .venv/bin/activate                # le prompt affiche (.venv)
```

**Il y a exactement 2 choses à lancer, et il faut les DEUX** (idéalement dans tmux,
pour ne pas se retrouver avec un process orphelin — voir Notes opérationnelles) :

```bash
python -m bot.redcandlecatch_dashboard          # 1) SCANNER — écrit le fichier de signaux sticky
python -m bot.redcandlecatch_terminator --live  # 2) EXÉCUTEUR — lit les signaux, détecte le dip, trade
# sans --live : mode PAPER (journalise, aucun ordre réel)
```

Le dashboard écrit `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json` (sticky : un
ticker qui a été éligible reste dans le fichier) ; le terminator lit ce fichier à
chaque cycle. **Si le dashboard ne tourne pas, le terminator lit un fichier figé**
et ne voit plus de nouveaux candidats.

Les librairies (`redcandlecatch_scan.py`, `eligible.py`, `indicators.py`,
`execution/ibkr_broker.py`, `config.py`) ne se lancent jamais directement.

## La stratégie en clair

Thèse : les small-caps qui gappent fort **montent en pré-marché puis fadent**. Mais
pendant la séance régulière elles font des **micro-replis suivis de reprises**. On
achète le repli (une bougie qui casse de −5% en PM / −1,5% post-open), on protège serré, et on laisse courir
avec un trailing stop pour capturer la reprise.

### 1. Sélection de l'univers (`redcandlecatch_scan.py`)
| Critère | Valeur | Note |
|---------|--------|------|
| **Gap** | **+10% à +20%** | mesuré sur le **plus-haut de 04:00 → midi** vs clôture veille (`ENABLE_POSTOPEN`, 16/09) — capte aussi les runners qui entrent dans la bande **après** 9:30 |
| Prix | **3–20 $** | |
| **Float** | **< 500 M actions** | filtre small-cap (22/09 : passé de market-cap → float, dans `evaluate` via Finviz) |
| Autres filtres | **AUCUN** | float, volume PM, ratings, anti-pump, inst% : tous **désactivés** (validé nuisibles ou non prouvés — voir FINDINGS) |

⚠️ **Le gap est mesuré sur le PM-high, pas à l'open.** C'est décisif : sélectionner
par le gap à l'open détruit l'edge (voir [FINDINGS.md](FINDINGS.md) — l'edge vit dans
les « runners fadés » qui ont couru en PM et sont déjà retombés à 9:30).

### 2. Entrée (`redcandlecatch_terminator.py`)
- **Déclencheur** : une bougie 1-min ferme sous le seuil de **dip ADAPTATIF**, avec prix
  3–20 $. On achète au close de cette bougie. **Le dip dépend du MOMENT où le ticker est
  devenu éligible** (heure `added` du fichier de signaux), PAS du volume :
  - **Dip −5%** (`DIP`) si éligible **AVANT l'ouverture** (`added < 09:31`) = gapper
    pré-marché survolatile (validé sur `candles.parquet`, gap 10-20).
  - **Dip −1,5%** (`DIP_LIQUID`) si **ajouté APRÈS l'ouverture** (`added ≥ 09:31`) = runner
    post-open, plus calme. Validé OOS 16/09 (+1,97%/tr, pf 2,13, t=6,7 en test —
    `research/intraday_gappers/`).
  - Rationnel : les deux populations ont des volatilités différentes → le pré-marché
    survolatile a besoin d'un dip profond (−5%), le post-open plus calme d'un dip léger (−1,5%).
- **PM DÉSACTIVÉ (18/09, `TRADE_PM=False`)** : on ne trade QUE les runners post-open (edge PM
  intrinsèquement faible, net-négatif après commissions). Les PM sont toujours COLLECTÉS (scanner) pour la recherche.
- **1 entrée par ticker par jour** (`self.done`) — voir FINDINGS : autoriser une 2e
  entrée est bénéfique mais **pas encore implémenté**.

### 3. Sortie — 2 phases + backstop
1. **Phase 1 — STOP fixe −10%** (`STOP = 0.10`) : posé dès le fill. Survit au repli initial.
2. **Bascule ADAPTATIVE** (`ACTIVATE_PM = 0.05` / `ACTIVATE_POST = 0.10`) : quand le trade
   atteint le seuil, on annule le stop fixe et on passe en phase 2. Seuil **+5% pour les
   gappers PM**, **+10% pour les runners post-open** (18/09). ⚠️ effet OPPOSÉ selon la
   population (validé 8 mois) : le PM plonge fort puis rebondit faiblement (+5% optimal, +10%
   le rend négatif) ; le post-open fait un petit repli et continue (+10% optimal). Le seuil
   retenu à l'entrée est stocké dans `pos['activate']`.
3. **Phase 2 — TRAIL 2%** (`TRAIL = 0.02`) : ordre trailing stop natif IBKR qui suit le
   sommet ; vend au marché quand ça retombe de 2% sous le plus-haut. C'est le paramètre
   dominant de la stratégie.
4. **Sortie forcée à 15:55** (2 niveaux) : à 15:55 ET (avant le vrai close 16:00, marché
   encore liquide), toute position ouverte est vendue au marché (limite marketable GTC
   `outsideRth`, re-price chaque cycle). Si pas remplie → filet extended hours → sinon GTC
   au prochain open. (Corrige le bug du backstop 16:30 qui laissait des positions overnight.)

> 🐛 **Piège trailing stop (corrigé le 14/09) :** l'ordre TRAIL IBKR doit fournir
> **UNIQUEMENT `trailingPercent`**, jamais `trailStopPrice` en plus — sinon IBKR
> rejette « Invalid Price » (err 201) et la position reste **à nu**. Voir FINDINGS.

### 4. Fenêtre
Entrées **09:30 → 15:55 ET** (`ENTRY_END`). **Sortie forcée dès 15:55** (`HARD_EXIT`),
puis le cycle continue à gérer/solder après la clôture jusqu'au fill (extended → GTC).
(⚠️ Différent de l'ancienne stratégie VWAP qui, elle,
tradait le pré-marché.)

### Paramètres (constantes dans `bot/redcandlecatch_terminator.py` et `bot/redcandlecatch_scan.py`)
| Constante | Valeur | Sens |
|-----------|--------|------|
| `GAP_MIN`, `GAP_MAX` | 10, 20 | fourchette de gap (%) |
| `ENABLE_POSTOPEN` / `POSTOPEN_END` | True / (12,0) | gap mesuré sur le high **04:00→midi** (post-ouverture) |
| `PRICE_MIN`, `PRICE_MAX` | 3, 20 | prix $ |
| `ENABLE_LIQUIDITY` / `MIN_DOLLAR_VOL` | **False** / 500 000 | filtre SCANNER session **DÉSACTIVÉ le 19/09** (le garde-fou liquidité est le $200K bougie-dip). `dollar_vol` reste collecté. |
| `MIN_DIP_DOLLAR_VOL` | 200 000 | filtre EXÉCUTEUR (18/09) : n'entre que si la **bougie de dip** a `volume × close ≥ 200 000$` (facilité d'exécution, anti-slippage) |
| `DIP` | 0.05 | dip des gappers **pré-marché** (éligibles avant `PREOPEN_CUTOFF`) |
| `DIP_LIQUID` | 0.015 | dip des runners **post-ouverture** (ajoutés après `PREOPEN_CUTOFF`) |
| `PREOPEN_CUTOFF` | '09:31' | frontière : `added` avant = dip −5%, après = dip −1,5% |
| `TRADE_PM` | False | 18/09 : ne trade PLUS les gappers PM (post-open seulement) ; PM toujours collectés |
| `STOP` | 0.10 | phase 1 : stop fixe −10% (du prix SIGNAL) |
| `ACTIVATE_PM` / `ACTIVATE_POST` | 0.05 / 0.10 | bascule phase 2 : +5% (PM) / +10% (post-open), adaptatif — du prix SIGNAL |
| `TRAIL` | 0.02 | phase 2 : trailing natif IBKR 2% |
| `HARD_EXIT` / `EXT_CLOSE` | (15,55) / (20,0) | sortie forcée à 15:55 ; re-price marketable jusqu'à 20:00 puis GTC |
| `SHARES` | 1 | 1 action/trade (test ; net-positif dès ~1000$ de position) |
| `FILL_TIMEOUT` | 3 | cycles d'attente du fill avant de considérer halt/illiquide |

## Notes opérationnelles (à lire avant de trader en réel)

- **Réconciliation broker** : le broker est la source de vérité. À chaque cycle, si une
  position existe sans ordre de vente vivant (redémarrage, annulation IBKR), le bot
  repose la protection. Voir la mémoire `reconciliation-protections`.
- **Prix de fill réel** : à la confirmation, `pos['entry']` est remplacé par le vrai
  prix payé (slippage journalisé), sinon le forward-test surestime la perf.
- **Redémarrage sûr** : positions ouvertes dans `redcandlecatch-open.json`, trades
  clôturés dans `redcandlecatch-journal.csv`. On peut relancer le bot ; il
  reprend/reprotège les positions. **Redémarrer de préférence quand aucune position
  n'est ouverte.**
- **⚠️ Process orphelin** : le terminator `--live` lancé dans un terminal/tmux qui
  meurt devient orphelin (PPID 1) et **continue de trader** sans que tu le saches.
  Toujours vérifier : `ps aux | grep redcandlecatch_terminator`. Le lancer dans **tmux** évite
  ça. Pour l'arrêter proprement : `kill <PID>` (SIGTERM = arrêt gracieux).
- **Compte IBKR** : port 4001 (compte réel), le broker utilise `clientId=31`. Les
  small caps exigent un compte financé (> ~2500 CAD) — voir mémoire `ibkr-bloque-small-caps`.

## Journaux & données
| Fichier | Contenu |
|---------|---------|
| `data/computed/redcandlecatch-eligible-YYYY-MM-DD.json` | fichier de signaux sticky (dashboard → terminator) |
| `data/computed/redcandlecatch-journal.csv` | trades clôturés (date,ticker,gap,entry,exit,reason,pnl_pct,mfe_pct,…,mode) |
| `data/computed/redcandlecatch-open.json` | positions ouvertes (restart-safe) |

## Statut & prochaines étapes (au 2026-09-16)
- ✅ Éligibilité **post-ouverture** (gap 04:00→midi) + **dip adaptatif** −1,5%/−5% (validé OOS,
  post-open : +1,97%/tr, pf 2,13, t=6,7 en test — voir FINDINGS / research/intraday_gappers).
- ✅ Filtre **liquidité** double : SCANNER (dollar-volume session ≥ 500 000$, écarte les spikes
  type ARTL) + EXÉCUTEUR (**bougie de dip** ≥ 200 000$, 18/09, pour la facilité d'exécution / anti-slippage type LGHL).
- ✅ Niveaux **sur le prix SIGNAL** (activation +5%/+10% théorique), P&L sur le fill réel. Trail **natif IBKR**.
- ✅ Bugs corrigés : trailing (err 201), peak (bougie d'entrée), **prev_close** (gap PM faussé).
- ✅ Commissions : edge **net-positif dès ~1000$** de position (drag ~0,16%) ; perd seulement à 1 action.
- ✅ Activation ADAPTATIVE (18/09) : **+5% PM / +10% post-open**. Effet OPPOSÉ selon la population
  (validé 8 mois) : PM veut +5% (pf 1,27 ; +10% le rend négatif), post-open veut +10% (exp +2,43→+3,08%).
  Un +10% global aurait dégradé le PM. Adaptatif = meilleur combiné (pf 2,75).
- ⏳ Forward-test PAPER (sans `--live`) recommandé avant de repasser en réel avec ces changements.
- 📋 Candidat non déployé : **max 2 entrées/ticker/jour** (gain propre in-sample, à valider OOS).
- 📋 Reporté : notifications **Discord** (clé `DISCORD_WEBHOOK` prête dans config).
