# Audit complet du moteur BetEngine — `shared/` et `nhl/`

*2026-10-04 · branche `test` (commit 9d0911a) · audit Senior Data Scientist / ML Engineer, paris quantitatifs.*
> **Mise à jour :** les phases P0 → P3 de ce rapport ont été exécutées le même jour. Résultats, décisions et évolution des notes (12,5 → 14/20) : [reports/RECAP_AUDIT_P0_P3_2026-10-04.md](reports/RECAP_AUDIT_P0_P3_2026-10-04.md).

*Fait suite à [AUDIT_NHL_2026-10-03.md](AUDIT_NHL_2026-10-03.md). Ce rapport audite l'état **actuel** du code après les phases P0 → P3 et la bascule en mode « proxy + cote seuil ».*

## 0. Verdict exécutif

**Note globale : 12,5 / 20.**

Le chantier P0 → P3 a réglé l'essentiel de l'audit précédent : une seule fonction de features pour l'entraînement, la simulation et la prod, une clé `playerId`, un modèle calibré sans repondération, une stratégie de mise unique (`nhl/core/betting.py`), le paper trading, un monitoring de dérive et des tests. L'architecture ML est désormais **saine**.

Il reste quatre problèmes qui empêchent de faire confiance aux chiffres en conditions réelles :

1. **Les données d'historique ne sont pas versionnées** (`mp_gamelogs.parquet` est ignoré par git). Sur un VPS cloné proprement, les features « carrière » seraient calculées sur une seule saison au lieu de 2008 → aujourd'hui, et le retrain hebdomadaire s'entraînerait sur 1 à 2 saisons. **À vérifier sur le VPS en priorité.**
2. **Le gate du retrain hebdomadaire est biaisé** : il compare le nouveau modèle à un modèle qui a déjà vu le holdout. Le modèle de prod restera donc figé.
3. **La récupération des cotes ne filtre pas les matchs par date** : si une équipe joue le lendemain, les cotes des deux matchs se mélangent.
4. **L'edge n'est pas démontré.** Hors période de validation, il reste 38 paris de test, et 84 % du gain test vient d'un seul pari. L'EV vue par Pinnacle reste négative (−8,7 %). La prod passeur n'utilise de plus pas le prix qui a été simulé.

**Recommandation : rester en `paper_trading = true`** et traiter les P0 ci-dessous avant toute mise réelle.

| Axe | Note | Évolution vs 03/10 | Commentaire |
|---|---|---|---|
| Architecture logicielle | 13/20 | +1 | Bon découpage ; `shared/` dépend encore de `nhl/`, beaucoup de code mort |
| Data engineering & features | 13/20 | +7 | Parité train/serve réelle et testée ; données d'historique hors git |
| Modélisation ML | 14/20 | +3 | GBDT calibré isotonique temporel, bon niveau vs Pinnacle en log-loss |
| Validation & backtest | 10/20 | +3 | Harnais walk-forward propre, mais test minuscule et réutilisé pour choisir la config |
| Stratégie de pari (EV/Kelly) | 12/20 | +4 | Blend modèle/Pinnacle, Kelly sans plancher, plafonds par match ; prix proxy non validé |
| MLOps / prod / monitoring | 10/20 | +3 | Retrain + PSI + CLV en place, mais gate biaisé et CLV mal défini |
| Tests & qualité | 11/20 | +7 | 40 tests utiles ; CI absente du dépôt et sur une version Python incompatible |

---

## 1. Problèmes critiques (P0)

### P0-1. Historique de logs absent du dépôt : risque de train/serve skew sur le VPS
- `.gitignore` exclut `nhl/data/gamelogs/mp_gamelogs.parquet` (2008-2024) et `nhl/stats/` (dont `skaters_all.csv`, 2,6 Go, sa seule source via `nhl/data/gamelog_moneypuck.py`).
- `FeatureEngine.refresh()` (`nhl/core/inference.py`) appelle `load_all_gamelogs()`, qui prend ce qu'il trouve. Sans le parquet MoneyPuck, il ne charge que `nhlapi_2025` et `nhlapi_2026`, **sans erreur ni warning**.
- Conséquences si le fichier manque sur le VPS :
  - `car_hours`, `car_g60`, `car_a60`, `car_sog60` et `sh_pct_shrunk` sont calculés sur une saison au lieu d'une carrière. Les vétérans ressemblent à des recrues et la distribution sort de celle de l'entraînement.
  - Le retrain hebdomadaire (`--live`) s'entraîne sur environ 2 saisons au lieu de 17.
- **Fix** : au chargement, vérifier `logs.gameDate.min() <= 2009-10-01` et refuser de servir sinon (alerte Telegram). Documenter comment le parquet arrive sur le VPS : copie manuelle, stockage objet, ou git LFS (7 Mo, versionnable).

### P0-2. Gate du retrain hebdomadaire biaisé : le modèle ne sera jamais remplacé
`nhl/scripts/train_models.py` :
- Le nouveau modèle est entraîné sur `date <= max − 45 j`, puis évalué sur les 45 derniers jours.
- Le modèle en place (`_current_model_logloss`) est évalué sur **le même holdout**, alors qu'il a été entraîné sur toutes les données jusqu'à son propre `train_cutoff`. Le modèle actuel a pour cutoff le 2026-04-16 : le holdout est **dans son échantillon d'entraînement**.
- Dès la semaine 2 de la saison, chaque retrain hebdomadaire compare donc un modèle hors échantillon à un modèle en échantillon. Le nouveau modèle perd presque toujours, et la prod reste figée sur un modèle de plus en plus ancien.
- **Fix** : comparer les deux modèles sur des données postérieures au `train_cutoff` des deux. Une option simple : ré-entraîner l'ancien recipe sur la même fenêtre `tr` (comparaison à recette égale), ou comparer sur les seuls matchs postérieurs à `cutoff_ancien`, avec un minimum de lignes. Logger le résultat du gate dans Telegram.

### P0-3. Cotes : events non filtrés par date (mélange de matchs, crédits gaspillés)
`shared/odds_api.py`, `OddsAPIClient.fetch_odds` :
- L'appel `/events` ne passe ni `commenceTimeFrom` ni `commenceTimeTo`. Il renvoie tous les matchs à venir (plusieurs jours).
- Tout event où joue une équipe ciblée est retenu. Si BOS joue ce soir et demain, les **deux** matchs sont interrogés.
- Pour un même joueur, les cotes des deux matchs sont fusionnées dans le même dict : `soft` reçoit les prix des deux matchs (la médiane mélange deux matchs), et `pin_yes`/`pin_no` sont écrasés par le dernier event lu.
- Effets : prix d'exécution et no-vig faux sur les back-to-back, et crédits consommés en double. Le snapshot CLV à T−5 (`log_closing_lines_for_match`) a le même défaut.
- **Fix** : filtrer par `commence_time` (fenêtre de la session NHL), ou mieux, faire correspondre l'event au `gameId` du match (équipes + date). Ajouter un test unitaire avec deux events pour la même équipe.

### P0-4. L'edge n'est pas démontré, et le marché passeur n'est pas simulé au prix de prod
Analyse refaite sur `nhl/reports/bets_p3.parquet` (= config actuelle, identique à `x_combo`) :

| Mesure | Valeur |
|---|---|
| Paris simulés (oct. 2023 → janv. 2025) | 208 (156 passeur, 52 buteur), 1,9 par soir |
| ROI total | +24,9 % (+45,9 U sur 184 U) |
| ROI en **test** (seule période jamais utilisée pour régler) | 38 paris, +14,1 U, dont **+16,8 U sur un seul pari buteur** (cote 7-15) |
| Passeur en test | 19 paris, −5,5 U |
| Gains attendus par Pinnacle no-vig (paris couverts) | 69,6 ; observés 87 (z ≈ +2,6) |
| Gains attendus par la proba finale du bot | 82,9 ; observés 87 (z ≈ +0,6) |
| EV moyenne vue par Pinnacle | −8,7 % |

Lecture :
- Le z = +2,6 contre Pinnacle vient surtout de la **validation 2023-24** (137 paris passeur). Cette période a servi à apprendre `w`, à choisir le modèle (`best_p1b`) et à adopter les pistes. Ce n'est pas une preuve hors échantillon.
- Le test est trop petit (38 paris) et dominé par un pari. Les pistes ont été adoptées sur « validation **et** test » (PISTES_AMELIORATION.md) : le test n'est donc plus vierge.
- En log-loss, le modèle bat légèrement Pinnacle sur toutes les lignes éligibles (but 0,5571 contre 0,5580 ; passe 0,6325 contre 0,6342). C'est le signal le plus fiable, mais l'écart est petit et ne garantit pas un edge **après** la marge FR.
- **Prix passeur de prod ≠ prix simulé.** D'après `odds_coverage_2026-10-04.md`, seul Pinnacle cote les passes. En prod, `apply_proxy` retombe sur `pin_yes × 0,90`, alors que la simulation utilisait `médiane soft × 0,94`. Avec `w_ast = 0,80`, un pari passeur exige en prod que le modèle dépasse Pinnacle d'environ **+24 % en probabilité relative** (calcul : EV ≥ 4 % à une cote `0,9 × pin_yes` avec une marge Pinnacle d'environ 3 %). Ce régime n'a jamais été simulé, et un tel désaccord avec le book le plus efficient est plus souvent une erreur du modèle qu'un edge (winner's curse).
- **Fix** : rejouer la simulation passeur avec `exec = pin_yes × pin_haircut` (même règle que la prod) avant toute mise. Ne plus utiliser la période de test pour adopter des pistes : définir un nouveau test, la saison 2025-26, dès que ses cotes sont collectées.

---

## 2. Problèmes majeurs (P1)

### 2.1 Écarts prod ↔ simulation (le backtest ne mesure pas exactement ce que fait le bot)
- **Passeurs « domicile seulement »** : `settings.toml` a `[thresholds.passeurs] home_only = true`, que `market_filter.evaluate_player_markets` applique en prod. La simulation (`sim/phases.py`, `p2_eligible`) le force à `false`. En prod, environ la moitié des candidats passeurs disparaît par rapport au backtest. **Fix** : mettre `home_only = false` dans le TOML (c'est ce qui a été simulé, et `is_home` est déjà une feature), ou simuler avec `true`.
- **Repli saison précédente** : `fetcher.fetch_all` complète `Player Season Totals.csv` avec la saison `fallback_season_id` pour les joueurs absents de la saison en cours. Un joueur qui n'a pas encore joué cette saison passe donc le filtre `GP >= 10` avec ses GP de l'an dernier. En simulation, `std_gp` vaut 0 et il est exclu. Le garde-fou « pas de pari avant 10 matchs », jugé indispensable par PISTES §2, fuit en prod. **Fix** : en prod, exiger `std_gp >= 10` calculé sur les logs de la saison en cours (déjà disponible dans `build_features`).
- **Bankroll et exposition** : la simulation mise sur 100 U fixes avec une exposition de départ nulle chaque jour. La prod utilise `Portfolio.get_balance()` et `get_pending_exposure()`, qui inclut des paris jamais résolus (voir 2.4). Écart acceptable, mais à garder en tête.

### 2.2 Mesure du marché
- **Dévig multiplicatif** (`odds_api.py`, `build_odds_table.py`) : il répartit la marge proportionnellement. Sur des props à 15-35 %, la marge est en pratique plus concentrée sur le longshot (biais favori-longshot) : le no-vig multiplicatif **surestime** la probabilité du « Oui ». Comparer avec les méthodes *power* et *Shin* sur l'historique (critère : log-loss du no-vig), et garder la meilleure.
- **Pinnacle sans côté « Non »** sur 63 % des cotes buteur : dans ce cas, `p_novig` est absent, le blend retombe sur `p_model` seul, et l'EV exigée passe à 9 %. C'est sain, mais le bot parie alors sur le modèle sans référence. Envisager un no-vig estimé à partir du « Oui » seul et de la marge moyenne Pinnacle observée sur ce marché.
- **CLV mal défini** : à T−5, `closing_cote` est le **prix proxy** (médiane US × 0,94), alors que la cote prise (`/pris`) est une cote FR réelle. `cote_prise / closing_cote − 1` mélange deux marchés, et le biais dépend de la décote supposée. **Fix** : KPI principal = EV de clôture `closing_p_novig × cote_prise − 1`, déjà stockée. Garder le CLV « prix » uniquement entre prix de même source.

### 2.3 Modélisation (`nhl/core/ensemble_model.py`, `TemporalCalibratedGBM`)
- Les 15 % de données les plus récentes ne servent **jamais** à entraîner les arbres, seulement à calibrer. Ce sont pourtant les plus informatives. Alternative standard : après calibration, ré-entraîner les arbres sur 100 % des données avec le même nombre d'itérations et garder l'isotonique. Le léger biais introduit est à mesurer en walk-forward.
- Les poids de blending et l'isotonique sont ajustés **sur le même bloc** : `calib_logloss_` est optimiste. Le facteur ×200 dans `exp(-(ll − ll_min) × 200)` est arbitraire.
- L'isotonique produit des paliers : plusieurs joueurs reçoivent exactement la même probabilité. C'est acceptable, mais vérifier la résolution dans la plage jouée (p de 0,15 à 0,50).
- `params` n'est appliqué qu'à LightGBM : les surcharges `xgb` et `cat` sont ignorées en silence.
- Pas de features de **marché** ni de contexte d'équipe pré-match : total de buts implicite du match (cotes h2h/totals, que les books FR cotent), gardien partant confirmé, rang de ligne réel. L'audit précédent l'avait déjà relevé. PISTES §3 conclut à raison que le modèle est limité par l'**information**, pas par ses hyperparamètres.

### 2.4 Résolution des paris et portefeuille
- `updater.update_pending_picks` ne gère pas les **joueurs non alignés** (scratch, blessure à l'échauffement). Le joueur est absent du boxscore, donc le pick n'est jamais résolu, la date est re-interrogée chaque nuit pour toujours, et un pari pris via `/pris` reste en « exposition en attente » à vie. Cela réduit progressivement le plafond journalier de 30 U. **Fix** : match `OFF`/`FINAL` + joueur absent = `void` (mise rendue).
- `Portfolio.get_daily_pnl` filtre sur la date d'**enregistrement** du pari et utilise `datetime.now()` (fuseau système), pas `paris_now()`. Un gain à 0 (void) est compté comme une perte.

### 2.5 Inférence : écarts mineurs de parité
- En début de saison, `FeatureEngine.predict` ne charge, pour les saisons passées, que les lignes des joueurs du soir (`season == courante | playerId in pids`). Les agrégats d'équipe glissants sur 10 matchs (`team_gf_l10`, `opp_ga_l10`, `opp_sa_l10`) qui débordent sur la saison précédente sont alors calculés sur des effectifs partiels. L'impact est faible tant que le filtre de 10 matchs joués tient (voir 2.1). **Fix** : charger les deux dernières saisons complètes.
- `pp_rank`, `toi_rank` et `toi_rank_pos` sont des rangs parmi les joueurs du match. À l'entraînement : ceux qui ont joué (environ 18). En prod : l'effectif du dernier match plus les joueurs RotoWire (souvent 19 à 22). Les rangs des tops ne bougent pas, mais ceux du bas de l'effectif sont légèrement décalés.

### 2.6 Monitoring de dérive (`nhl/core/monitoring.py`)
- Le profil de référence couvre **tous** les joueurs des 365 derniers jours (4e lignes et défenseurs compris pour la passe). Les vecteurs servis ne concernent que les candidats filtrés (ATOI ≥ 13, GP ≥ 10, alignés). Les distributions diffèrent par construction, ce qui produira des alertes PSI **faux positifs** permanentes, que l'on finira par ignorer. **Fix** : construire le profil sur la population éligible (même filtre que la prod).

---

## 3. Qualité logicielle, MLOps et coûts

- **CI inexistante en pratique** : `.github/` est dans `.gitignore`, donc `.github/workflows/tests.yml` n'est pas versionné et ne tourne jamais sur GitHub. Il cible de plus Python 3.10, alors que `nhl/config/settings.py` utilise `tomllib` (3.11+) : les tests échoueraient à l'import. **Fix** : retirer `.github/` du `.gitignore`, passer en Python 3.12, déclencher aussi sur `test`.
- **Import bare restant** : `nhl/core/updater.py:10` utilise `from  core.database import get_connection`, ce qui crée un second module `core.database` distinct de `nhl.core.database`. Ça ne fonctionne que via le `sys.path` de `main_bot.py` et ça casse dans les scripts et les tests.
- **`shared/` dépend de `nhl/`** : `shared/kelly.py` importe `nhl.config.settings`, et `shared/odds_api.fetch_nhl_odds` importe la config et les constantes NHL. La couche partagée n'est plus multi-sport. Déplacer `fetch_nhl_odds` dans `nhl/` et passer les paramètres explicitement.
- **Code mort à supprimer**, source de confusion pour les humains comme pour les agents :
  - `NHLEnsembleClassifier`, `market_filter.prepare_features_for_player`, `load_ml_models` et `get_adaptive_ev_threshold` ;
  - `shared/kelly.py` et `nhl/core/kelly.py`, utilisés seulement par la phase `baseline` de la simulation et par `NhlBot._calculate_quarter_kelly` ;
  - `train_production_models.py`, `ensemble_*.joblib`, `xg_model_*.pkl`, `lr_model_ast.pkl` et `historical_dataset.parquet`, tous versionnés ;
  - les sections `[thresholds.buteurs]`, `[thresholds.pointeurs]` et `[kelly]` « OMEGA » du TOML, dont seuls `home_only` et `atoi_min` sont lus ;
  - les colonnes de `logger_csv` (`ixg`, `hdcf`, `prior_*`, `opp_xga_60`) qui loggent des stats CSV héritées n'ayant plus rien à voir avec le modèle ;
  - `get_roi_stats("parlays")` alors que les combinés ne sont plus construits.
- **Pré-filtre hérité** : la sélection des candidats repose encore sur les CSV de l'ancien pipeline (`last 10.csv`, `Player Season Totals.csv`, `ds.form_data`), alors que le modèle utilise les logs de match. Il y a deux sources de vérité pour « qui est éligible ». À terme, filtrer directement sur les features (`toi_l10`, `std_gp`, `position`).
- **Quota The Odds API** : la docstring parle de 500 requêtes par mois. Chaque appel `/events/{id}/odds` coûte (marchés × régions), soit 2 crédits par marché avec `eu,us`, donc 4 crédits par match et par scan. Estimation pour une soirée de 8 matchs : environ 32 crédits pour les vagues, plus environ 32 pour les snapshots CLV, doublés par le bug P0-3 sur les back-to-back. Cela fait **2 000 à 4 000 crédits par mois**. Vérifier l'abonnement. Si les FR ne cotent pas les props, la région `eu` est inutile pour ces marchés : passer `regions="us"` et couvrir Pinnacle via `bookmakers=pinnacle,...`.
- **Push git depuis le bot** (`end_of_day_cleanup` → `dashboard/exporter.git_commit_and_push`) : le process de prod écrit dans le dépôt que le watchdog `git reset --hard` (`vps/watchdog.py`). Un conflit ou un reset concurrent peut perdre l'export ou bloquer le pull. Sortir l'export du dépôt de code (branche `gh-pages` séparée ou stockage objet).
- **Exceptions avalées** : `updater.py` (`except: continue` sur le boxscore) et `ensemble_model._load_optimal_params` (`except Exception: pass`) sont contraires à la convention du projet.

---

## 4. Ce qui est bien

- **Parité train/serve réelle** : `nhl/core/features.py` est l'unique constructeur de features. La prod ajoute des lignes « match à venir » et passe par la même fonction. Des tests de parité existent, `shift(1)` est systématique, les moyennes de ligue sont « à date » (la fuite d'une moyenne de saison complète a été repérée et corrigée), et les priors de saison précédente sont propres.
- **Schéma de logs unique** MoneyPuck / API NHL, avec une parité mesurée de 99,98 à 100 %.
- **Modèle honnête** : pas de repondération, isotonique sur un bloc temporel hors entraînement, `features_version` vérifiée avant de servir, métadonnées complètes (`data_hash`, `feature_profile`, `train_cutoff`).
- **Stratégie de mise propre et partagée** : un seul `select_bets` utilisé par la prod et la simulation, shrinkage vers le no-vig Pinnacle avec `w` appris en log-loss (et non en ROI), Kelly fractionné sans plancher, plafonds par match pour les paris corrélés.
- **Hygiène statistique visible** : IC bootstrap par journée, rejet explicite des pistes sur-apprises (P2 grille : +33 % en validation, −57 % en test), « edge Pinnacle » rapporté à côté du ROI, et une lecture honnête dans les rapports.
- **Mode proxy + cote seuil** : il gère proprement l'absence de books FR. `/pris` enregistre la cote réelle, ce qui permettra de calibrer la décote (`calibrate_proxy.py`).
- **Ops** : kill-switch paper, déduplication persistée, index unique SQLite, scan de secours toutes les 15 min, snapshot par match à T−5, alertes de crash et de quota, `paris_now()` indépendant du fuseau du VPS.

---

## 5. Feuille de route priorisée

### P0 : avant toute mise réelle (1 à 2 jours)
1. Vérifier sur le VPS la présence de `mp_gamelogs.parquet` ; ajouter le garde-fou « historique complet sinon pas de service » (P0-1).
2. Corriger le gate du retrain : comparaison sur des données postérieures aux deux cutoffs (P0-2).
3. Filtrer les events The Odds API par date et équipes du match ; ajouter un test back-to-back (P0-3).
4. Aligner `home_only` passeur entre le TOML et la simulation ; exiger `std_gp >= 10` depuis les logs (2.1).
5. Résolution `void` des joueurs non alignés (2.4).

### P1 : rendre la mesure fiable (1 à 2 semaines)
6. Rejouer la simulation passeur au prix de prod `pin_yes × 0,90` ; si le ROI ou l'edge Pinnacle s'effondre, désactiver le marché passeur en prod (P0-4).
7. Comparer les dévig multiplicatif, power et Shin sur l'historique ; adopter le meilleur en log-loss (2.2).
8. KPI principal en paper : EV de clôture contre Pinnacle (`closing_p_novig × cote_prise − 1`), avec IC ; seuil de passage en réel fixé **à l'avance** (par exemple 300 paris, borne basse de l'IC à 95 % > 0) (2.2).
9. Geler une nouvelle période de test (saison 2025-26, cotes à collecter) et ne plus adopter de piste sur l'ancien test.
10. Profil PSI sur la population éligible (2.6).

### P2 : gagner de l'information (2 à 4 semaines)
11. Features de marché : total implicite du match et ligne de l'équipe (h2h/totals, cotés par les FR), gardien partant confirmé, rang de ligne RotoWire.
12. Entraîner les arbres sur 100 % des données après calibration (à valider en walk-forward) ; appliquer `params` aux trois algos.
13. Collecter les cotes points et tirs cadrés en journalisation (PISTES §4).

### P3 : dette technique
14. CI versionnée en Python 3.12 ; corriger l'import bare d'`updater.py`.
15. Supprimer le code et les modèles morts (§3) ; sortir `fetch_nhl_odds` de `shared/`.
16. Sortir le push du dashboard du process bot ; corriger les `except` silencieux.

---

## 6. Annexe : vérifications effectuées

| Vérification | Résultat |
|---|---|
| `pytest tests/` | 40 tests passés (2,5 s) |
| Modèles servis (`ml_model_{but,ast}.pkl`) | `temporal_calibrated_gbm[lgbm+xgb+cat]`, `features_version p1-2026-10`, cutoff 2026-04-16 ; AUC holdout 0,662 (but) / 0,677 (ast) |
| Log-loss modèle vs Pinnacle, lignes éligibles cotées (walk-forward `p1b_ens`) | but 0,5571 vs 0,5580 (20 615 lignes) ; ast 0,6325 vs 0,6342 (11 715 lignes) |
| `bets_p3.parquet` vs `bets_x_combo.parquet` | identiques (la config de prod = combo) |
| Fichiers suivis par git | `.github/` absent ; `mp_gamelogs.parquet`, `*_all.csv` et `nhl/models/live/` ignorés |
| Branche déployée par le watchdog | `GIT_BRANCH` (défaut `main`), avec `git reset --hard` |

Fichiers lus en priorité :
- `nhl/core/` : `features.py`, `inference.py`, `ensemble_model.py`, `betting.py`, `bot_logic.py`, `market_filter.py`, `services.py`, `updater.py`, `logger_csv.py`, `monitoring.py` ;
- `nhl/scripts/` : `train_models.py`, `simulate_roi.py`, `build_odds_table.py` ;
- `nhl/sim/phases.py`, `nhl/data/gamelog_nhlapi.py`, `nhl/data/fetcher.py`, `nhl/config/settings.toml` ;
- `shared/` : `odds_api.py`, `portfolio.py`, `kelly.py`, `utils.py`.
