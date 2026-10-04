# Pistes d'amélioration du moteur NHL — résultats mesurés

*2026-10-04. Harnais `nhl/scripts/simulate_roi.py` en walk-forward. Validation : saison 2023-24. Test : oct. 2024 → janv. 2025. Les détails de chaque phase sont dans `roi_by_phase.md`.*

**Règle d'adoption, fixée avant les tests.** Une piste est adoptée seulement si elle est positive ou neutre à la fois en validation et en test, au prix d'exécution comme aux prix médian et meilleure cote, et sans dégrader la log-loss. Les seuils ne sont jamais réglés sur le ROI : la phase P2 « réglée » faisait +33 % en validation et −57 % en test.

**Prix d'exécution simulé :** médiane des soft books × 0,94.

## 1. Résumé

| | Avant (P3, 03/10) | **Après (config adoptée)** | Écart |
|---|---|---|---|
| Paris | 157 | **208** | **+32 %** |
| Gain net | +30,7 U | **+45,9 U** | **+50 %** |
| ROI | +26,0 % | +24,9 % | ≈ |
| Gain en validation | +24,6 U | +31,8 U | ↑ |
| Gain en test | +6,1 U | +14,0 U | ↑ |
| Paris au prix médian | 830 (+13,1 %) | 1 108 (+13,3 %) | ↑ |

La config adoptée est écrite dans `nhl/config/settings.toml [betting]` :
- EV ≥ 4 % ;
- Kelly 1/6 ;
- plafonds de 5 U par match et 30 U par jour ;
- cote d'exécution = meilleure cote parmi Winamax, Betclic, Unibet et PMU (`exec_books`).

`paper_trading` reste à `true`.

> ⚠️ **Le gain n'est pas encore prouvé.** Vu par Pinnacle (no-vig), l'EV moyenne des paris pris reste **négative (−8,7 %)**. Le ROI positif du backtest repose donc sur des écarts que le marché le plus efficace ne confirme pas : il peut s'agir de variance. Seuls le paper trading et le CLV (cote de clôture) trancheront.

## 2. Pistes testées, classées par impact

| # | Piste | Paris | Gain net | ROI | Val / Test (U) | Verdict |
|---|---|---|---|---|---|---|
| A | **Prix : meilleur book FR** au lieu de Winamax seul | 157 → **830 à 1 108** (prix médian) | ×2 à ×3 en U | +13 % | positif dans les 2 périodes | ✅ **adoptée, levier n°1 du volume** |
| — | **Combo B + C + H** (EV 4 %, Kelly 1/6, plafonds 5/30) | 208 | **+45,9** | +24,9 % | +31,8 / +14,0 | ✅ **adoptée** |
| C | Kelly 1/4 | 168 | +51,8 | +25,4 % | +39,4 / +12,4 | ⚠️ meilleur gain, mais mises et variance ×2 → réservé à une bankroll qui l'accepte (voir le simulateur, multiplicateur ×2) |
| C | Kelly 1/6 | 164 | +40,8 | +26,5 % | +28,4 / +12,5 | ✅ (dans le combo) |
| B | EV ≥ 4 % | 190 | +33,1 | +24,3 % | +26,0 / +7,1 | ✅ (dans le combo) |
| B | EV ≥ 3 % | 240 | +33,3 | +20,6 % | +26,8 / +6,4 | ➖ plus de volume, mais ROI en baisse |
| B | EV ≥ 8 % | 67 | +27,9 | +43,6 % | +21,2 / +6,7 | ❌ ROI élevé mais gain net plus bas (trop sélectif) |
| H | Plafonds 5 U/match et 30 U/jour | 160 | +32,6 | +27,2 % | +26,6 / +6,1 | ✅ (dans le combo) |
| B' | Aucun pari sans Pinnacle | 146 | +32,4 | +29,8 % | +26,4 / +6,0 | ❌ moins bon aux prix médian et meilleure cote |
| D | Retrain **mensuel** au lieu de trimestriel | 225 | +34,3 | +18,1 % | +22,9 / +11,4 | ❌ plus faible dans les 2 périodes, log-loss égale ou pire, 3× plus coûteux |
| F | Features V2 (part du PP de l'équipe, PK adverse, interactions) | 238 | +32,9 | +16,1 % | +23,9 / +9,0 | ❌ log-loss des passes moins bonne (0,6286 contre 0,6278), gain ↓ |
| E | Tuning Optuna du LGBM | 228 | +61,4 | +31,7 % | +38,2 / +23,2 | ❌ log-loss −0,1 % en validation, non reproduite en test ; ROI instable (§3) |
| — | LGBM seul au lieu de l'ensemble LGBM+XGB+Cat | 254 | +69,3 | +31,2 % | +54,5 / +14,8 | ❌ meilleur au prix ×0,94, mais **pire au prix médian** (+8,0 % contre +13,3 %) et à la meilleure cote : l'avantage n'est pas robuste |

Garde-fous **confirmés indispensables** :
- Filtre d'éligibilité : sans lui, le modèle mise sur des défenseurs au marché buteur et le ROI tombe à −38 %.
- Exclusion du début de saison (moins de 10 matchs) : négatif dans les deux saisons.
- Plancher de mise 0,5 U : ne coûte que 12 paris.

## 3. Piste E — tuning des hyperparamètres

Optuna, 25 essais par marché, critère = log-loss sur la validation 2023-24 (le test 2024-25 n'est jamais vu). Paramètres dans `nhl/config/tuned_gbm_params.json`.

| | Log-loss val. par défaut | Log-loss val. tunée | Gain |
|---|---|---|---|
| Buteur | 0,46518 | 0,46472 | −0,1 % |
| Passe | 0,51388 | 0,51334 | −0,1 % |

Rejoué au harnais avec la stratégie actuelle (LGBM tuné contre LGBM par défaut) :

| | Paris | Gain net | Val (U) | Test (U) | ROI prix médian | ROI meilleure cote | Log-loss test but / ast |
|---|---|---|---|---|---|---|---|
| LGBM par défaut | 254 | +69,3 | +54,5 | +14,8 | +8,0 % | +6,9 % | 0,5585 / 0,6230 |
| LGBM tuné | 228 | +61,4 | +38,2 | +23,2 | +8,5 % | +3,9 % | 0,5591 / 0,6231 |

❌ **Rejetée.** Le gain de log-loss est négligeable. Il ne se retrouve pas en test : la log-loss des buteurs y est même un peu moins bonne. Le ROI bouge dans des directions opposées selon la période et le prix, donc c'est du bruit. Le modèle est limité par l'**information** (les features), pas par ses hyperparamètres.

## 4. Piste G — nouveaux marchés (points, tirs cadrés)

Il n'y a pas assez de cotes historiques pour simuler un ROI. On mesure donc la qualité prédictive hors échantillon sur trois saisons, contre une référence naïve : la fréquence du joueur sur ses 20 derniers matchs, shrinkée vers la moyenne. Résultats dans `new_markets_eval.csv`.

| Marché | Saison | Taux | LL modèle | LL naïf | Gain LL | AUC modèle | AUC naïf | ECE |
|---|---|---|---|---|---|---|---|---|
| Points ≥ 1 | 2023-24 | 38,6 % | 0,6165 | 0,6323 | −2,5 % | 0,684 | 0,657 | 0,014 |
| Points ≥ 1 | 2024-25 | 38,1 % | 0,6146 | 0,6319 | −2,7 % | 0,683 | 0,653 | 0,013 |
| Points ≥ 1 | 2025-26 | 39,0 % | 0,6210 | 0,6345 | −2,1 % | 0,681 | 0,655 | 0,018 |
| Tirs ≥ 2 | 2023-24 | 59,2 % | 0,6226 | 0,6365 | −2,2 % | 0,688 | 0,662 | 0,031 |
| Tirs ≥ 2 | 2024-25 | 54,7 % | 0,6388 | 0,6516 | −2,0 % | 0,682 | 0,658 | 0,020 |
| Tirs ≥ 2 | 2025-26 | 54,6 % | 0,6367 | 0,6532 | −2,5 % | 0,683 | 0,654 | 0,008 |
| Tirs ≥ 3 | 2023-24 | 36,1 % | 0,5963 | 0,6088 | −2,1 % | 0,700 | 0,676 | 0,028 |
| Tirs ≥ 3 | 2024-25 | 31,1 % | 0,5677 | 0,5806 | −2,2 % | 0,698 | 0,672 | 0,024 |
| Tirs ≥ 3 | 2025-26 | 31,4 % | 0,5666 | 0,5832 | −2,9 % | 0,701 | 0,673 | 0,011 |

**Lecture.** Le modèle bat la référence naïve de façon **stable** (−2 à −3 % de log-loss, +2,5 points d'AUC) et il est bien calibré. Les tirs cadrés sont le marché le plus prévisible (AUC 0,70). Ce n'est pas encore une preuve d'edge contre les bookmakers, qui font mieux qu'une moyenne mobile. Les cibles `target_pts`, `target_sog2` et `target_sog3` et les features (`FEATURES_G`) existent déjà, avec tests de parité.

**Recommandation.** Ajouter `player_points` et `player_shots_on_goal` (lignes 1.5 et 2.5) à la collecte des cotes, d'abord en **simple journalisation**, pendant 4 à 8 semaines. On obtient ainsi un historique de cotes pour simuler le ROI avec le même harnais, avant tout pari, même en paper trading. Ces marchés multiplieraient le nombre de picks disponibles par soirée.

## 5. Risque opérationnel n°1 — couverture des books FR : **CONFIRMÉ, bloquant**

Test live du 2026-10-04 (`python nhl/scripts/check_odds_coverage.py`, rapport `odds_coverage_2026-10-04.md`), sur 3 matchs, avec les régions `eu,fr,uk,us` :

| Marché | Books qui cotent |
|---|---|
| Buteur | fanatics, fanduel, draftkings, bovada, pinnacle |
| Passes, points, tirs cadrés | **pinnacle uniquement** |

- **Aucun book FR** (Winamax, Betclic, Unibet, PMU) ne cote les props joueurs NHL dans The Odds API.
- Confirmé par l'historique : sur les 815 319 cotes de `odds_long.parquet` (régions `us,eu`), il n'y a aucun book FR.
- Les books FR sont bien dans l'API (région `fr` : betclic_fr, winamax_fr, unibet_fr, pmu_fr, netbet_fr), **mais seulement pour les marchés de match**. Test sur 2 matchs à venir, région `fr` : `h2h` → 4 à 5 books FR ; props joueurs → aucun book. L'endpoint `/events/{id}/markets` le confirme : Winamax, Betclic et PMU ne proposent que `h2h` et `h2h_3_way` ; NetBet y ajoute `h2h_ot`, `spreads` et `totals`. La documentation liste les books disponibles, pas les marchés que chacun couvre.
- Le chemin prod `fetch_nhl_odds` a été testé de bout en bout. Il émet bien le warning « Aucun book d'exécution … aucun pari possible ».

**Conséquence.** En l'état, le bot ne produira **aucun pick**. L'option « meilleur book FR » est codée mais n'a rien à lire. Les ROI simulés reposent sur un *proxy* : médiane des books US × 0,94. Ils supposent que Winamax affiche des cotes comparables, ce qui n'a pas été vérifié.

**Options, à décider :**
1. Scraper Winamax en direct (Pinnacle via The Odds API reste la référence no-vig).
2. Calculer l'EV sur le proxy médiane US × 0,94 et vérifier la cote Winamax à la main avant chaque pari.
3. Parier sur un book présent dans The Odds API (Pinnacle n'est pas accessible en France).

## 6. Prochaines étapes, par ordre de priorité

1. **Paper trading pendant 4 à 8 semaines** avec la config adoptée. Suivre le **CLV** (snapshot à T−5 déjà en place) : c'est le seul indicateur d'edge qui converge vite. Un CLV moyen supérieur à 0 contre Pinnacle valide le modèle ; un CLV négatif confirme l'EV Pinnacle de −8,7 %.
2. Vérifier la couverture des books FR (§5).
3. Collecter les cotes points et tirs (§4) pour rendre la piste G simulable.
4. Ne passer en réel qu'avec un CLV positif. Kelly 1/4 seulement après 300 paris réels positifs.

Le simulateur `simulateur.html` contient les données réelles de la config adoptée. Il est régénéré par `python nhl/scripts/export_simulator_data.py` après chaque changement de config.
