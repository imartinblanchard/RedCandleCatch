# STRATEGY_VWAP_ARCHIVE.md — ancienne stratégie VWAP-pullback (ARCHIVE)

> 🗄️ **CE N'EST PAS LA STRATÉGIE LIVE.** Ce document décrit la première stratégie
> testée (VWAP-pullback pré-marché, `terminator_long.py` + `bot/strategy.py`),
> développée le 2026-08-21. Elle n'a jamais été mise en production. Le bot qui trade
> réellement utilise `redcandlecatch_terminator` + `redcandlecatch_scan` (dip −5% / trail 2%) —
> voir **[STRATEGY.md](STRATEGY.md)** pour la stratégie live et **[FINDINGS.md](FINDINGS.md)**
> pour l'historique des découvertes. On garde ce fichier pour référence : la logique
> VWAP+2σ et les leçons structurelles restent instructives.

---

Backtested pre-market long strategy for the `terminator-long` bot. Developed
2026-08-21 by replaying the historical checklist (~389 gapper rows, May–Jul 2026)
on 1-min SIP bars.

> ⚠️ **Status: IN-SAMPLE ONLY — NOT YET VALIDATED.** Every parameter below was
> tuned on the same May–Jul sample.

## La stratégie expliquée (en clair)

### L'idée de base
On trade des **small-caps qui gappent à la hausse** (+4%+) en **pré-marché**. Le
constat clé du backtest : ces stocks **montent fort en pré-marché puis s'effondrent
à l'ouverture de 9:30** (le "gap and crap" que le projet short exploite en shortant).
La stratégie : **acheter les replis pendant le run pré-marché, sortir AVANT l'open** —
encaisser la montée, éviter le fade.

### L'entrée — 7 conditions (repli sur VWAP + rebond confirmé par le volume)
1. **Liquidité** : volume PM cumulé ≥ 150K.
2. **Surge de volume** : bougie d'entrée ≥ 3× le volume moyen des 5 précédentes.
3. **Tendance** : les 3 bougies avant l'entrée clôturent au-dessus du VWAP.
4. **Tag du VWAP** : la bougie touche le VWAP (support dynamique).
5. **Rebond vert** : bougie verte qui clôture au-dessus du VWAP.
6. **Tradabilité** : range moyen ≥ 1% sur les 5 dernières bougies **et** volume ≥ 10K.
7. **Reward mini** : la bande VWAP+2σ (le TP) doit être ≥ 5% au-dessus de l'entrée.

### La sortie — 3 façons
1. **TP à la bande VWAP+2σ** ⭐ (meilleur exit du backtest).
2. **Stop −5%**.
3. **Backstop 9:30** : jamais dans la séance régulière.

### Paramètres (`bot/strategy.py`)
| Constant | Value | Meaning |
|----------|-------|---------|
| `MIN_ABOVE` | 3 | bars above VWAP before the pullback |
| `VWAP_TOL` | 0.003 | pullback tags VWAP if bar low ≤ VWAP × (1 + 0.003) |
| `SURGE` | 3.0 | entry-bar volume ≥ 3× avg of prior 5 bars |
| `MIN_PM_VOL` | 150 000 | cumulative pre-market volume gate |
| `STOP_PCT` | 0.05 | fixed initial stop, −5% |
| `BAND_K` | 2 | take profit at VWAP + 2σ |
| `MIN_RANGE_PCT` | 0.01 | tradability: avg bar range ≥ 1% |
| `MIN_BAR_VOL` | 10 000 | tradability: entry-bar volume floor |
| `MIN_TARGET_PCT` | 0.05 | reward gate: band ≥ 5% above entry |

### Why these rules (in-sample research path, 246 entries)
| Change | avg P&L / trade |
|--------|-----------------|
| Hold to 9:30 open, stop −10% | −3.29% (loser) |
| Stop sweep | all negative; −5% least-bad |
| Exit diagnostic | MFE +21% vs open −5% → run is pre-market, fade at open |
| Fixed TP pre-market (+15%) | +0.20% |
| Trailing 5% from peak | +0.98% |
| + volume surge ≥ 3× | +1.71% |
| TP at VWAP + 2σ band | +2.68% — best |
| + tradability gate | +3.83% |

**Three structural lessons (still valid):**
1. **Never hold to the open** — gappers run pre-market and fade at 9:30.
2. **Trail tight, don't use the 9 EMA** (whipsaw on 1-min).
3. **Confirm the entry with a volume surge** (relative ≥3× beats absolute).
