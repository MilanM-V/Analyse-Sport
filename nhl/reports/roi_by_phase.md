# ROI simulé par phase

Généré par `nhl/scripts/simulate_roi.py`. Une section par exécution.

## Phase `baseline` — 2026-10-03 23:58 (retrain quarterly, 8 min)

Pipeline actuel : features MoneyPuck (xG inclus, défenseurs dans le train), ensemble XGB/LGBM/CatBoost (scale_pos_weight + sigmoid), filtres de prod (bug ailiers L/R inclus), cote_min 4,5 / 2,5, EV adaptatif, Kelly 1/8 plancher 0,5 U, exposition 15 U/jour. ⚠️ Optimiste vs la prod réelle : le backtest voit le xG MoneyPuck que la prod n'a pas.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 10 | 5.0 | -5.0 | **-100.0%** | [-100 ; -100] | +1.1% | +30.0% | 0.5560 | 0.5547 | 0.6079 | 0.6103 | 0.0172 |
| but | test | 35 | 18.5 | +6.1 | **+33.1%** | [-44 ; +109] | -8.9% | +40.0% | 0.5580 | 0.5548 | 0.5851 | 0.5957 | 0.0175 |
| but | all | 45 | 23.5 | +1.1 | **+4.8%** | [-58 ; +72] | -7.1% | +37.8% | 0.5567 | 0.5547 | 0.6007 | 0.6055 | 0.0113 |
| ast | val | 84 | 48.5 | -3.1 | **-6.5%** | [-41 ; +27] | -13.3% | +94.0% | 0.6391 | 0.6361 | 0.6135 | 0.6176 | 0.0179 |
| ast | test | 94 | 63.0 | -0.8 | **-1.3%** | [-34 ; +34] | -14.3% | +93.6% | 0.6333 | 0.6308 | 0.5940 | 0.6049 | 0.0204 |
| ast | all | 178 | 111.5 | -4.0 | **-3.6%** | [-29 ; +22] | -13.8% | +93.8% | 0.6371 | 0.6342 | 0.6070 | 0.6134 | 0.0168 |
| total | val | 94 | 53.5 | -8.1 | **-15.2%** | [-46 ; +17] | -12.8% | +87.2% | — | — | — | — | — |
| total | test | 129 | 81.5 | +5.3 | **+6.5%** | [-23 ; +38] | -13.5% | +79.1% | — | — | — | — | — |
| total | all | 223 | 135.0 | -2.8 | **-2.1%** | [-23 ; +21] | -13.2% | +82.5% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = -2.1% (223 paris), soft_median = -1.0% (689 paris), soft_max = +13.3% (1781 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 164 | 104.0 | +3.5 | +3.4% |
| ast | (3.5, 4.5] | 13 | 7.0 | -7.0 | -100.0% |
| ast | (4.5, 6.0] | 1 | 0.5 | -0.5 | -100.0% |
| but | (4.5, 6.0] | 26 | 14.0 | -6.3 | -44.9% |
| but | (6.0, 10.0] | 19 | 9.5 | +7.4 | +78.1% |

## Phase `p0` — 2026-10-03 23:59 (retrain quarterly, 0 min)

P0 : ailiers L/R réintégrés au marché buteur (market_filter), dédoublonnage des picks, mode paper, crash `dt` corrigé. Même modèle que la baseline (prédictions réutilisées).

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 25 | 13.0 | -7.2 | **-55.5%** | [-100 ; +17] | -1.4% | +24.0% | 0.5601 | 0.5574 | 0.5958 | 0.6039 | 0.0121 |
| but | test | 85 | 46.5 | +23.4 | **+50.4%** | [-21 ; +141] | -5.1% | +44.7% | 0.5622 | 0.5594 | 0.5765 | 0.5880 | 0.0157 |
| but | all | 110 | 59.5 | +16.2 | **+27.3%** | [-29 ; +100] | -4.6% | +40.0% | 0.5608 | 0.5580 | 0.5895 | 0.5987 | 0.0111 |
| ast | val | 84 | 48.5 | -3.1 | **-6.5%** | [-41 ; +27] | -13.3% | +94.0% | 0.6391 | 0.6361 | 0.6135 | 0.6176 | 0.0179 |
| ast | test | 94 | 63.0 | -0.8 | **-1.3%** | [-34 ; +34] | -14.3% | +93.6% | 0.6333 | 0.6308 | 0.5940 | 0.6049 | 0.0204 |
| ast | all | 178 | 111.5 | -4.0 | **-3.6%** | [-29 ; +22] | -13.8% | +93.8% | 0.6371 | 0.6342 | 0.6070 | 0.6134 | 0.0168 |
| total | val | 109 | 61.5 | -10.3 | **-16.8%** | [-47 ; +15] | -12.5% | +78.0% | — | — | — | — | — |
| total | test | 179 | 109.5 | +22.6 | **+20.6%** | [-16 ; +63] | -11.5% | +70.4% | — | — | — | — | — |
| total | all | 288 | 171.0 | +12.3 | **+7.2%** | [-18 ; +37] | -11.9% | +73.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +7.2% (288 paris), soft_median = -0.4% (872 paris), soft_max = +9.1% (2623 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 164 | 104.0 | +3.5 | +3.4% |
| ast | (3.5, 4.5] | 13 | 7.0 | -7.0 | -100.0% |
| ast | (4.5, 6.0] | 1 | 0.5 | -0.5 | -100.0% |
| but | (4.5, 6.0] | 77 | 42.0 | -11.6 | -27.7% |
| but | (6.0, 10.0] | 32 | 16.0 | +11.0 | +68.9% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `p1a` — 2026-10-04 00:25 (retrain quarterly, 18 min)

P1a : features construites par nhl/core/features.py à partir de stats identiques MoneyPuck / API NHL (plus de xG en cours de saison ; xG seulement en prior de saison précédente), clé playerId, saison 2025-26 ajoutée via l'API NHL, priors de saison issus des *_all.csv, défenseurs exclus du train buteur, données depuis 2009. Modèle identique à la baseline pour isoler l'effet des données.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 13 | 6.5 | -3.9 | **-60.2%** | [-100 ; -3] | -2.4% | +30.8% | 0.5582 | 0.5574 | 0.6029 | 0.6039 | 0.0147 |
| but | test | 11 | 6.0 | +8.8 | **+146.0%** | [-100 ; +503] | +21.7% | +54.5% | 0.5591 | 0.5594 | 0.5883 | 0.5880 | 0.0126 |
| but | all | 24 | 12.5 | +4.8 | **+38.7%** | [-100 ; +235] | +12.0% | +41.7% | 0.5585 | 0.5580 | 0.5980 | 0.5987 | 0.0123 |
| ast | val | 49 | 26.0 | +2.9 | **+11.3%** | [-38 ; +61] | -12.4% | +98.0% | 0.6368 | 0.6361 | 0.6212 | 0.6176 | 0.0194 |
| ast | test | 18 | 9.0 | +0.5 | **+5.5%** | [-64 ; +70] | -14.6% | +94.4% | 0.6310 | 0.6308 | 0.6032 | 0.6049 | 0.0174 |
| ast | all | 67 | 35.0 | +3.4 | **+9.8%** | [-32 ; +50] | -13.0% | +97.0% | 0.6347 | 0.6342 | 0.6152 | 0.6134 | 0.0129 |
| total | val | 62 | 32.5 | -1.0 | **-3.0%** | [-48 ; +39] | -11.6% | +83.9% | — | — | — | — | — |
| total | test | 29 | 15.0 | +9.3 | **+61.7%** | [-60 ; +225] | -5.2% | +79.3% | — | — | — | — | — |
| total | all | 91 | 47.5 | +8.3 | **+17.4%** | [-31 ; +79] | -9.6% | +82.4% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +17.4% (91 paris), soft_median = +15.2% (406 paris), soft_max = +18.4% (2292 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 62 | 32.5 | +4.1 | +12.6% |
| ast | (3.5, 4.5] | 5 | 2.5 | -0.7 | -26.7% |
| but | (4.5, 6.0] | 13 | 6.5 | -1.4 | -21.2% |
| but | (6.0, 10.0] | 10 | 5.0 | -5.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `p1b_lgbm` — 2026-10-04 00:27 (retrain quarterly, 2 min)

P1b : features P1a + modèle TemporalCalibratedGBM('lgbm',) — scale_pos_weight=1, calibration isotonique sur les 15 % de lignes les plus récentes (hors apprentissage). Sélection du modèle sur la log-loss de VALIDATION (2023-24), pas sur le ROI.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 7 | 4.0 | -4.0 | **-100.0%** | [-100 ; -100] | -7.6% | +42.9% | 0.5571 | 0.5574 | 0.6058 | 0.6039 | 0.0116 |
| but | test | 13 | 7.0 | +10.2 | **+145.4%** | [-100 ; +367] | +42.5% | +23.1% | 0.5585 | 0.5594 | 0.5924 | 0.5880 | 0.0162 |
| but | all | 20 | 11.0 | +6.2 | **+56.2%** | [-100 ; +245] | +17.5% | +30.0% | 0.5576 | 0.5580 | 0.6010 | 0.5987 | 0.0117 |
| ast | val | 88 | 54.5 | +6.6 | **+12.2%** | [-21 ; +45] | -13.1% | +96.6% | 0.6335 | 0.6361 | 0.6235 | 0.6176 | 0.0171 |
| ast | test | 17 | 10.5 | -7.8 | **-74.2%** | [-100 ; -31] | -13.1% | +100.0% | 0.6310 | 0.6308 | 0.6040 | 0.6049 | 0.0273 |
| ast | all | 105 | 65.0 | -1.1 | **-1.8%** | [-32 ; +28] | -13.1% | +97.1% | 0.6326 | 0.6342 | 0.6165 | 0.6134 | 0.0094 |
| total | val | 95 | 58.5 | +2.6 | **+4.5%** | [-27 ; +35] | -13.0% | +92.6% | — | — | — | — | — |
| total | test | 30 | 17.5 | +2.4 | **+13.7%** | [-82 ; +147] | -4.7% | +66.7% | — | — | — | — | — |
| total | all | 125 | 76.0 | +5.0 | **+6.6%** | [-29 ; +47] | -11.4% | +86.4% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +6.6% (125 paris), soft_median = +8.9% (495 paris), soft_max = +21.0% (1899 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 101 | 63.0 | -2.7 | -4.2% |
| ast | (3.5, 4.5] | 4 | 2.0 | +1.5 | +76.2% |
| but | (4.5, 6.0] | 11 | 6.0 | -1.0 | -17.4% |
| but | (6.0, 10.0] | 8 | 4.0 | -4.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `p1b_ens` — 2026-10-04 00:34 (retrain quarterly, 7 min)

P1b : features P1a + modèle TemporalCalibratedGBM('lgbm', 'xgb', 'cat') — scale_pos_weight=1, calibration isotonique sur les 15 % de lignes les plus récentes (hors apprentissage). Sélection du modèle sur la log-loss de VALIDATION (2023-24), pas sur le ROI.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 2 | 1.0 | -1.0 | **-100.0%** | [-100 ; -100] | -10.0% | +50.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 9 | 5.0 | +14.4 | **+287.8%** | [-40 ; +648] | +150.1% | +11.1% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 11 | 6.0 | +13.4 | **+223.1%** | [-100 ; +580] | +70.0% | +18.2% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 76 | 45.5 | +3.2 | **+7.0%** | [-28 ; +43] | -12.9% | +97.4% | 0.6333 | 0.6361 | 0.6238 | 0.6176 | 0.0246 |
| ast | test | 12 | 7.5 | -3.4 | **-45.3%** | [-100 ; +29] | -12.6% | +100.0% | 0.6310 | 0.6308 | 0.6035 | 0.6049 | 0.0195 |
| ast | all | 88 | 53.0 | -0.2 | **-0.4%** | [-33 ; +33] | -12.9% | +97.7% | 0.6325 | 0.6342 | 0.6165 | 0.6134 | 0.0132 |
| total | val | 78 | 46.5 | +2.2 | **+4.7%** | [-28 ; +41] | -12.9% | +96.2% | — | — | — | — | — |
| total | test | 21 | 12.5 | +11.0 | **+87.9%** | [-65 ; +294] | -0.1% | +61.9% | — | — | — | — | — |
| total | all | 99 | 59.0 | +13.2 | **+22.3%** | [-22 ; +78] | -11.0% | +88.9% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +22.3% (99 paris), soft_median = +17.1% (408 paris), soft_max = +24.1% (1679 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 85 | 51.5 | -0.5 | -0.9% |
| ast | (3.5, 4.5] | 3 | 1.5 | +0.3 | +17.5% |
| but | (4.5, 6.0] | 3 | 1.5 | +1.2 | +80.2% |
| but | (6.0, 10.0] | 7 | 3.5 | +1.0 | +27.6% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `p2` — 2026-10-04 00:37 (retrain quarterly, 0 min)

P2 : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('ast',), cotes but [1.5, 25.0], ast [1.5, 3.5], seuils EV 0.08/0.05/0.1, majoration sans Pinnacle 9.0, Kelly 0.125 sans plancher, plafond 3.0 U/match. Réglages choisis sur 2023-24 uniquement.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 0 | 0.0 | +0.0 | **—** | — | — | — | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 0 | 0.0 | +0.0 | **—** | — | — | — | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 0 | 0.0 | +0.0 | **—** | — | — | — | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 94 | 71.0 | +23.4 | **+32.9%** | [+7 ; +59] | -10.6% | +100.0% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 14 | 9.0 | -5.1 | **-57.0%** | [-100 ; +5] | -10.5% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 108 | 80.0 | +18.2 | **+22.8%** | [-0 ; +48] | -10.6% | +100.0% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 94 | 71.0 | +23.4 | **+32.9%** | [+7 ; +59] | -10.6% | +100.0% | — | — | — | — | — |
| total | test | 14 | 9.0 | -5.1 | **-57.0%** | [-100 ; +5] | -10.5% | +100.0% | — | — | — | — | — |
| total | all | 108 | 80.0 | +18.2 | **+22.8%** | [-0 ; +48] | -10.6% | +100.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +22.8% (108 paris), soft_median = +12.5% (516 paris), soft_max = +10.1% (898 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 8 | 13.5 | +6.7 | +49.5% |
| ast | (2.0, 2.5] | 48 | 36.0 | +4.8 | +13.2% |
| ast | (2.5, 3.5] | 52 | 30.5 | +6.8 | +22.2% |

## Phase `p2_apriori` — 2026-10-04 00:39 (retrain quarterly, 0 min)

P2 [a priori : w appris en log-loss, seuils standards] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 19 | 14.0 | +5.4 | **+38.5%** | [-23 ; +107] | -6.8% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 13 | 10.0 | +11.7 | **+116.9%** | [-56 ; +366] | +21.2% | +46.2% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 32 | 24.0 | +17.1 | **+71.2%** | [-12 ; +186] | -0.1% | +78.1% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 110 | 84.5 | +19.2 | **+22.8%** | [-1 ; +46] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 9.5 | -5.6 | **-59.3%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 125 | 94.0 | +13.6 | **+14.5%** | [-8 ; +37] | -10.7% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 129 | 98.5 | +24.6 | **+25.0%** | [+2 ; +48] | -10.1% | +96.9% | — | — | — | — | — |
| total | test | 28 | 19.5 | +6.1 | **+31.1%** | [-64 ; +175] | -1.4% | +75.0% | — | — | — | — | — |
| total | all | 157 | 118.0 | +30.7 | **+26.0%** | [+0 ; +55] | -8.9% | +93.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +26.0% (157 paris), soft_median = +13.1% (830 paris), soft_max = +7.7% (3166 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 17 | 22.0 | +4.3 | +19.7% |
| ast | (2.0, 2.5] | 50 | 38.5 | +5.5 | +14.3% |
| ast | (2.5, 3.5] | 52 | 30.5 | +6.8 | +22.2% |
| ast | (3.5, 4.5] | 6 | 3.0 | -3.0 | -100.0% |
| but | (1.0, 2.0] | 4 | 5.0 | -3.2 | -63.3% |
| but | (2.0, 2.5] | 5 | 6.5 | +1.9 | +29.1% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (4.5, 6.0] | 2 | 1.0 | +1.7 | +170.2% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `p2_model` — 2026-10-04 00:39 (retrain quarterly, 0 min)

P2 [a priori : modèle seul (w=1)] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=1.00, ast=1.00), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 95 | 75.0 | +4.2 | **+5.7%** | [-22 ; +37] | -11.6% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 48 | 31.5 | +18.2 | **+57.6%** | [-9 ; +153] | -6.7% | +85.4% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 143 | 106.5 | +22.4 | **+21.0%** | [-8 ; +56] | -10.1% | +95.1% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 257 | 216.5 | +28.2 | **+13.0%** | [-2 ; +27] | -12.1% | +98.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 39 | 29.5 | -7.5 | **-25.6%** | [-57 ; +12] | -12.1% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 296 | 246.0 | +20.7 | **+8.4%** | [-5 ; +22] | -12.1% | +98.6% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 352 | 291.5 | +32.4 | **+11.1%** | [-2 ; +24] | -11.9% | +98.9% | — | — | — | — | — |
| total | test | 87 | 61.0 | +10.6 | **+17.4%** | [-21 ; +72] | -9.3% | +92.0% | — | — | — | — | — |
| total | all | 439 | 352.5 | +43.1 | **+12.2%** | [-1 ; +26] | -11.4% | +97.5% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +12.2% (439 paris), soft_median = +8.6% (1508 paris), soft_max = +9.1% (3277 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 36 | 50.0 | +2.8 | +5.7% |
| ast | (2.0, 2.5] | 122 | 107.0 | +10.9 | +10.2% |
| ast | (2.5, 3.5] | 126 | 83.0 | +7.3 | +8.8% |
| ast | (3.5, 4.5] | 12 | 6.0 | -0.4 | -6.0% |
| but | (1.0, 2.0] | 23 | 31.0 | -3.2 | -10.3% |
| but | (2.0, 2.5] | 31 | 25.5 | -0.9 | -3.7% |
| but | (2.5, 3.5] | 43 | 26.0 | +8.0 | +30.8% |
| but | (3.5, 4.5] | 38 | 19.5 | +8.1 | +41.7% |
| but | (4.5, 6.0] | 4 | 2.0 | +0.7 | +35.1% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `p3` — 2026-10-04 00:40 (retrain quarterly, 0 min)

P3 : stratégie lue dans settings.toml [betting] (code de prod final, après P3). Les chiffres doivent être identiques à `p2_apriori`.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 19 | 14.0 | +5.4 | **+38.5%** | [-23 ; +107] | -6.8% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 13 | 10.0 | +11.7 | **+116.9%** | [-56 ; +366] | +21.2% | +46.2% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 32 | 24.0 | +17.1 | **+71.2%** | [-12 ; +186] | -0.1% | +78.1% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 110 | 84.5 | +19.2 | **+22.8%** | [-1 ; +46] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 9.5 | -5.6 | **-59.3%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 125 | 94.0 | +13.6 | **+14.5%** | [-8 ; +37] | -10.7% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 129 | 98.5 | +24.6 | **+25.0%** | [+2 ; +48] | -10.1% | +96.9% | — | — | — | — | — |
| total | test | 28 | 19.5 | +6.1 | **+31.1%** | [-64 ; +175] | -1.4% | +75.0% | — | — | — | — | — |
| total | all | 157 | 118.0 | +30.7 | **+26.0%** | [+0 ; +55] | -8.9% | +93.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +26.0% (157 paris), soft_median = +13.1% (830 paris), soft_max = +7.7% (3166 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 17 | 22.0 | +4.3 | +19.7% |
| ast | (2.0, 2.5] | 50 | 38.5 | +5.5 | +14.3% |
| ast | (2.5, 3.5] | 52 | 30.5 | +6.8 | +22.2% |
| ast | (3.5, 4.5] | 6 | 3.0 | -3.0 | -100.0% |
| but | (1.0, 2.0] | 4 | 5.0 | -3.2 | -63.3% |
| but | (2.0, 2.5] | 5 | 6.5 | +1.9 | +29.1% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (4.5, 6.0] | 2 | 1.0 | +1.7 | +170.2% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_ev3` — 2026-10-04 01:04 (retrain quarterly, 1 min)

P2 [piste B : EV ≥ 3 %] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.03/0.03/0.03, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 30 | 19.5 | +5.4 | **+27.5%** | [-22 ; +80] | -8.8% | +96.7% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 15 | 11.0 | +10.7 | **+97.2%** | [-56 ; +326] | +13.8% | +53.3% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 45 | 30.5 | +16.1 | **+52.6%** | [-13 ; +146] | -3.9% | +82.2% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 173 | 118.0 | +21.5 | **+18.2%** | [-1 ; +37] | -11.0% | +97.1% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 22 | 13.0 | -4.3 | **-32.8%** | [-73 ; +16] | -11.0% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 195 | 131.0 | +17.2 | **+13.1%** | [-4 ; +31] | -11.0% | +97.4% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 203 | 137.5 | +26.8 | **+19.5%** | [+2 ; +38] | -10.6% | +97.0% | — | — | — | — | — |
| total | test | 37 | 24.0 | +6.4 | **+26.8%** | [-51 ; +141] | -4.4% | +81.1% | — | — | — | — | — |
| total | all | 240 | 161.5 | +33.3 | **+20.6%** | [+0 ; +43] | -9.8% | +94.6% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +20.6% (240 paris), soft_median = +10.0% (1135 paris), soft_max = +8.0% (3458 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 31 | 30.5 | +5.2 | +16.9% |
| ast | (2.0, 2.5] | 88 | 58.0 | +7.6 | +13.1% |
| ast | (2.5, 3.5] | 70 | 39.5 | +7.4 | +18.8% |
| ast | (3.5, 4.5] | 6 | 3.0 | -3.0 | -100.0% |
| but | (1.0, 2.0] | 10 | 8.0 | -4.2 | -53.0% |
| but | (2.0, 2.5] | 10 | 9.0 | +0.6 | +6.8% |
| but | (2.5, 3.5] | 9 | 5.0 | +3.1 | +61.7% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (4.5, 6.0] | 3 | 1.5 | +3.5 | +235.3% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_ev4` — 2026-10-04 01:05 (retrain quarterly, 1 min)

P2 [piste B : EV ≥ 4 %] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.04/0.04/0.04, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 24 | 16.5 | +6.2 | **+37.4%** | [-16 ; +98] | -7.9% | +95.8% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 14 | 10.5 | +11.2 | **+106.6%** | [-52 ; +352] | +17.0% | +50.0% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 38 | 27.0 | +17.4 | **+64.3%** | [-7 ; +163] | -2.1% | +78.9% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 133 | 97.5 | +19.8 | **+20.3%** | [-1 ; +40] | -10.7% | +96.2% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 11.5 | -4.1 | **-35.4%** | [-75 ; +14] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 152 | 109.0 | +15.7 | **+14.4%** | [-6 ; +35] | -10.7% | +96.7% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 157 | 114.0 | +26.0 | **+22.8%** | [+4 ; +42] | -10.3% | +96.2% | — | — | — | — | — |
| total | test | 33 | 22.0 | +7.1 | **+32.3%** | [-51 ; +161] | -3.2% | +78.8% | — | — | — | — | — |
| total | all | 190 | 136.0 | +33.1 | **+24.3%** | [+2 ; +51] | -9.2% | +93.2% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.3% (190 paris), soft_median = +11.6% (989 paris), soft_max = +8.1% (3337 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 25.5 | +4.3 | +17.0% |
| ast | (2.0, 2.5] | 62 | 45.0 | +8.3 | +18.4% |
| ast | (2.5, 3.5] | 62 | 35.5 | +6.1 | +17.2% |
| ast | (3.5, 4.5] | 6 | 3.0 | -3.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 6.5 | -3.7 | -57.0% |
| but | (2.0, 2.5] | 7 | 7.5 | +0.9 | +11.9% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (4.5, 6.0] | 3 | 1.5 | +3.5 | +235.3% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_ev8` — 2026-10-04 01:06 (retrain quarterly, 1 min)

P2 [piste B : EV ≥ 8 %] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.08/0.08/0.08, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 6 | 5.0 | +5.9 | **+118.5%** | [+16 ; +234] | -5.0% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 8 | 7.5 | +9.8 | **+131.2%** | [-76 ; +493] | +31.6% | +50.0% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 14 | 12.5 | +15.8 | **+126.2%** | [-13 ; +336] | +9.7% | +71.4% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 47 | 47.0 | +15.3 | **+32.5%** | [-1 ; +63] | -10.1% | +95.7% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 6 | 4.5 | -3.1 | **-69.2%** | [-100 ; +4] | -9.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 53 | 51.5 | +12.2 | **+23.6%** | [-9 ; +56] | -10.0% | +96.2% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 53 | 52.0 | +21.2 | **+40.8%** | [+8 ; +71] | -9.5% | +96.2% | — | — | — | — | — |
| total | test | 14 | 12.0 | +6.7 | **+56.1%** | [-84 ; +286] | +6.9% | +71.4% | — | — | — | — | — |
| total | all | 67 | 64.0 | +27.9 | **+43.6%** | [+0 ; +94] | -6.8% | +91.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +43.6% (67 paris), soft_median = +18.4% (416 paris), soft_max = +10.1% (2331 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 8 | 13.5 | +6.7 | +49.5% |
| ast | (2.0, 2.5] | 22 | 22.0 | +1.8 | +8.4% |
| ast | (2.5, 3.5] | 21 | 15.0 | +4.6 | +30.9% |
| ast | (3.5, 4.5] | 2 | 1.0 | -1.0 | -100.0% |
| but | (1.0, 2.0] | 1 | 1.5 | -1.5 | -100.0% |
| but | (2.0, 2.5] | 4 | 5.5 | +2.9 | +52.5% |
| but | (2.5, 3.5] | 2 | 1.5 | +0.2 | +12.8% |
| but | (3.5, 4.5] | 4 | 2.0 | +4.0 | +198.4% |
| but | (6.0, 10.0] | 2 | 1.0 | -1.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_kelly6` — 2026-10-04 01:06 (retrain quarterly, 1 min)

P2 [piste C : Kelly 1/6] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.05, Kelly 0.16666666666666666 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 25 | 18.5 | +1.9 | **+10.5%** | [-43 ; +68] | -5.9% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 15 | 12.0 | +19.6 | **+163.0%** | [-32 ; +444] | +19.0% | +46.7% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 40 | 30.5 | +21.5 | **+70.5%** | [-20 ; +196] | -0.5% | +80.0% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 109 | 110.0 | +26.4 | **+24.0%** | [+0 ; +47] | -10.8% | +96.3% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 13.5 | -7.1 | **-52.6%** | [-100 ; +5] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 124 | 123.5 | +19.3 | **+15.7%** | [-7 ; +39] | -10.8% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 134 | 128.5 | +28.4 | **+22.1%** | [+0 ; +44] | -9.9% | +97.0% | — | — | — | — | — |
| total | test | 30 | 25.5 | +12.5 | **+48.9%** | [-56 ; +215] | -1.1% | +73.3% | — | — | — | — | — |
| total | all | 164 | 154.0 | +40.8 | **+26.5%** | [+0 ; +56] | -8.6% | +92.7% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +26.5% (164 paris), soft_median = +14.7% (856 paris), soft_max = +7.4% (3088 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 16 | 25.5 | +4.1 | +16.2% |
| ast | (2.0, 2.5] | 50 | 54.0 | +6.9 | +12.7% |
| ast | (2.5, 3.5] | 52 | 40.5 | +11.8 | +29.2% |
| ast | (3.5, 4.5] | 6 | 3.5 | -3.5 | -100.0% |
| but | (1.0, 2.0] | 4 | 5.0 | -3.2 | -63.3% |
| but | (2.0, 2.5] | 5 | 7.0 | +2.4 | +35.0% |
| but | (2.5, 3.5] | 8 | 5.5 | +2.6 | +47.0% |
| but | (3.5, 4.5] | 14 | 7.5 | +4.1 | +54.8% |
| but | (4.5, 6.0] | 4 | 2.0 | +0.7 | +35.1% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_kelly4` — 2026-10-04 01:07 (retrain quarterly, 1 min)

P2 [piste C : Kelly 1/4] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.05, Kelly 0.25 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 27 | 23.0 | +5.4 | **+23.5%** | [-36 ; +83] | -5.3% | +96.3% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 17 | 15.5 | +24.1 | **+155.2%** | [-22 ; +389] | +19.0% | +41.2% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 44 | 38.5 | +29.5 | **+76.5%** | [-3 ; +181] | -0.2% | +75.0% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 109 | 145.0 | +34.0 | **+23.4%** | [+1 ; +45] | -10.8% | +96.3% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 20.5 | -11.6 | **-56.7%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 124 | 165.5 | +22.4 | **+13.5%** | [-8 ; +37] | -10.8% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 136 | 168.0 | +39.4 | **+23.5%** | [+2 ; +46] | -9.7% | +96.3% | — | — | — | — | — |
| total | test | 32 | 36.0 | +12.4 | **+34.5%** | [-51 ; +161] | -1.1% | +68.8% | — | — | — | — | — |
| total | all | 168 | 204.0 | +51.8 | **+25.4%** | [+2 ; +52] | -8.5% | +91.1% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +25.4% (168 paris), soft_median = +14.2% (837 paris), soft_max = +9.1% (2717 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 16 | 28.5 | +3.9 | +13.6% |
| ast | (2.0, 2.5] | 50 | 73.0 | +6.4 | +8.8% |
| ast | (2.5, 3.5] | 52 | 60.0 | +16.0 | +26.7% |
| ast | (3.5, 4.5] | 6 | 4.0 | -4.0 | -100.0% |
| but | (1.0, 2.0] | 4 | 6.0 | -3.2 | -54.2% |
| but | (2.0, 2.5] | 5 | 7.5 | +1.9 | +26.0% |
| but | (2.5, 3.5] | 8 | 7.0 | +5.7 | +81.3% |
| but | (3.5, 4.5] | 14 | 9.5 | +8.1 | +85.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +0.2 | +8.1% |
| but | (6.0, 10.0] | 7 | 4.5 | -0.0 | -0.8% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_caps_wide` — 2026-10-04 01:08 (retrain quarterly, 1 min)

P2 [piste H : plafonds 5 U/match, 30 U/jour] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.05, Kelly 0.125 sans plancher, plafond 5.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 19 | 14.0 | +5.4 | **+38.5%** | [-23 ; +107] | -6.8% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 13 | 10.0 | +11.7 | **+116.9%** | [-56 ; +366] | +21.2% | +46.2% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 32 | 24.0 | +17.1 | **+71.2%** | [-12 ; +186] | -0.1% | +78.1% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 113 | 86.5 | +21.2 | **+24.5%** | [+2 ; +47] | -10.8% | +96.5% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 9.5 | -5.6 | **-59.3%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 128 | 96.0 | +15.5 | **+16.2%** | [-6 ; +38] | -10.8% | +96.9% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 132 | 100.5 | +26.6 | **+26.4%** | [+4 ; +48] | -10.2% | +97.0% | — | — | — | — | — |
| total | test | 28 | 19.5 | +6.1 | **+31.1%** | [-64 ; +175] | -1.4% | +75.0% | — | — | — | — | — |
| total | all | 160 | 120.0 | +32.6 | **+27.2%** | [+2 ; +56] | -9.0% | +93.1% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +27.2% (160 paris), soft_median = +13.7% (848 paris), soft_max = +7.9% (3726 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 17 | 22.5 | +4.8 | +21.4% |
| ast | (2.0, 2.5] | 51 | 39.0 | +6.2 | +15.8% |
| ast | (2.5, 3.5] | 53 | 31.0 | +6.3 | +20.3% |
| ast | (3.5, 4.5] | 7 | 3.5 | -1.7 | -49.6% |
| but | (1.0, 2.0] | 4 | 5.0 | -3.2 | -63.3% |
| but | (2.0, 2.5] | 5 | 6.5 | +1.9 | +29.1% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (4.5, 6.0] | 2 | 1.0 | +1.7 | +170.2% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_nopin_off` — 2026-10-04 01:09 (retrain quarterly, 1 min)

P2 [piste B' : aucun pari sans référence Pinnacle] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 9.0, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 19 | 14.0 | +5.4 | **+38.5%** | [-23 ; +107] | -6.8% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 6 | 5.5 | +11.6 | **+211.1%** | [-67 ; +634] | +21.2% | +100.0% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 25 | 19.5 | +17.0 | **+87.2%** | [-5 ; +231] | -0.1% | +100.0% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 106 | 79.5 | +21.0 | **+26.4%** | [+3 ; +50] | -10.7% | +100.0% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 9.5 | -5.6 | **-59.3%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 121 | 89.0 | +15.4 | **+17.3%** | [-5 ; +40] | -10.7% | +100.0% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 125 | 93.5 | +26.4 | **+28.2%** | [+5 ; +52] | -10.1% | +100.0% | — | — | — | — | — |
| total | test | 21 | 15.0 | +6.0 | **+39.8%** | [-73 ; +231] | -1.4% | +100.0% | — | — | — | — | — |
| total | all | 146 | 108.5 | +32.4 | **+29.8%** | [+2 ; +61] | -8.9% | +100.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +29.8% (146 paris), soft_median = +10.7% (790 paris), soft_max = +6.1% (2887 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 16 | 20.0 | +6.3 | +31.7% |
| ast | (2.0, 2.5] | 48 | 36.0 | +4.8 | +13.2% |
| ast | (2.5, 3.5] | 52 | 30.5 | +6.8 | +22.2% |
| ast | (3.5, 4.5] | 5 | 2.5 | -2.5 | -100.0% |
| but | (1.0, 2.0] | 3 | 3.5 | -1.7 | -47.6% |
| but | (2.0, 2.5] | 5 | 6.5 | +1.9 | +29.1% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 8 | 4.0 | +2.0 | +49.2% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_nopin_10` — 2026-10-04 01:09 (retrain quarterly, 1 min)

P2 [piste B' : +10 % d'EV exigée sans Pinnacle] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.05/0.05/0.05, majoration sans Pinnacle 0.1, Kelly 0.125 sans plancher, plafond 3.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 19 | 14.0 | +5.4 | **+38.5%** | [-23 ; +107] | -6.8% | +100.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 10 | 8.5 | +10.5 | **+123.4%** | [-73 ; +433] | +21.2% | +60.0% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 29 | 22.5 | +15.9 | **+70.6%** | [-13 ; +185] | -0.1% | +86.2% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 106 | 79.5 | +21.0 | **+26.4%** | [+3 ; +50] | -10.7% | +100.0% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 15 | 9.5 | -5.6 | **-59.3%** | [-100 ; -4] | -10.4% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 121 | 89.0 | +15.4 | **+17.3%** | [-5 ; +40] | -10.7% | +100.0% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 125 | 93.5 | +26.4 | **+28.2%** | [+5 ; +52] | -10.1% | +100.0% | — | — | — | — | — |
| total | test | 25 | 18.0 | +4.9 | **+27.0%** | [-71 ; +191] | -1.4% | +84.0% | — | — | — | — | — |
| total | all | 150 | 111.5 | +31.2 | **+28.0%** | [+1 ; +58] | -8.9% | +97.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +28.0% (150 paris), soft_median = +11.8% (811 paris), soft_max = +8.2% (3108 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 16 | 20.0 | +6.3 | +31.7% |
| ast | (2.0, 2.5] | 48 | 36.0 | +4.8 | +13.2% |
| ast | (2.5, 3.5] | 52 | 30.5 | +6.8 | +22.2% |
| ast | (3.5, 4.5] | 5 | 2.5 | -2.5 | -100.0% |
| but | (1.0, 2.0] | 4 | 5.0 | -3.2 | -63.3% |
| but | (2.0, 2.5] | 5 | 6.5 | +1.9 | +29.1% |
| but | (2.5, 3.5] | 8 | 4.5 | +3.6 | +79.6% |
| but | (3.5, 4.5] | 9 | 4.5 | +3.3 | +74.4% |
| but | (6.0, 10.0] | 2 | 1.0 | -1.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.0 | +11.2 | +1122.0% |

## Phase `x_combo` — 2026-10-04 01:11 (retrain quarterly, 1 min)

P2 [combo : EV ≥ 4 % + Kelly 1/6 + plafonds 5 U/match, 30 U/jour] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.04/0.04/0.04, majoration sans Pinnacle 0.05, Kelly 0.16666666666666666 sans plancher, plafond 5.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 137 | 131.0 | +28.6 | **+21.9%** | [+1 ; +43] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 15.5 | -5.5 | **-35.7%** | [-77 ; +16] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 156 | 146.5 | +23.1 | **+15.8%** | [-4 ; +35] | -10.6% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 170 | 154.5 | +31.8 | **+20.6%** | [+1 ; +38] | -9.9% | +96.5% | — | — | — | — | — |
| total | test | 38 | 29.5 | +14.0 | **+47.6%** | [-44 ; +183] | -2.4% | +78.9% | — | — | — | — | — |
| total | all | 208 | 184.0 | +45.9 | **+24.9%** | [+2 ; +52] | -8.7% | +93.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.9% (208 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4543 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 34.0 | +6.6 | +19.4% |
| ast | (2.0, 2.5] | 62 | 61.5 | +10.9 | +17.7% |
| ast | (2.5, 3.5] | 63 | 46.0 | +10.7 | +23.2% |
| ast | (3.5, 4.5] | 9 | 5.0 | -5.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `p1b_ens` — 2026-10-04 01:21 (retrain monthly, 21 min)

P1b : features P1a + modèle TemporalCalibratedGBM('lgbm', 'xgb', 'cat') — scale_pos_weight=1, calibration isotonique sur les 15 % de lignes les plus récentes (hors apprentissage). Sélection du modèle sur la log-loss de VALIDATION (2023-24), pas sur le ROI.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 2 | 1.0 | -1.0 | **-100.0%** | [-100 ; -100] | -5.9% | +100.0% | 0.5566 | 0.5574 | 0.6069 | 0.6039 | 0.0089 |
| but | test | 8 | 4.0 | +4.8 | **+120.3%** | [-100 ; +323] | +69.6% | +25.0% | 0.5585 | 0.5594 | 0.5921 | 0.5880 | 0.0159 |
| but | all | 10 | 5.0 | +3.8 | **+76.2%** | [-100 ; +270] | +31.8% | +40.0% | 0.5573 | 0.5580 | 0.6018 | 0.5987 | 0.0111 |
| ast | val | 66 | 41.5 | +3.5 | **+8.5%** | [-33 ; +52] | -13.3% | +98.5% | 0.6342 | 0.6361 | 0.6220 | 0.6176 | 0.0263 |
| ast | test | 11 | 6.5 | -5.1 | **-78.7%** | [-100 ; -31] | -13.8% | +100.0% | 0.6309 | 0.6308 | 0.6037 | 0.6049 | 0.0185 |
| ast | all | 77 | 48.0 | -1.6 | **-3.3%** | [-39 ; +36] | -13.4% | +98.7% | 0.6331 | 0.6342 | 0.6157 | 0.6134 | 0.0152 |
| total | val | 68 | 42.5 | +2.5 | **+5.9%** | [-35 ; +50] | -13.1% | +98.5% | — | — | — | — | — |
| total | test | 19 | 10.5 | -0.3 | **-2.9%** | [-100 ; +117] | -1.0% | +68.4% | — | — | — | — | — |
| total | all | 87 | 53.0 | +2.2 | **+4.2%** | [-34 ; +47] | -11.1% | +92.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +4.2% (87 paris), soft_median = +5.9% (343 paris), soft_max = +24.0% (1483 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (2.5, 3.5] | 74 | 46.5 | -3.6 | -7.8% |
| ast | (3.5, 4.5] | 3 | 1.5 | +2.0 | +135.0% |
| but | (4.5, 6.0] | 7 | 3.5 | -0.8 | -22.8% |
| but | (6.0, 10.0] | 2 | 1.0 | -1.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 0.5 | +5.6 | +1122.0% |

## Phase `p3` — 2026-10-04 01:22 (retrain quarterly, 1 min)

P3 : stratégie lue dans settings.toml [betting] (code de prod final, après P3). Les chiffres doivent être identiques à `p2_apriori`.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 137 | 131.0 | +28.6 | **+21.9%** | [+1 ; +43] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 15.5 | -5.5 | **-35.7%** | [-77 ; +16] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 156 | 146.5 | +23.1 | **+15.8%** | [-4 ; +35] | -10.6% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 170 | 154.5 | +31.8 | **+20.6%** | [+1 ; +38] | -9.9% | +96.5% | — | — | — | — | — |
| total | test | 38 | 29.5 | +14.0 | **+47.6%** | [-44 ; +183] | -2.4% | +78.9% | — | — | — | — | — |
| total | all | 208 | 184.0 | +45.9 | **+24.9%** | [+2 ; +52] | -8.7% | +93.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.9% (208 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4545 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 34.0 | +6.6 | +19.4% |
| ast | (2.0, 2.5] | 62 | 61.5 | +10.9 | +17.7% |
| ast | (2.5, 3.5] | 63 | 46.0 | +10.7 | +23.2% |
| ast | (3.5, 4.5] | 9 | 5.0 | -5.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_base_lgbm` — 2026-10-04 01:23 (retrain quarterly, 8 min)

Piste modèle [référence LGBM] — features `base`, algos ('lgbm',), tuning=False, stratégie = config actuelle.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 44 | 32.5 | +11.2 | **+34.3%** | [-12 ; +76] | -6.8% | +81.8% | 0.5571 | 0.5574 | 0.6058 | 0.6039 | 0.0116 |
| but | test | 31 | 20.5 | +23.4 | **+114.4%** | [-7 ; +281] | +4.3% | +58.1% | 0.5585 | 0.5594 | 0.5924 | 0.5880 | 0.0162 |
| but | all | 75 | 53.0 | +34.6 | **+65.3%** | [+8 ; +137] | -3.1% | +72.0% | 0.5576 | 0.5580 | 0.6010 | 0.5987 | 0.0117 |
| ast | val | 153 | 149.5 | +43.3 | **+29.0%** | [+10 ; +47] | -11.2% | +96.1% | 0.6278 | 0.6300 | 0.6157 | 0.6120 | 0.0100 |
| ast | test | 26 | 20.0 | -8.6 | **-43.0%** | [-75 ; -3] | -11.6% | +96.2% | 0.6230 | 0.6234 | 0.6128 | 0.6117 | 0.0113 |
| ast | all | 179 | 169.5 | +34.7 | **+20.5%** | [+3 ; +37] | -11.3% | +96.1% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0074 |
| total | val | 197 | 182.0 | +54.5 | **+29.9%** | [+14 ; +45] | -10.3% | +92.9% | — | — | — | — | — |
| total | test | 57 | 40.5 | +14.8 | **+36.6%** | [-37 ; +135] | -4.9% | +75.4% | — | — | — | — | — |
| total | all | 254 | 222.5 | +69.3 | **+31.2%** | [+11 ; +51] | -9.3% | +89.0% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +31.2% (254 paris), soft_median = +8.0% (1242 paris), soft_max = +6.9% (4876 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 27 | 42.5 | +11.8 | +27.7% |
| ast | (2.0, 2.5] | 62 | 61.5 | +9.1 | +14.9% |
| ast | (2.5, 3.5] | 81 | 61.0 | +14.6 | +23.9% |
| ast | (3.5, 4.5] | 9 | 4.5 | -0.8 | -17.5% |
| but | (1.0, 2.0] | 5 | 7.0 | -1.8 | -25.7% |
| but | (2.0, 2.5] | 8 | 10.5 | +7.3 | +69.8% |
| but | (2.5, 3.5] | 15 | 8.5 | +6.9 | +81.4% |
| but | (3.5, 4.5] | 28 | 16.0 | +9.9 | +61.7% |
| but | (4.5, 6.0] | 9 | 4.5 | +0.5 | +10.2% |
| but | (6.0, 10.0] | 9 | 5.0 | -5.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_monthly` — 2026-10-04 01:23 (retrain quarterly, 1 min)

P2 [piste D : retrain mensuel + config actuelle] : prédictions de `p1b_ens` (meilleure log-loss de validation) + nhl/core/betting.py — mélange modèle/Pinnacle (w but=0.65, ast=0.80), marchés ('but', 'ast'), cotes but [1.5, 15.0], ast [1.5, 6.0], seuils EV 0.04/0.04/0.04, majoration sans Pinnacle 0.05, Kelly 0.1667 sans plancher, plafond 5.0 U/match.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 21 | 11.5 | -1.4 | **-12.3%** | [-70 ; +57] | -3.5% | +95.2% | 0.5566 | 0.5574 | 0.6069 | 0.6039 | 0.0089 |
| but | test | 35 | 32.5 | +18.4 | **+56.6%** | [-31 ; +170] | -1.4% | +68.6% | 0.5585 | 0.5594 | 0.5921 | 0.5880 | 0.0159 |
| but | all | 56 | 44.0 | +17.0 | **+38.6%** | [-29 ; +124] | -2.3% | +78.6% | 0.5573 | 0.5580 | 0.6018 | 0.5987 | 0.0111 |
| ast | val | 148 | 130.0 | +24.3 | **+18.7%** | [-1 ; +39] | -10.7% | +97.3% | 0.6279 | 0.6300 | 0.6156 | 0.6120 | 0.0125 |
| ast | test | 21 | 16.0 | -7.0 | **-43.5%** | [-84 ; +5] | -11.4% | +100.0% | 0.6229 | 0.6234 | 0.6127 | 0.6117 | 0.0122 |
| ast | all | 169 | 146.0 | +17.3 | **+11.9%** | [-6 ; +30] | -10.8% | +97.6% | 0.6262 | 0.6277 | 0.6146 | 0.6121 | 0.0114 |
| total | val | 169 | 141.5 | +22.9 | **+16.2%** | [-3 ; +35] | -9.9% | +97.0% | — | — | — | — | — |
| total | test | 56 | 48.5 | +11.4 | **+23.6%** | [-38 ; +100] | -6.0% | +80.4% | — | — | — | — | — |
| total | all | 225 | 190.0 | +34.3 | **+18.1%** | [-4 ; +43] | -9.0% | +92.9% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +18.1% (225 paris), soft_median = +12.1% (1009 paris), soft_max = +4.6% (4331 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 25 | 35.5 | +14.2 | +39.9% |
| ast | (2.0, 2.5] | 66 | 58.5 | +5.5 | +9.4% |
| ast | (2.5, 3.5] | 69 | 47.0 | +0.9 | +1.9% |
| ast | (3.5, 4.5] | 9 | 5.0 | -3.2 | -64.8% |
| but | (1.0, 2.0] | 9 | 11.0 | -1.4 | -12.5% |
| but | (2.0, 2.5] | 9 | 11.0 | -3.6 | -32.7% |
| but | (2.5, 3.5] | 7 | 4.0 | +2.7 | +66.8% |
| but | (3.5, 4.5] | 19 | 10.5 | +3.0 | +28.9% |
| but | (4.5, 6.0] | 8 | 4.5 | +0.9 | +20.1% |
| but | (6.0, 10.0] | 3 | 1.5 | -1.5 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_feat_lgbm` — 2026-10-04 01:30 (retrain quarterly, 7 min)

Piste modèle [piste F : features V2] — features `v2`, algos ('lgbm',), tuning=False, stratégie = config actuelle.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 32 | 24.0 | +1.4 | **+5.9%** | [-37 ; +58] | -4.3% | +84.4% | 0.5570 | 0.5574 | 0.6062 | 0.6039 | 0.0117 |
| but | test | 29 | 20.5 | +13.7 | **+66.7%** | [-53 ; +255] | +1.9% | +86.2% | 0.5587 | 0.5594 | 0.5917 | 0.5880 | 0.0179 |
| but | all | 61 | 44.5 | +15.1 | **+33.9%** | [-28 ; +131] | -1.3% | +85.2% | 0.5576 | 0.5580 | 0.6012 | 0.5987 | 0.0123 |
| ast | val | 151 | 138.0 | +22.5 | **+16.3%** | [-4 ; +36] | -11.2% | +97.4% | 0.6286 | 0.6300 | 0.6140 | 0.6120 | 0.0094 |
| ast | test | 26 | 22.0 | -4.7 | **-21.3%** | [-73 ; +35] | -11.8% | +96.2% | 0.6234 | 0.6234 | 0.6111 | 0.6117 | 0.0119 |
| ast | all | 177 | 160.0 | +17.8 | **+11.1%** | [-7 ; +31] | -11.3% | +97.2% | 0.6268 | 0.6277 | 0.6131 | 0.6121 | 0.0053 |
| total | val | 183 | 162.0 | +23.9 | **+14.8%** | [-4 ; +32] | -10.1% | +95.1% | — | — | — | — | — |
| total | test | 55 | 42.5 | +9.0 | **+21.1%** | [-42 ; +119] | -5.0% | +90.9% | — | — | — | — | — |
| total | all | 238 | 204.5 | +32.9 | **+16.1%** | [-6 ; +40] | -9.0% | +94.1% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +16.1% (238 paris), soft_median = +9.6% (1209 paris), soft_max = +4.1% (4817 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 30.5 | +11.0 | +36.0% |
| ast | (2.0, 2.5] | 65 | 70.5 | -1.2 | -1.7% |
| ast | (2.5, 3.5] | 80 | 52.5 | +12.8 | +24.3% |
| ast | (3.5, 4.5] | 10 | 6.5 | -4.7 | -72.9% |
| but | (1.0, 2.0] | 9 | 12.5 | +2.6 | +21.2% |
| but | (2.0, 2.5] | 4 | 4.5 | -3.4 | -76.0% |
| but | (2.5, 3.5] | 11 | 8.0 | +3.2 | +40.0% |
| but | (3.5, 4.5] | 28 | 14.0 | -0.2 | -1.2% |
| but | (4.5, 6.0] | 2 | 1.0 | -1.0 | -100.0% |
| but | (6.0, 10.0] | 6 | 3.0 | -3.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `x_tuned_lgbm` — 2026-10-04 01:40 (retrain quarterly, 3 min)

Piste modèle [piste E : LGBM tuné Optuna] — features `base`, algos ('lgbm',), tuning=True, stratégie = config actuelle.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 41 | 35.5 | -0.8 | **-2.3%** | [-40 ; +43] | -6.9% | +87.8% | 0.5571 | 0.5574 | 0.6070 | 0.6039 | 0.0136 |
| but | test | 20 | 13.0 | +25.1 | **+192.8%** | [-5 ; +443] | +9.0% | +75.0% | 0.5591 | 0.5594 | 0.5900 | 0.5880 | 0.0138 |
| but | all | 61 | 48.5 | +24.3 | **+50.0%** | [-12 ; +144] | -2.2% | +83.6% | 0.5578 | 0.5580 | 0.6012 | 0.5987 | 0.0124 |
| ast | val | 141 | 128.5 | +39.0 | **+30.4%** | [+8 ; +53] | -11.2% | +96.5% | 0.6280 | 0.6300 | 0.6150 | 0.6120 | 0.0080 |
| ast | test | 26 | 16.5 | -1.9 | **-11.6%** | [-53 ; +42] | -12.1% | +100.0% | 0.6231 | 0.6234 | 0.6120 | 0.6117 | 0.0185 |
| ast | all | 167 | 145.0 | +37.1 | **+25.6%** | [+5 ; +46] | -11.3% | +97.0% | 0.6263 | 0.6277 | 0.6140 | 0.6121 | 0.0062 |
| total | val | 182 | 164.0 | +38.2 | **+23.3%** | [+3 ; +44] | -10.3% | +94.5% | — | — | — | — | — |
| total | test | 46 | 29.5 | +23.2 | **+78.5%** | [-15 ; +211] | -4.3% | +89.1% | — | — | — | — | — |
| total | all | 228 | 193.5 | +61.4 | **+31.7%** | [+8 ; +59] | -9.1% | +93.4% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +31.7% (228 paris), soft_median = +8.5% (1115 paris), soft_max = +3.9% (4806 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 19 | 28.0 | +6.7 | +23.9% |
| ast | (2.0, 2.5] | 68 | 63.0 | +11.7 | +18.6% |
| ast | (2.5, 3.5] | 77 | 52.5 | +20.2 | +38.5% |
| ast | (3.5, 4.5] | 3 | 1.5 | -1.5 | -100.0% |
| but | (1.0, 2.0] | 11 | 15.5 | -3.0 | -19.1% |
| but | (2.0, 2.5] | 4 | 5.5 | -0.1 | -1.3% |
| but | (2.5, 3.5] | 12 | 8.0 | +1.5 | +18.5% |
| but | (3.5, 4.5] | 26 | 14.5 | +7.1 | +48.8% |
| but | (4.5, 6.0] | 3 | 1.5 | +3.9 | +260.3% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `p3` — 2026-10-04 02:08 (retrain quarterly, 0 min)

P3 : stratégie lue dans settings.toml [betting] (code de prod final, après P3). Les chiffres doivent être identiques à `p2_apriori`.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 137 | 131.0 | +28.6 | **+21.9%** | [+1 ; +43] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 15.5 | -5.5 | **-35.7%** | [-77 ; +16] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 156 | 146.5 | +23.1 | **+15.8%** | [-4 ; +35] | -10.6% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 170 | 154.5 | +31.8 | **+20.6%** | [+1 ; +38] | -9.9% | +96.5% | — | — | — | — | — |
| total | test | 38 | 29.5 | +14.0 | **+47.6%** | [-44 ; +183] | -2.4% | +78.9% | — | — | — | — | — |
| total | all | 208 | 184.0 | +45.9 | **+24.9%** | [+2 ; +52] | -8.7% | +93.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.9% (208 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4545 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 34.0 | +6.6 | +19.4% |
| ast | (2.0, 2.5] | 62 | 61.5 | +10.9 | +17.7% |
| ast | (2.5, 3.5] | 63 | 46.0 | +10.7 | +23.2% |
| ast | (3.5, 4.5] | 9 | 5.0 | -5.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `p3` — 2026-10-04 02:29 (retrain quarterly, 0 min)

P3 : stratégie lue dans settings.toml [betting] (code de prod final, après P3). Les chiffres doivent être identiques à `p2_apriori`.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 137 | 131.0 | +28.6 | **+21.9%** | [+1 ; +43] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 15.5 | -5.5 | **-35.7%** | [-77 ; +16] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 156 | 146.5 | +23.1 | **+15.8%** | [-4 ; +35] | -10.6% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 170 | 154.5 | +31.8 | **+20.6%** | [+1 ; +38] | -9.9% | +96.5% | — | — | — | — | — |
| total | test | 38 | 29.5 | +14.0 | **+47.6%** | [-44 ; +183] | -2.4% | +78.9% | — | — | — | — | — |
| total | all | 208 | 184.0 | +45.9 | **+24.9%** | [+2 ; +52] | -8.7% | +93.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.9% (208 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4545 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 34.0 | +6.6 | +19.4% |
| ast | (2.0, 2.5] | 62 | 61.5 | +10.9 | +17.7% |
| ast | (2.5, 3.5] | 63 | 46.0 | +10.7 | +23.2% |
| ast | (3.5, 4.5] | 9 | 5.0 | -5.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `q_ref` — 2026-10-04 14:33 (retrain quarterly, 0 min)

[référence : config du 2026-10-04 telle que simulée] prédictions `p1b_ens`, prix médiane soft × 0,94, marchés ('but', 'ast'), w={'but': 0.65, 'ast': 0.8}, EV ≥ 0.04, Kelly 0.1667, plafonds 5.0/30.0 U.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 137 | 131.0 | +28.6 | **+21.9%** | [+1 ; +43] | -10.7% | +96.4% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 19 | 15.5 | -5.5 | **-35.7%** | [-77 ; +16] | -10.6% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 156 | 146.5 | +23.1 | **+15.8%** | [-4 ; +35] | -10.6% | +96.8% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 170 | 154.5 | +31.8 | **+20.6%** | [+1 ; +38] | -9.9% | +96.5% | — | — | — | — | — |
| total | test | 38 | 29.5 | +14.0 | **+47.6%** | [-44 ; +183] | -2.4% | +78.9% | — | — | — | — | — |
| total | all | 208 | 184.0 | +45.9 | **+24.9%** | [+2 ; +52] | -8.7% | +93.3% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +24.9% (208 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4545 paris), prod = +38.1% (94 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 22 | 34.0 | +6.6 | +19.4% |
| ast | (2.0, 2.5] | 62 | 61.5 | +10.9 | +17.7% |
| ast | (2.5, 3.5] | 63 | 46.0 | +10.7 | +23.2% |
| ast | (3.5, 4.5] | 9 | 5.0 | -5.0 | -100.0% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `q_prod` — 2026-10-04 14:33 (retrain quarterly, 0 min)

[prod réelle au 2026-10-04 : passeurs domicile seul, repli saison, prix prod] prédictions `p1b_ens`, prix PROD (passes = Pinnacle × pin_haircut), marchés ('but', 'ast'), w={'but': 0.65, 'ast': 0.8}, EV ≥ 0.04, Kelly 0.1667, plafonds 5.0/30.0 U.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5566 | 0.5573 | 0.6067 | 0.6038 | 0.0122 |
| but | test | 22 | 16.5 | +17.1 | **+103.5%** | [-48 ; +316] | +8.6% | +59.1% | 0.5591 | 0.5603 | 0.5936 | 0.5877 | 0.0112 |
| but | all | 55 | 40.0 | +20.3 | **+50.6%** | [-21 ; +147] | -2.2% | +81.8% | 0.5575 | 0.5583 | 0.6020 | 0.5984 | 0.0096 |
| ast | val | 35 | 34.5 | +4.0 | **+11.5%** | [-33 ; +54] | -15.8% | +100.0% | 0.6334 | 0.6360 | 0.6228 | 0.6169 | 0.0247 |
| ast | test | 3 | 2.0 | -0.7 | **-33.4%** | [-100 ; +166] | -16.6% | +100.0% | 0.6330 | 0.6321 | 0.6020 | 0.6046 | 0.0235 |
| ast | all | 38 | 36.5 | +3.3 | **+9.1%** | [-33 ; +48] | -15.8% | +100.0% | 0.6332 | 0.6347 | 0.6151 | 0.6127 | 0.0139 |
| total | val | 68 | 58.0 | +7.2 | **+12.3%** | [-23 ; +43] | -11.4% | +98.5% | — | — | — | — | — |
| total | test | 25 | 18.5 | +16.4 | **+88.7%** | [-47 ; +289] | +3.9% | +64.0% | — | — | — | — | — |
| total | all | 93 | 76.5 | +23.6 | **+30.8%** | [-13 ; +90] | -8.4% | +89.2% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +30.8% (93 paris), soft_median = +13.5% (877 paris), soft_max = +6.9% (4313 paris), prod = +30.8% (93 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 6 | 9.5 | -0.2 | -2.4% |
| ast | (2.0, 2.5] | 20 | 18.0 | +3.0 | +16.5% |
| ast | (2.5, 3.5] | 12 | 9.0 | +0.6 | +6.3% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 20 | 11.0 | +4.6 | +41.9% |
| but | (4.5, 6.0] | 7 | 4.0 | +1.0 | +25.7% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `q_p0` — 2026-10-04 14:40 (retrain quarterly, 0 min)

[après P0 : passeurs domicile+extérieur, GP saison depuis les logs, prix prod] prédictions `p1b_ens`, prix PROD (passes = Pinnacle × pin_haircut), marchés ('but', 'ast'), w={'but': 0.65, 'ast': 0.8}, EV ≥ 0.04, Kelly 0.1667, plafonds 5.0/30.0 U.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 33 | 23.5 | +3.2 | **+13.5%** | [-30 ; +63] | -6.6% | +97.0% | 0.5567 | 0.5574 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 19 | 14.0 | +19.6 | **+139.9%** | [-35 ; +385] | +11.9% | +57.9% | 0.5579 | 0.5594 | 0.5946 | 0.5880 | 0.0113 |
| but | all | 52 | 37.5 | +22.8 | **+60.7%** | [-10 ; +168] | -1.9% | +82.7% | 0.5571 | 0.5580 | 0.6026 | 0.5987 | 0.0096 |
| ast | val | 38 | 35.5 | +5.7 | **+16.0%** | [-26 ; +55] | -15.9% | +100.0% | 0.6277 | 0.6300 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 4 | 2.5 | +0.3 | **+13.4%** | [-100 ; +166] | -15.9% | +100.0% | 0.6230 | 0.6234 | 0.6119 | 0.6117 | 0.0164 |
| ast | all | 42 | 38.0 | +6.0 | **+15.8%** | [-24 ; +51] | -15.9% | +100.0% | 0.6261 | 0.6277 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 71 | 59.0 | +8.9 | **+15.0%** | [-16 ; +46] | -11.6% | +98.6% | — | — | — | — | — |
| total | test | 23 | 16.5 | +19.9 | **+120.7%** | [-28 ; +330] | +4.5% | +65.2% | — | — | — | — | — |
| total | all | 94 | 75.5 | +28.8 | **+38.1%** | [-4 ; +96] | -8.8% | +90.4% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +38.1% (94 paris), soft_median = +13.3% (1108 paris), soft_max = +7.3% (4545 paris), prod = +38.1% (94 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 5 | 8.0 | +1.3 | +15.9% |
| ast | (2.0, 2.5] | 20 | 18.0 | +3.0 | +16.5% |
| ast | (2.5, 3.5] | 17 | 12.0 | +1.8 | +14.7% |
| but | (1.0, 2.0] | 7 | 7.5 | -3.7 | -49.9% |
| but | (2.0, 2.5] | 7 | 8.0 | +1.4 | +18.1% |
| but | (2.5, 3.5] | 9 | 6.0 | +2.1 | +34.7% |
| but | (3.5, 4.5] | 19 | 10.0 | +5.6 | +56.0% |
| but | (4.5, 6.0] | 5 | 2.5 | +2.5 | +101.2% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |

## Phase `q_p1_devig` — 2026-10-04 14:42 (retrain quarterly, 0 min)

[P1 : no-vig Pinnacle de Shin (au lieu de multiplicatif) + w réappris] prédictions `p1b_ens`, prix PROD (passes = Pinnacle × pin_haircut), marchés ('but', 'ast'), w={'but': 0.5, 'ast': 0.75}, EV ≥ 0.04, Kelly 0.1667, plafonds 5.0/30.0 U.

Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.

| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| but | val | 5 | 3.5 | +3.6 | **+102.8%** | [-17 ; +264] | -10.2% | +80.0% | 0.5567 | 0.5568 | 0.6069 | 0.6039 | 0.0120 |
| but | test | 11 | 9.0 | +18.0 | **+199.5%** | [-64 ; +532] | +31.3% | +27.3% | 0.5579 | 0.5595 | 0.5946 | 0.5874 | 0.0113 |
| but | all | 16 | 12.5 | +21.6 | **+172.4%** | [-18 ; +437] | +7.6% | +43.8% | 0.5571 | 0.5577 | 0.6026 | 0.5985 | 0.0096 |
| ast | val | 25 | 19.5 | +5.6 | **+28.5%** | [-32 ; +75] | -18.6% | +100.0% | 0.6277 | 0.6294 | 0.6159 | 0.6120 | 0.0131 |
| ast | test | 1 | 1.0 | -1.0 | **-100.0%** | [-100 ; -100] | -17.9% | +100.0% | 0.6230 | 0.6228 | 0.6119 | 0.6118 | 0.0164 |
| ast | all | 26 | 20.5 | +4.6 | **+22.2%** | [-35 ; +68] | -18.6% | +100.0% | 0.6261 | 0.6271 | 0.6145 | 0.6121 | 0.0072 |
| total | val | 30 | 23.0 | +9.2 | **+39.8%** | [-13 ; +87] | -17.5% | +96.7% | — | — | — | — | — |
| total | test | 12 | 10.0 | +17.0 | **+169.5%** | [-66 ; +498] | +19.0% | +33.3% | — | — | — | — | — |
| total | all | 42 | 33.0 | +26.1 | **+79.1%** | [-5 ; +203] | -13.1% | +78.6% | — | — | — | — | — |

Sensibilité au prix d'exécution (ROI total, toute la période) : exec = +79.1% (42 paris), soft_median = +18.8% (701 paris), soft_max = +9.5% (2834 paris), prod = +79.1% (42 paris)

ROI par tranche de cote (exec) :

| Marché | Cote | Paris | Mise | Profit | ROI |
|---|---|---|---|---|---|
| ast | (1.0, 2.0] | 3 | 5.0 | +1.0 | +19.9% |
| ast | (2.0, 2.5] | 13 | 10.0 | +2.1 | +21.1% |
| ast | (2.5, 3.5] | 10 | 5.5 | +1.5 | +26.4% |
| but | (1.0, 2.0] | 1 | 1.5 | -1.5 | -100.0% |
| but | (2.0, 2.5] | 4 | 3.5 | +1.7 | +49.7% |
| but | (2.5, 3.5] | 2 | 1.5 | +0.2 | +12.8% |
| but | (3.5, 4.5] | 1 | 1.0 | +2.8 | +276.0% |
| but | (4.5, 6.0] | 3 | 1.5 | +3.5 | +235.3% |
| but | (6.0, 10.0] | 4 | 2.0 | -2.0 | -100.0% |
| but | (10.0, 100.0] | 1 | 1.5 | +16.8 | +1122.0% |
