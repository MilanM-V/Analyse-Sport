# Pistes pour dépasser Pinnacle : résultats des tests

*2026-10-07 · branche `test` · aucune modification du bot (ni code, ni modèle, ni TOML). Expériences en lecture seule sur les données du dépôt et les API publiques. Zéro crédit The Odds API consommé. Scripts : annexe A.*

Ce document répond à une question : **parmi toutes les pistes pour rendre le moteur NHL meilleur que Pinnacle, lesquelles tiennent face à un test ?** Chaque piste a été testée avec un protocole et une règle de décision fixés avant de lancer les calculs (§2). Le tableau du §1 sert à décider ce qu'on ajoute au bot.

---

## 0. En bref

1. **Le moteur actuel bat Pinnacle au buteur, de peu.** Le mélange de prod (modèle 0,65 / Pinnacle 0,35) fait −1,06 millinat par ligne [−2,09 ; −0,02] sur le contrôle 2024-25 et −0,37 sur la validation, avec le modèle entraîné comme en prod. Aux passes, l'avantage existe en 2023-24 et disparaît en 2024-25. Pinnacle est le book le plus sharp sur les props NHL : les books américains ne font pas mieux, et leur consensus non plus.
2. **Découverte majeure : le harnais de simulation ne calibre pas comme la prod (H17).** Les lignes d'entraînement n'y sont pas triées par date : le bloc de calibration « récent » est en fait un bloc de jeunes joueurs. Toutes les simulations passées (ROI, recherche de config, simulateur) portent donc sur un modèle meilleur que celui que sert le bot : environ 0,7 mnat de mieux au buteur. En paris, l'écart est énorme. Avec le modèle entraîné comme en prod, « buteur seul » rapporte **+1,1 U en validation et +8,9 U en contrôle**, au lieu de +46,6 et +17,1 U, et la config de prod +39,1 / +5,6 U au lieu de +120,9 / +1,6 U. Les projections affichées partout surestiment donc ce que le bot peut faire aujourd'hui. Bonne nouvelle : le schéma « accidentel » du harnais est meilleur et sans fuite. L'adopter en prod (après validation) est la piste la plus rentable du rapport.
3. **Aucune astuce de combinaison ne fait mieux que le mélange actuel.** Empilement logit, référence US dévigée pour les lignes sans Pinnacle, micro-structure du marché : tous ❌. Il ne faut rien changer à la formule de mélange.
4. **Aucune donnée nouvelle ne passe nettement le test sur le modèle de prod.** La plus prometteuse est le xG en saison, et plus précisément le xG produit sur la glace pendant les présences du joueur. Ajouté à LightGBM seul, il améliore nettement les **passes** (−1,08 mnat [−1,84 ; −0,30] en contrôle). Sur l'ensemble de prod, l'effet se réduit à −0,48 [−1,21 ; +0,20] (🟡). Rien au buteur. Il exigerait en plus les shift charts de l'API NHL.
5. **Les informations « évidentes » sont déjà dans le prix de Pinnacle** : gardien adverse titulaire, voyage et fatigue, arbitres, données de tracking NHL EDGE. Toutes ❌.
6. **Côté prix, la marche est haute.** La meilleure cote des 3 books FR vaut la cote Pinnacle « Oui », soit environ 11 % sous la cote juste : il faut que la vraie probabilité dépasse celle de Pinnacle de 8 à 30 % selon la cote pour être rentable (14 % aux cotes 2,5-3,5). On ne gagne que là où le modèle s'écarte franchement de Pinnacle, et c'est justement là qu'il a raison. Au buteur, sur les lignes où le modèle dépasse nettement Pinnacle (écart logit ≥ 0,3), la réussite bat Pinnacle dans les deux saisons : z 3,5 et 1,9 avec le modèle de prod, z 3,2 et 3,3 avec celui du harnais. Mais avec le modèle de prod, parier ces lignes ne rapporte presque rien en validation (+0,6 à +2,7 U), et un peu en contrôle (+6,7 à +7,7 U). « Buteur seul » reste positif sur les deux saisons, mais de peu (+1,1 / +8,9 U).
7. **Trois changements de modélisation prometteurs (🟡)**, qui améliorent nettement la validation et le contrôle sans significativité :
   - une calibration paramétrique (Platt ou bêta) à la place de l'isotonique, qui supprime aussi les paliers de probabilité (confirmé sur l'ensemble de prod) ;
   - un objectif Poisson au buteur ;
   - un réseau de neurones tabulaire ajouté à l'ensemble (−1,11 mnat en validation au buteur).
8. **Les books FR sont lents, mais pas assez pour être battus sur le seul timing.** Quand Pinnacle bouge de plus de 2 % entre l'aperçu et les picks confirmés, Unibet et Betclic ne suivent que dans 14 % et 23 % des cas (2 soirées). Pourtant, la cote restée figée était encore à −12 % de la cote juste en moyenne : la marge FR absorbe ces mouvements. Seuls de gros chocs (scratch, changement de gardien) pourraient laisser une fenêtre. À mesurer, attente faible.
9. **Feuille de match officielle : faisable, testé en direct ce soir.** L'API NHL publie les 20 joueurs habillés de chaque équipe entre T−24 et T−18, puis la liste officielle des scratches à T−18 / T−15. Le bot peut donc vérifier ses picks juste avant l'envoi de T−17, à condition de relever chaque minute (ou de décaler l'envoi à T−15 / T−12).
10. **Technologies** : le quantique n'apporte rien à ce problème en 2026 (❌). Un ensemble de réseaux de neurones sur CPU apporte déjà de la diversité à l'ensemble d'arbres (🟡). Les modèles de fondation tabulaires (TabPFN-3) méritent un test sur GPU loué, sans attente forte. Le GPU accélère l'entraînement mais n'améliore pas la précision.

---

## 1. Tableau de décision

Métrique : Δ log-loss en millinats par ligne (négatif = mieux), sur les lignes éligibles avec Pinnacle des deux côtés. IC 95 % bootstrap par soirée. Verdicts selon la règle du §2.

| # | Piste testée | Résultat clé (contrôle 2024-25) | Verdict | Ce qu'il faudrait ajouter au bot | Effort | Décision |
|---|---|---|---|---|---|---|
| H17 | **Harnais trié par joueur au lieu de la date** | le modèle servi est ~0,7 mnat moins bon au buteur que celui des simulations ; « buteur seul » simulé : +1,1 / +8,9 U au lieu de +46,6 / +17,1 U | ⚠️ écart à corriger | aligner prod et harnais | faible | ☐ |
| H17b | Calibrer hors du bloc récent (bloc au hasard ou ordre du harnais) | LightGBM, buteur : −1,13 [−2,21 ; −0,11] en val., −0,52 en ctrl ; ensemble (ordre du harnais) : −0,66 / −0,76 | 🟡 buteur | changer le découpage calibration / arbres dans `TemporalCalibratedGBM` | faible | ☐ |
| H1 | Empilement logit au lieu du mélange linéaire | buteur +0,03 [−0,32 ; +0,37] ; passes −0,20 [−0,60 ; +0,17] vs mélange actuel | ❌ | rien (garder le mélange) | — | ☐ |
| H2 | Référence US dévigée quand Pinnacle manque | buteur +0,78 [−2,40 ; +4,00] vs repli actuel | ❌ | rien | — | ☐ |
| H3 | Sélection « gros désaccord » (buteur, écart ≥ 0,4) | modèle de prod : +6,7 U, z 1,8 (val. +2,7 U, z 1,0) ; modèle du harnais : +11,3 U, z 2,3 (val. +24,4 U) | 🟡 contaminé | règle à pré-enregistrer, suivie en paper avant tout pari | faible | ☐ |
| H3b | Buteur seul (config de prod) | modèle de prod : +8,9 U, z 0,7 (val. +1,1 U) ; modèle du harnais : +17,1 U (val. +46,6 U) | 🟡 fragile | `markets = ["but"]` | nul | ☐ |
| H4 | Micro-structure du marché dans le mélange | buteur +1,15 [+0,13 ; +2,14] | ❌ | rien | — | ☐ |
| H5 | **xG en saison** (MoneyPuck) | ensemble de prod : passes −0,48 [−1,21 ; +0,20], buteur −0,05. LightGBM seul : passes −1,08 [−1,84 ; −0,30]. Le gain vient du xG pendant les présences sur la glace | 🟡 passes / ❌ buteur | features xG alimentées par le fichier de tirs MoneyPuck **et** les shift charts de l'API NHL | fort | ☐ |
| H6 | Gardien adverse titulaire (qualité, remplaçant, b2b) | buteur −0,28 [−0,75 ; +0,17] ; passes +1,41 | ❌ | rien | — | ☐ |
| H8 | Voyage et fatigue (distance, fuseaux, série à l'extérieur) | buteur +0,04 ; passes +0,01 | ❌ | rien | — | ☐ |
| H9 | Arbitres (tendance aux pénalités) | buteur −0,02 ; passes +0,12 | ❌ | rien | — | ☐ |
| H9b | NHL EDGE (tracking, saison précédente) | buteur +0,05 ; passes −0,22 [−0,79 ; +0,40] | ❌ | rien | — | ☐ |
| H10 | Calibration Platt / bêta au lieu de l'isotonique | ensemble de prod, buteur : Platt −0,32 [−0,84 ; +0,18], bêta −0,44 [−1,03 ; +0,13] (val. −0,49 / −0,43, IC < 0) | 🟡 buteur | remplacer l'isotonique dans `TemporalCalibratedGBM` | faible | ☐ |
| H11 | Objectif Poisson (comptage de buts) | buteur −0,50 [−1,37 ; +0,33] (val. −0,87 [−1,64 ; −0,12]) | 🟡 buteur | nouveau modèle de base | moyen | ☐ |
| H12 | Population / poids d'entraînement | population : effet < 0,1 mnat ; poids temporels : passes +0,51 | ❌ | rien | — | ☐ |
| H13 | Réseau tabulaire (ensemble de 5 MLP) ajouté à l'ensemble | buteur −0,41 [−1,15 ; +0,31] (val. −1,11 [−1,65 ; −0,61]) ; passes −0,23 | 🟡 | membre neuronal dans l'ensemble (torch, CPU) | moyen | ☐ |
| H13b | GPU pour XGBoost / CatBoost (RTX 3060) | XGBoost ×4,1, CatBoost ×5,7 plus rapides, log-loss identique à ±0,2 mnat | ✅ pour les expériences | `device="cuda"` / `task_type="GPU"` dans les scripts de recherche ; inutile en prod | faible | ☐ |
| H14 | Latence des books FR vs Pinnacle | les books FR ne suivent que 14-23 % des mouvements Pinnacle > 2 %, mais la cote figée reste à −12 % du juste (n = 27) | 🔬 attente faible | instantanés T−60 / T−20 ; alerte seulement sur gros chocs (scratch, gardien) | moyen | ☐ |
| H15 | Feuille de match officielle avant le match (`rosterSpots`) | mesuré en direct le 07/10 : 20 joueurs par équipe (18 patineurs + 2 gardiens) à T−24 et entre T−20 et T−18 ; scratches officiels à T−18 / T−15 | ✅ faisable | relever `rosterSpots` chaque minute dès T−30, envoyer les picks confirmés quand les deux équipes sont à 20 (au plus tard T−12) et retirer les joueurs non habillés | faible | ☐ |
| H15b | Lignes et unités PP Daily Faceoff | JSON lisible (lignes, PP1/PP2, blessés) | ✅ faisable | journalisation quotidienne (données futures) | faible | ☐ |
| H16 | Kelly sous incertitude / autre fraction | aucune fraction meilleure en contrôle (tous ≈ 0) | ❌ (garder 1/6) | rien | — | ☐ |
| T | Quantique | aucun avantage démontré | ❌ | rien | — | ☐ |

Légende : ✅ à intégrer (paper d'abord) · 🟡 prometteur, à confirmer · ❌ rejeté · 🔬 à mesurer avec de nouvelles données · ⚠️ défaut de mesure découvert pendant les tests.

---

## 2. Protocole

- **Données.** Prédictions walk-forward de la config de prod (`preds_q_final.parquet`, ensemble LGBM + XGB + CatBoost, retrain trimestriel), cotes historiques T−10 (`odds_long/odds_wide.parquet`, 12 books, oct. 2023 → janv. 2025), logs MoneyPuck match par match (`nhl/stats/skaters_all.csv`), API NHL publique (boxscores, arbitres, EDGE, shift charts), export VPS (`dashboard-data:db.json`, 05-06/10/2026).
- **Découpage.** Validation = saison 2023-24 (160 soirées). Contrôle = oct. 2024 → janv. 2025 (86 soirées). Les combinaisons (H1, H2, H4, tests incrémentaux) sont ajustées sur une saison et appliquées à l'autre ; les modèles (H5, H10-H13) sont ré-entraînés en walk-forward sur le passé uniquement, aux mêmes dates que le harnais (`simulate_roi.py`).
- **Lignes évaluées.** Joueurs éligibles selon les règles de prod, avec Pinnacle des deux côtés : 13 728 (buteur) et 15 144 (passes) lignes en validation, 6 887 et 8 062 en contrôle.
- **Métrique.** Δ log-loss par ligne, en millinats. Un millinat vaut 0,2 % de la log-loss. C'est le signal qui converge le plus vite : ~8 000 lignes suffisent pour détecter 1 mnat, alors qu'un ROI de +5 % demande ~4 900 paris.
- **Contrôles de reproduction, passés avant tout test.** La baseline redonne exactement les log-loss du rapport de configuration (buteur 0,55669 / 0,55790, passes 0,62768 / 0,62303 ; Pinnacle 0,55680 / 0,55950 / 0,62942 / 0,62281). La simulation de la config de prod au prix S2 redonne exactement l'audit data : +120,9 U en validation (445 paris), +1,6 U en contrôle (171 paris).
- **Règle de décision (fixée avant les tests).** ✅ si Δ < 0 en validation et en contrôle, avec l'IC du contrôle entièrement négatif. 🟡 si Δ < 0 dans les deux périodes mais l'IC touche 0. ❌ sinon. Une règle dont le seuil a été choisi en voyant le contrôle est marquée « contaminée ».
- **Prix des simulations.** Prix S2 de `nhl/sim/real_price.py` (cote Winamax reconstituée : Pinnacle « Oui » × 1,00 quand Pinnacle cote).
- **Quel modèle sous quelle piste.** Les tests de combinaison (H1-H4), les tests incrémentaux (H5 incrémental, H6-H9b), H14 et H16 utilisent les prédictions du harnais (`preds_q_final`). Les walk-forwards rejoués (H5 complet, H10-H13, H17) utilisent des lignes triées par date, comme la prod. Le défaut du harnais découvert en H17 change les niveaux (log-loss vs Pinnacle, gains simulés). Il ne change pas les comparaisons relatives : une feature qui n'apporte rien au modèle du harnais n'a pas de raison d'apporter au modèle de prod.

---

## 3. Résultats détaillés

### 3.1 Combiner le modèle et le marché (H1-H4)

**Point de départ : qui est le plus sharp ?** Information de chaque book après recalibration logistique (ajustée sur 2023-24), sur les lignes éligibles communes avec Pinnacle, contrôle 2024-25. Δ vs Pinnacle (positif = moins bon que Pinnacle) :

| Book | Buteur | Passes |
|---|---|---|
| DraftKings | +0,36 [−0,68 ; +1,45] | +0,41 [−0,19 ; +1,02] |
| FanDuel | −0,17 [−1,61 ; +1,29] | — (trop peu de lignes) |
| BetMGM | +0,10 [−1,62 ; +1,88] | +0,56 [−0,30 ; +1,45] |
| Caesars | **+1,97 [+0,22 ; +3,71]** | +0,82 [−0,19 ; +1,81] |
| Bovada | +0,66 [−1,35 ; +2,72] | −0,22 (n = 1 273) |
| BetRivers | +0,81 [−1,20 ; +2,83] | — |
| Consensus des books US (≥ 4 cotes) | +0,06 | +0,90 (n = 1 109) |

Parmi les 12 books de l'historique, Pinnacle est le plus sharp sur les props NHL, à égalité statistique avec DraftKings, FanDuel et BetMGM. Caesars est nettement moins bon au buteur, et le consensus des books US ne fait pas mieux que Pinnacle. Les études qui le décrivent comme « mou » sur les props portent sur la NFL et la MLB, et désignent les bourses d'échange (Kalshi, ProphetX) comme plus sharp. Ces bourses ne sont ni dans nos données ni accessibles depuis la France.

**H1 — Empilement logit vs mélange linéaire de prod.**

| Marché | Période | Mélange de prod − Pinnacle | Empilement − Pinnacle | Empilement − mélange |
|---|---|---|---|---|
| Buteur | val. | −0,78 [−1,63 ; +0,04] | −0,52 [−1,59 ; +0,49] | +0,26 [−0,12 ; +0,62] |
| Buteur | ctrl | **−1,59 [−2,70 ; −0,53]** | −1,55 [−2,60 ; −0,55] | +0,03 [−0,32 ; +0,37] |
| Passes | val. | −1,90 [−3,21 ; −0,63] | −1,77 [−2,43 ; −1,12] | +0,13 [−0,51 ; +0,80] |
| Passes | ctrl | −0,10 [−1,90 ; +1,49] | −0,30 [−1,97 ; +1,17] | −0,20 [−0,60 ; +0,17] |

Lecture : le mélange actuel est déjà le bon. Les poids optimaux restent instables d'une saison à l'autre : au buteur, le poids du modèle passe de 0,56 (ajusté sur 2023-24) à 0,75 (ajusté sur 2024-25) ; aux passes, de 0,74 à 0,44. Verdict ❌ pour l'empilement. Le mélange de prod est ✅ contre Pinnacle au buteur.

**H2 — Lignes sans Pinnacle** (20 % des buteurs éligibles, joueurs de profondeur, cote moyenne ≈ 7).

Correction d'un audit précédent : Pinnacle ne cote jamais le seul côté « Oui ». Il cote les deux côtés ou rien, dans l'historique comme en prod (181 lignes sur 181 au VPS les 5-6 octobre). Les « 63 % des cotes buteur sans côté Non » de `AUDIT_COMPLET_2026-10-04.md` sont des joueurs que Pinnacle ne cote pas du tout, surtout des joueurs non éligibles. Un dévig « unilatéral » de Pinnacle est donc inutile. Une carte logit apprise sur les lignes à Pinnacle (`logit p = −0,24 + 1,06 · logit(1/médiane US)`) reproduit bien Pinnacle là où il existe. Mais sur les lignes sans Pinnacle, elle ne bat pas le modèle : +0,28 (val.), −0,12 (ctrl), IC de ±2 à ±3 mnat. En 2023-24, le modèle **et** les books US surestimaient ces joueurs (+1,6 pt tous les deux), ce n'est donc pas un défaut propre au modèle. ❌. La majoration actuelle de 5 points d'EV sans Pinnacle reste la bonne protection.

**H3 — Règles de sélection simulées** (prix S2, bankroll 100 U, Kelly 1/6, plafonds de prod).

| Règle | Validation 2023-24 | Contrôle 2024-25 |
|---|---|---|
| Config de prod (buteur + passes) | 445 paris, +120,9 U, ROI +24,2 %, z +4,8 | 171 paris, **+1,6 U**, ROI +1,1 %, z +0,5 |
| Buteur seul | 197 paris, +46,6 U, ROI +28,7 %, z +2,8 | 114 paris, **+17,1 U**, ROI +25,3 %, z +1,2 |
| Passes seules | 327 paris, +81,7 U, z +4,0 | 76 paris, **−19,8 U**, ROI −22 %, z −0,8 |
| Buteur, écart ≥ 0,3, EV ≥ 0 *(contaminé)* | 257 paris, +18,4 U, z +2,1 | 55 paris, +8,3 U, z +1,8 |
| Buteur, écart ≥ 0,4, EV ≥ 0 *(contaminé)* | 146 paris, +24,4 U, z +2,5, DD 6,8 U | 38 paris, +11,3 U, z +2,3, DD 2,5 U |
| Buteur seul, lignes avec Pinnacle | 113 paris, +23,5 U, z +2,2 | 16 paris, +8,8 U, z +2,2 |

L'écart est `logit(p_modèle) − logit(p_Pinnacle)`. Sur **toutes les lignes** (pas seulement les paris) où l'écart dépasse 0,3, au buteur :

| | Lignes | Réussite observée | Pinnacle | Modèle | z vs Pinnacle |
|---|---|---|---|---|---|
| Validation 2023-24 | 1 035 | 29,6 % | 25,3 % | ≈ 33 % | +3,2 |
| Contrôle 2024-25 | 215 | 33,0 % | 23,4 % | ≈ 30 % | +3,3 |

C'est le signal le plus net de ce rapport : quand le modèle voit un buteur nettement au-dessus de Pinnacle, il a raison plus souvent que Pinnacle, dans les deux saisons. En validation, la vérité tombe à mi-chemin entre le modèle et Pinnacle, ce que fait déjà le mélange ; en contrôle, elle dépasse même le modèle. Aux passes, l'effet n'existe qu'en 2023-24 (z 3,6, puis 0,6).

Au prix Pinnacle « Oui », le ROI des lignes à écart de 0,4 à 0,6 vaut +9,9 % en validation et +18,6 % en contrôle ; entre 0,3 et 0,4, il vaut −3,0 % puis +18,6 %. D'où le seuil de 0,4 pour parier (tableau ci-dessus). Script : `h3b_buckets.py`.

Lecture :
- Le marché passeur fait toujours le yo-yo (+82 U puis −20 U) : c'est lui qui rend la config de prod nulle en contrôle.
- « Buteur seul » est positif dans les deux périodes ; la moitié de son gain vient des lignes sans Pinnacle.
- La règle « gros désaccord » a le meilleur rapport gain / risque (drawdown 2,5 U en contrôle), mais ses seuils ont été lus sur le contrôle : 🟡 contaminé. Elle se valide en paper trading ou sur la saison 2025-26 (§5).

**Les mêmes règles avec le modèle tel que la prod l'entraîne** (lignes triées par date, voir H17 au §3.3 bis ; `h3c_chrono.py`) :

| Règle | Validation 2023-24 | Contrôle 2024-25 |
|---|---|---|
| Config de prod (buteur + passes) | 511 paris, +39,1 U, ROI +6,8 %, z +2,4 | 169 paris, +5,6 U, ROI +3,7 %, z +0,9 |
| Buteur seul | 187 paris, **+1,1 U**, ROI +0,8 %, z +0,3 | 90 paris, **+8,9 U**, ROI +16,8 %, z +0,7 |
| Buteur, écart ≥ 0,4, EV ≥ 0 | 117 paris, +2,7 U, z +1,0 | 20 paris, +6,7 U, z +1,8 |
| Buteur, écart ≥ 0,3, EV ≥ 0 | 186 paris, +0,6 U, z +0,9 | 37 paris, +7,7 U, z +1,9 |
| Lignes (pas les paris) à écart ≥ 0,3 : réussite vs Pinnacle | 27,8 % vs 23,2 % (n = 1 046, z 3,5) | 26,9 % vs 21,6 % (n = 216, z 1,9) |

Le signal « gros désaccord » subsiste avec le modèle de prod, mais il ne suffit plus à battre la marge FR en validation. Les gains simulés des rapports précédents, et ceux du tableau ci-dessus en version harnais, viennent en bonne partie du schéma de calibration du harnais.

**H4 — Micro-structure du marché** (dispersion des books US, nombre de books, marge Pinnacle, écart US − Pinnacle) ajoutée au mélange : buteur +0,25 / +1,15 [+0,13 ; +2,14], passes +0,02 / −0,17. ❌ (ça dégrade même le buteur en contrôle).

### 3.2 Information nouvelle (H5, H6, H8, H9)

Deux tests :
- **Test incrémental** : la feature apporte-t-elle quelque chose que ni le modèle ni Pinnacle n'ont ? On compare une régression logistique [logit Pinnacle, logit modèle] avec et sans la feature (ajustée sur une saison, appliquée à l'autre).
- **Walk-forward complet** pour le xG : modèle ré-entraîné avec les nouvelles features, retrain trimestriel, comparé au même modèle sans elles (LightGBM seul, puis ensemble de prod).

**H5 — xG en saison.** 12 features issues des logs MoneyPuck match par match, toutes calculées sur les matchs antérieurs :
- xG individuel : sur 10 matchs, en moyenne exponentielle, par 60 min ;
- tirs et xG à haut danger, xG en avantage numérique ;
- xG pour sur la glace (10 matchs) et part de xG à 5 contre 5 ;
- part de départs en zone offensive ;
- finition (buts − xG cumulés, shrinkés) ;
- xG pour de l'équipe et xG concédé par l'adversaire sur 10 matchs.

| Test | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl |
|---|---|---|---|---|
| Incrémental (au-dessus du modèle et de Pinnacle) | +0,43 | −0,00 | −0,05 | −0,53 [−1,11 ; +0,10] |
| Walk-forward LightGBM : modèle | +0,27 | −0,49 | **−0,70 [−1,36 ; −0,01]** | **−1,08 [−1,84 ; −0,30]** |
| Walk-forward LightGBM : mélange avec Pinnacle | +0,15 | −0,33 | −0,61 [−1,21 ; +0,01] | **−0,96 [−1,65 ; −0,26]** |
| **Walk-forward ensemble de prod** (LGBM + XGB + CatBoost, trié par date) : modèle | +0,06 [−0,46 ; +0,62] | −0,05 [−0,90 ; +0,75] | −0,20 [−0,78 ; +0,39] | −0,48 [−1,21 ; +0,20] |
| Walk-forward ensemble de prod : mélange avec Pinnacle | +0,05 | −0,04 | −0,18 | −0,43 [−1,08 ; +0,19] |
| Ablation sans les 3 features de présence sur la glace (LightGBM) | −0,39 [−1,16 ; +0,35] | −0,49 [−1,41 ; +0,44] | +0,14 | −0,09 |

Les features xG pèsent 11 % du gain des arbres aux passes et 14,5 % au buteur. La plus utile est le **xG pour sur la glace sur 10 matchs** (6,7 % et 7,6 % du gain) : la qualité des occasions créées quand le joueur est sur la glace, donc aussi par ses linemates. C'est logique pour les passes.

L'ablation le confirme : **sans les features de présence sur la glace** (xG pour sur la glace, part de xG à 5 contre 5, départs en zone offensive), **le gain des passes disparaît**. Les autres features xG, plus simples à produire, donnent seulement un léger 🟡 au buteur.

Sur l'ensemble de prod, le gain des passes se réduit de moitié et n'est plus significatif : XGBoost et CatBoost captent déjà une partie de l'information. En paris, l'ensemble avec xG fait +48,4 U en validation et −4,1 U en contrôle aux passes, contre +23,4 et −5,4 U sans. Au buteur : +21,0 et +9,9 U, contre +1,1 et +8,9 U.

Verdict : 🟡 aux passes (✅ sur LightGBM seul, 🟡 sur l'ensemble de prod), ❌ au buteur. À ne construire que si l'on garde le marché passeur, et en sachant qu'il faut les présences sur la glace.

Faisabilité en prod : MoneyPuck bloque les requêtes directes (Cloudflare, 403 même avec l'empreinte Chrome). Un miroir public republie chaque nuit le fichier de tirs de la saison en cours (`shots_2026.parquet`, mis à jour le 07/10 à 17:23 UTC), sous licence non commerciale avec mention de MoneyPuck. Le xG individuel s'en déduit directement. Le xG sur la glace demande en plus les présences (shift charts de l'API NHL, disponibles depuis 2012 au moins). Garder l'historique d'entraînement (MoneyPuck) et la prod sur la même source préserve la parité train/serve. Attention : l'historique utilisé ici (`nhl/stats/skaters_all.csv`, 2,6 Go) est ignoré par git et n'est probablement pas sur le VPS. Les fichiers de tirs 2007-2025 du miroir (~250 Mo) peuvent le reconstituer.

**H6 — Gardien adverse titulaire.** Boxscores 2021-25 de l'API NHL (titulaire, temps de jeu, tirs, buts). Features :
- GSAx/60 shrinké : xG contre au prorata du temps de jeu, moins les buts encaissés ;
- % d'arrêts shrinké ;
- expérience ;
- titulaire la veille ;
- part des titularisations sur 20 matchs, et indicateur « remplaçant ».

Test incrémental : buteur +0,06 / −0,28, passes +0,96 / +1,41 (dégrade). ❌ Pinnacle intègre déjà le gardien annoncé.

**H8 — Voyage et fatigue.** Distance depuis le match précédent, changement de fuseau, longueur de la série à l'extérieur, pour l'équipe et l'adversaire (le repos et le b2b sont déjà dans le modèle). Buteur +0,40 / +0,04, passes +0,73 / +0,01. ❌

**H9 — Arbitres.** Équipes arbitrales et occasions de PP de 3 936 matchs (2022-25). Tendance de l'équipe arbitrale shrinkée, et son produit avec le temps de PP du joueur. Après shrinkage, les équipes arbitrales ne diffèrent que de ±0,26 PP par match autour de 5,86. Buteur +0,08 / −0,02, passes +0,30 / +0,12. ❌

**H9b — NHL EDGE (tracking).** Données de la saison précédente pour 718 joueurs : vitesse de tir max, vitesse de patinage max, accélérations > 20 mph, distance, temps en zone offensive, part et réussite des tirs à haut danger. Buteur +0,73 [+0,10 ; +1,33] / +0,05, passes +0,06 / −0,22. ❌ Ce que le tracking résume (talent, rôle) est déjà dans les stats du joueur et dans le prix.

### 3.3 Modélisation (H10-H13)

Les variantes sont comparées à une baseline LightGBM rejouée à l'identique (même découpage, mêmes features). Cette baseline LightGBM seule est un peu moins bonne que l'ensemble de prod (buteur 0,55781 contre 0,55669 en validation).

**H10 — Calibration.** Même bloc de calibration que l'isotonique actuelle (les 15 % les plus récents du train).

| Calibration | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl | Valeurs distinctes entre 0,15 et 0,50 |
|---|---|---|---|---|---|
| Platt sur logit | **−0,67 [−1,07 ; −0,29]** | −0,37 [−0,91 ; +0,17] | +0,03 | −0,23 | ~19 400 (isotonique : ~200) |
| Bêta (3 paramètres) | **−0,61 [−1,00 ; −0,22]** | −0,34 [−0,90 ; +0,21] | +0,18 | −0,24 | ~19 400 |
| Isotonique lissée | −0,13 | −0,14 | +0,02 | +0,07 | ~18 600 |
| Platt, sur l'ensemble de prod (trié par date) | **−0,49 [−0,83 ; −0,14]** | −0,32 [−0,84 ; +0,18] | −0,07 | −0,12 | |
| Bêta, sur l'ensemble de prod (trié par date) | **−0,43 [−0,79 ; −0,06]** | −0,44 [−1,03 ; +0,13] | +0,09 | −0,12 | |

Verdict : 🟡 au buteur (Platt et bêta, confirmés sur l'ensemble de prod), ❌ aux passes. Bonus : les paliers disparaissent (deux joueurs ne reçoivent plus la même probabilité), et l'EV n'avance plus par sauts.

**H11 — Objectif Poisson.** LightGBM sur le nombre de buts, `p(≥1) = 1 − exp(−λ)`, puis isotonique.
- Buteur : modèle −0,87 [−1,64 ; −0,12] / −0,50 [−1,37 ; +0,33], mélange −0,51 / −0,26. 🟡
- Passes : −0,16 / +0,51. ❌
- Le Poisson brut surestime P(2 buts ou plus) d'environ 20 % (2,14 % prédit, 1,73 % observé) : un marché « doublé » demanderait sa propre calibration.

**H12 — Population et poids d'entraînement.**
- Entraîner seulement sur des joueurs proches de ceux servis (TOI ≥ 12 min, ≥ 5 matchs) : −0,08 / −0,07 au buteur, +0,10 / −0,10 aux passes. Effet nul.
- Poids temporels (demi-vie 3 saisons) : buteur −0,17 / −0,01, passes +0,73 / +0,51. Rien au buteur, dégradation aux passes.

Verdict : ❌ (aucun gain mesurable).

**Impact pari des variantes.** Mêmes règles de prod, un marché à la fois, prix S2, walk-forwards triés par date comme en prod (`h_bet_variants.py`). Gain en U :

| Variante | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl |
|---|---|---|---|---|
| Baseline LightGBM | −2,8 | −2,9 | +84,1 | −7,8 |
| + xG en saison | +4,8 | +6,9 | +44,3 | **+3,7** |
| + xG sans présences sur la glace | +15,8 | −2,2 | +57,3 | −6,7 |
| Objectif Poisson | **+20,1** | **+14,3** | +38,9 | −21,4 |
| Calibration Platt | +7,9 | +6,9 | +44,5 | −24,0 |
| Calibration bêta | +9,3 | +2,7 | +30,1 | −19,6 |
| **Ensemble de prod (trié par date)** | +1,1 | +8,9 | +23,4 | −5,4 |
| Ensemble + xG en saison | +21,0 | +9,9 | +48,4 | −4,1 |
| Ensemble + calibration Platt | +9,6 | −3,8 | +29,9 | −7,0 |
| Ensemble + calibration bêta | +10,2 | −5,3 | +21,2 | −6,9 |
| *Pour mémoire : ensemble du harnais (simulations publiées, H17)* | *+46,6* | *+17,1* | *+81,7* | *−19,8* |

Ces gains sont très bruités (une centaine de paris par saison et par marché) ; la log-loss reste le juge. Trois constats vont pourtant dans le même sens qu'elle :
- le Poisson améliore le buteur dans les deux périodes ;
- le xG améliore les deux marchés, sur LightGBM comme sur l'ensemble ;
- l'ensemble trié par date fait mieux que LightGBM seul trié par date au buteur (+1,1 / +8,9 U contre −2,8 / −2,9 U).

Toute amélioration doit être confirmée sur l'ensemble, dans un harnais aligné sur la prod (H17).

**H13 — Réseau tabulaire (ensemble de 5 MLP, approximation de TabM sur CPU).** Entraînement unique avant le 2023-10-01, sans retrain, sur les mêmes features ; calibration isotonique sur le bloc récent. Comparé à LightGBM entraîné sur le même découpage (`h13_mlp.py`) :

| | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl |
|---|---|---|---|---|
| MLP seul − LightGBM | −1,20 [−2,26 ; −0,21] | +0,09 [−1,41 ; +1,55] | +0,55 | +0,59 |
| Moyenne des logits MLP + LightGBM − LightGBM | **−1,11 [−1,65 ; −0,61]** | −0,41 [−1,15 ; +0,31] | −0,22 | −0,23 |

Seul, le réseau n'est pas meilleur (❌). **En membre d'ensemble, il apporte de la diversité sur les deux marchés (🟡)**, ce qui rejoint TabArena : les meilleurs résultats viennent du mélange arbres + réseaux. Entraînement : 4 à 6 min sur CPU. Le test mérite un walk-forward complet avec retrain, puis un vrai TabM ou RealMLP.

**GPU (H13b).** Un fit des passes (638 780 lignes, 54 features, mêmes hyperparamètres que la prod) sur la RTX 3060 du PC (`h13_gpu.py`) :

| Modèle | CPU (12 threads) | GPU | Log-loss contrôle (brute) |
|---|---|---|---|
| XGBoost | 19,7 s | **4,8 s** (×4,1) | 0,62287 → 0,62262 |
| CatBoost | 30,9 s | **5,4 s** (×5,7) | 0,62280 → 0,62302 |

Même précision, entraînements 4 à 6 fois plus rapides : un walk-forward complet de l'ensemble passerait d'environ 13 min à 4-5 min (LightGBM reste sur CPU). Utile pour multiplier les expériences, sans effet sur la qualité. Les résultats GPU ne sont pas identiques bit à bit à ceux du CPU : figer le matériel dans les comparaisons.

### 3.3 bis — Découverte : le harnais de simulation ne calibre pas comme la prod (H17)

`TemporalCalibratedGBM` calibre son isotonique sur « les 15 % de lignes les plus récentes », à condition que les lignes soient triées par date. C'est le cas en prod (`train_models.py`, `load_training_frame` trie par date). Ce n'est **pas** le cas dans le harnais :
- `simulate_roi.walk_forward_predictions` reçoit les features de `build_features`, triées par joueur puis par date, et ne les retrie pas ;
- au retrain du 2023-10-01, le « bloc récent » de calibration couvre en réalité les joueurs aux playerId les plus élevés (8477956 → 8484287), soit surtout de jeunes joueurs, sur les saisons 2014 à 2023 ;
- toutes les prédictions walk-forward (`preds_p1b_ens`, `preds_q_final`) et donc toutes les simulations de ROI, y compris la recherche de configuration, ont été produites avec ce schéma, différent de la prod.

**Vérification.** Le même ensemble ré-entraîné dans l'ordre du harnais (lignes triées par joueur) redonne **exactement** les prédictions publiées : 96 261 lignes sur 96 261 identiques, écart maximal 0,0000. L'ordre des lignes est donc la seule différence entre les simulations et le modèle de prod.

Même ensemble ré-entraîné avec les lignes triées par date, comme en prod (`h17_order.py`) :

| | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl |
|---|---|---|---|---|
| Ensemble trié par date − ensemble du harnais | +0,66 [−0,11 ; +1,34] | +0,76 [−0,18 ; +1,70] | +0,45 [−0,22 ; +1,12] | −0,35 [−1,11 ; +0,47] |
| Ensemble trié par date − Pinnacle | +0,55 | −0,84 | −1,29 | −0,12 |
| Mélange de prod (trié par date) − Pinnacle | −0,37 [−1,25 ; +0,43] | **−1,06 [−2,09 ; −0,02]** | −1,51 [−2,87 ; −0,18] | −0,42 |

En paris (mêmes règles de prod, prix S2) :

| Config | Modèle du harnais (simulations publiées) | Modèle entraîné comme en prod |
|---|---|---|
| Config de prod, validation / contrôle | +120,9 U / +1,6 U | +39,1 U / +5,6 U |
| Buteur seul, validation / contrôle | +46,6 U / +17,1 U | **+1,1 U / +8,9 U** |
| Passes seules, validation / contrôle | +81,7 U / −19,8 U | +23,4 U / −5,4 U |

Lecture :
- **Le modèle réellement servi est moins bon que celui des simulations**, d'environ 0,7 mnat au buteur. Le mélange de prod bat encore Pinnacle au buteur en contrôle, mais de justesse. Les gains affichés par le TOML, le simulateur et la carte « projection » du dashboard ne correspondent pas au modèle servi.
- L'erreur du harnais s'est révélée favorable. Explication probable : avec un bloc récent, les arbres ne voient jamais les ~1,5 dernières saisons (l'audit du 04/10 le notait déjà) ; avec le bloc « jeunes joueurs », ils les voient. Deux variantes contrôlées (LightGBM seul, vs le même modèle trié par date) le confirment au buteur :

  | Bloc de calibration | Buteur val. | Buteur ctrl | Passes val. | Passes ctrl |
  |---|---|---|---|---|
  | 15 % tirés au hasard | **−1,13 [−2,21 ; −0,11]** | −0,52 [−1,77 ; +0,69] | +0,62 | +0,34 |
  | Ordre du harnais (par joueur) | −0,69 [−1,60 ; +0,23] | −0,57 [−1,71 ; +0,57] | −0,45 | +0,01 |

  Verdict « calibrer hors du bloc récent » : 🟡 au buteur, ❌ aux passes. Une version plus propre serait de calibrer sur des prédictions hors échantillon par blocs de temps (validation croisée) et d'entraîner les arbres sur 100 % des lignes.
- Les options `refit_full` et `split_calib`, rejetées à l'audit P2 du 04/10, ont été jugées dans ce harnais mal trié : elles méritent d'être retestées après correction.
- **À corriger dans tous les cas**, pour que la simulation mesure ce que fait le bot :
  - soit trier par date dans le harnais, puis refaire la simulation de la config ;
  - soit adopter en prod le schéma qui gagne (calibration hors bloc récent), après validation.

### 3.4 Marché et exécution (H14-H15)

**Pourquoi la marche est haute.** Au prix FR (≈ cote Pinnacle « Oui »), voici de combien la vraie probabilité doit dépasser la probabilité juste de Pinnacle, en relatif, pour qu'un pari soit rentable. Médianes sur les lignes éligibles 2023-25 (`h14_required_edge.py`) :

| Marché | Cote | Lignes | Proba juste moyenne | Écart requis pour EV ≥ 0 | Pour EV ≥ 8 % (seuil de prod) |
|---|---|---|---|---|---|
| Buteur | 1,5-2,5 | 1 998 | 41 % | +9 % | +18 % |
| Buteur | 2,5-3,5 | 7 698 | 30 % | +14 % | +23 % |
| Buteur | 3,5-5 | 10 311 | 20 % | +23 % | +33 % |
| Buteur | 5-8 | 607 | 15 % | +30 % | +41 % |
| Passes | 1,5-2,5 | 9 201 | 45 % | +8 % | +17 % |
| Passes | 2,5-3,5 | 11 470 | 30 % | +13 % | +22 % |
| Passes | 3,5-5 | 2 328 | 22 % | +20 % | +29 % |

Il faut donc que Pinnacle sous-estime de 10 à 40 % la probabilité des paris choisis, alors que le modèle ne bat Pinnacle que de ~1 mnat en moyenne. C'est possible sur le petit sous-ensemble des gros désaccords (un écart logit de 0,3 représente environ +24 % de probabilité relative à 25 %), pas sur l'ensemble des lignes. Cela explique aussi pourquoi un book FR resté en retard d'un mouvement Pinnacle de 2 à 8 % n'est pas value.

**H14 — Books FR vs Pinnacle**, cotes réellement relevées par le VPS les 5 et 6 octobre (1 072 cotes). Échantillon très petit, à lire comme un ordre de grandeur.
- Meilleure cote des 3 books vs cote juste Pinnacle (Shin) : buteur −11,6 % (n = 83, 0 % des lignes au-dessus de 0), passes −11,1 % (n = 94, 2 % au-dessus de 0). La meilleure cote FR vaut la cote Pinnacle « Oui » (rapport 1,00 au buteur, 0,98 aux passes), ce qui confirme le prix S2 des simulations.
- Meilleur des 3 vs Winamax seul : +1,7 % au buteur (n = 10), +1,4 % aux passes (n = 6). Vs Unibet seul : +9,1 % et +3,6 %.
- Lignes sans Pinnacle : meilleure cote FR = 1,005 × médiane US au buteur ; Winamax seul = 1,045 × (la calibration du 04/10 donnait 1,11).
- **Mouvements entre l'aperçu (16h30) et les picks confirmés** (135 couples) : Pinnacle bouge sur 23 % des lignes (0,7 % en moyenne), Unibet 22 %, Betclic 25 %. **Quand Pinnacle bouge de plus de 2 %, Unibet ne suit que dans 14 % des cas (n = 14) et Betclic dans 23 % (n = 13).**
- **Mais ce retard ne crée pas de value à lui seul.** Dans les 27 cas, Pinnacle avait raccourci la cote « Oui ». La cote du book FR restée figée était encore à −12,4 % de la cote juste en moyenne, et à −5,5 % au mieux : les mouvements observés (2 à 8 %) sont plus petits que la marge FR (~12 %). Seuls de gros chocs pourraient créer de la value : scratch d'un titulaire, changement de gardien, promotion en PP1. 🔬 À mesurer avec des instantanés plus fréquents ; attente faible.

**H15 — Faisabilité des sources** (tests le 07/10).

| Source | Résultat | Usage possible |
|---|---|---|
| Feuille de match officielle (`rosterSpots` du play-by-play) | ✅ relevé toutes les 2 min le 07/10. PIT-WSH : 23 + 23 joueurs jusqu'à T−30, puis 21 + 21 à T−28 (état « PRE »), puis **20 + 20 à T−24**. COL-WPG : **20 + 20 entre T−20 et T−18**. Les joueurs retirés sont les scratches, dont un défenseur régulier (Matt Roy, WSH, ~20 min de jeu par match) | confirmer les joueurs habillés juste avant l'envoi de T−17 ; c'est serré : il faudrait relever chaque minute et décaler l'envoi à T−15 / T−12 |
| Arbitres et scratches (`right-rail`) | ✅ arbitres publiés à T−33 / T−30 ; liste officielle des scratches à T−18 / T−15, identique aux retraits de `rosterSpots` | confirmation des scratches ; arbitres rejetés par H9 |
| Shift charts (API NHL) | ✅ ~760 présences par match, disponibles en 2012 comme en 2024 | linemates, xG sur la glace, TOI à 5 contre 5 |
| NHL EDGE | ✅ carte joueur et vitesses de tir | rejeté par H9b |
| Daily Faceoff, lignes | ✅ JSON : lignes F1-F4, D1-D3, PP1/PP2, PK1/PK2, blessés, « game-time decision », mis à jour le soir même | lignes du jour (RotoWire ne donne que le PP) |
| Daily Faceoff, gardiens | ✅ JSON | confirmation des gardiens |
| MoneyPuck direct | ❌ défi Cloudflare (403) | — |
| Miroir MoneyPuck (GitHub Releases) | ✅ `shots_2026.parquet` mis à jour chaque nuit | xG en saison (H5) |
| Cotes boostées Winamax | ✅ lisibles (`PRELOADED_STATE`). Le 07/10 : 2 boosts NHL, tous deux des combinés de match (« +6,5 buts dans WPG-COL et WSH-PIT » à 3,75 au lieu de 2,96 ; « EDM gagne et +5,5 buts » à 3,25 au lieu de 2,75), mise max 20 € | évaluation de l'EV : demande un modèle de score de match (non fait) |

### 3.5 Mise (H16)

Paris choisis par la règle de prod au prix S2 (prédictions du harnais), puis mises recalculées : fraction k de Kelly plein (plafond 3 % de bankroll par pari), croissance logarithmique de la bankroll par soirée.

| Sélection | Période | k = 1/16 | k = 1/6 (prod) | k = 1/4 | k = 1/2 | 1 % fixe | Baker-McHale × ½ Kelly |
|---|---|---|---|---|---|---|---|
| Prod | val. | +0,48 | +1,22 | +1,69 | +2,30 | +1,00 | +1,96 |
| Prod | ctrl | −0,00 | +0,00 | +0,02 | −0,01 | +0,01 | +0,05 |
| Buteur seul | val. | +0,16 | +0,43 | +0,63 | +0,92 | +0,49 | +0,87 |
| Buteur seul | ctrl | +0,07 | +0,19 | +0,28 | +0,40 | +0,14 | +0,29 |

La croissance augmente avec la fraction là où un edge existait, et rien ne marche là où il n'y en avait pas. La réduction de Baker-McHale ne domine pas. Monter la fraction ne se justifie qu'une fois l'edge confirmé en paper trading. ❌ pour un changement aujourd'hui. Une fraction de 1/4 sur « buteur seul » serait le candidat naturel après validation.

---

## 4. Nouvelles technologies

| Technologie | Ce qu'elle promet | État en 2026 | Verdict pour ce moteur |
|---|---|---|---|
| **Apprentissage automatique quantique** (QSVM, réseaux variationnels) | classifieurs plus puissants | Sur 160 jeux de données, les classifieurs quantiques font moins bien que des modèles classiques non réglés, et retirer l'intrication ne change rien ([Bowles et al., 2024](https://arxiv.org/abs/2403.07059)). Aucun avantage démontré sur des données réelles ([état du domaine 2026](https://postquantum.com/quantum-ai/quantum-machine-learning-reality/)) | ❌ |
| **Recuit quantique** (D-Wave, QAOA) pour le portefeuille de paris | optimiser des milliers de combinaisons corrélées | Pertinent pour un book qui gère des millions de combinés ; notre portefeuille compte 1 à 5 paris par soir, résolu exactement en une milliseconde sur un PC | ❌ |
| **Estimation d'amplitude** (Monte Carlo quadratiquement plus rapide) | simulations plus rapides | Exige des machines tolérantes aux fautes, 3 à 4 ordres de grandeur au-delà du matériel actuel ([revue](https://arxiv.org/abs/2011.06492)) | ❌ (à revoir dans 5-10 ans) |
| **Modèles de fondation tabulaires** (TabPFN-3, TabICL, Mitra) | précision au niveau des GBDT réglés, sans réglage | [TabPFN-3](https://arxiv.org/abs/2605.13986) annonce jusqu'à 1 M de lignes et 200 features, devant des GBDT réglés 8 h sur TabArena, mais sur un GPU H100. Une variante [Drift-Resilient](https://arxiv.org/abs/2411.10634) vise les dérives temporelles | 🟡 à tester sur GPU loué (≈ 1-2 € de l'heure) ; la RTX 3060 (6 Go) limite à des sous-échantillons |
| **Réseaux tabulaires** (TabM, RealMLP) | diversité dans l'ensemble | En tête de [TabArena](https://arxiv.org/abs/2506.16791) avec LightGBM après ensemblage ; [TabM](https://arxiv.org/abs/2410.24210) = ensemble implicite de MLP | 🟡 H13 : un ensemble de 5 MLP sur CPU améliore le mélange avec LightGBM (−1,11 mnat en validation au buteur) |
| **GPU** (XGBoost, CatBoost) | entraînements plus rapides | H13b : ×4 à ×6 sur la RTX 3060 du PC, précision identique | ✅ pour la recherche ; pas d'intérêt en prod (un retrain par semaine) |
| **Programmation probabiliste** (PyMC + JAX, NumPyro) | talent des joueurs hiérarchique et dynamique, incertitude par joueur | Ajuster un modèle hiérarchique sur 160 000 matchs prend ~3 min sur GPU ([PyMC Labs](https://www.pymc-labs.com/blog-posts/pymc-stan-benchmark)) | 🔬 piste de recherche (remplacer les priors fixes 0,85 / 1,30 / 7,0 par 60 min) |
| **Simulateur de match** (Monte Carlo présence par présence, à partir des lignes du jour) | probabilités cohérentes entre buteur, passes, points, 2+ buts et combinés d'un même match | Seule façon propre de tarifer un bet builder (MyMatch) ou un boost de combiné ; exige les lignes du jour (H15b) et un modèle de taux par ligne | 🔬 utile si l'on attaque les combinés (§5) |
| **LLM** (extraction d'actualités, agents) | lire blessures, retours, déclarations avant les books | Daily Faceoff fournit déjà lignes, blessés et « game-time decisions » structurés. Un LLM ne servirait que pour l'actualité non structurée, avec un risque d'hallucination et de latence | 🟡 après H15b, si la latence FR se confirme |
| **Flux temps réel** (WebSocket, flux Pinnacle tiers) | voir les mouvements de Pinnacle en secondes | L'API Pinnacle est fermée au public depuis le 23/07/2025 ; accès possible sur demande pour un projet de handicapping ([doc](https://github.com/pinnacleapi/pinnacleapi-documentation)), sinon flux tiers payants | 🔬 utile seulement si H14 se confirme |

**Moteur plus puissant ?** Les tests de ce rapport montrent que le moteur est limité par **l'information** et par **la façon dont on l'entraîne**, pas par la puissance de calcul. Le tuning Optuna (−0,1 %) et les variantes de population ou de poids bougent la log-loss de moins de 0,2 mnat. Les plus gros écarts viennent :
- du découpage entre arbres et calibration (H17, ~0,7 mnat au buteur) ;
- du xG sur la glace (jusqu'à 1 mnat aux passes sur LightGBM) ;
- de la diversité des modèles (ensemble d'arbres, réseau en membre d'ensemble).

Un moteur plus gros sans données nouvelles n'aidera pas.

---

## 5. Non testable aujourd'hui : ce qu'il faudrait

| Piste | Pourquoi pas de test | Ce qu'il faut | Coût |
|---|---|---|---|
| Linemates et lignes du jour (promotion en 1re ligne, PP1) | aucun historique des lignes annoncées | journaliser Daily Faceoff chaque jour (H15b), tester dans 2-3 mois | gratuit |
| Total implicite du match et proba de victoire comme features | pas d'historique h2h / totaux | historique The Odds API, endpoint groupé : ~20 crédits par jour | ~11 000 crédits (2023-26) |
| Saison test vierge pour H3, H5, H10, H11 | le contrôle 2024-25 est déjà « vu » | props 2025-26 buteur + passes, un instantané, `bookmakers=` ≤ 10 books | ~26 000 crédits |
| Meilleur moment pour parier, latence FR (H14) | un seul instantané historique (T−10) | instantanés FR et Pinnacle à T−60, T−20, T−5 | crédits The Odds API pour Pinnacle à chaque instantané |
| Bet builder (MyMatch, Betclic) | aucun prix de combiné FR historique | relever les prix et construire un modèle joint (corrélations but / passe) | moyen |
| Cotes boostées | EV inconnue sans prix Pinnacle des marchés de match | modèle de score de match calé sur la ligne et le 1N2 Pinnacle | faible |

---

## 6. Ordre d'ajout proposé (si tu valides)

1. **D'abord, aligner la prod et la simulation (H17).** Tant que le harnais ne calibre pas comme le bot, aucun chiffre simulé ne décrit le bot. Deux voies :
   - **(a) recommandée** : adopter en prod le schéma qui gagne. Bloc de calibration hors du bloc récent : tiré au hasard, ou mieux, prédictions hors échantillon par blocs de temps, avec des arbres entraînés sur toutes les saisons. Puis trier le harnais de la même façon, ré-entraîner, refaire `simulate_roi` et la recherche de config. Gain attendu au buteur : ~0,7 mnat, l'écart harnais / prod mesuré ici.
   - **(b)** trier le harnais par date, comme la prod, et accepter des projections plus basses.
2. **Sans risque, maintenant** :
   - corriger le retrain hebdomadaire : `services.py:558` lance `train_models.py --live` sans `--algos`, donc un LightGBM seul au lieu de l'ensemble validé (LightGBM seul : −2,8 U au buteur en validation, contre +1,1 U pour l'ensemble) ;
   - journaliser dans `players` `p_novig`, `p_final` et `player_id` (0 % renseignés sur le VPS) ;
   - journaliser Daily Faceoff (lignes, PP, blessés) et les cotes boostées NHL ;
   - ajouter des instantanés T−60 et T−20 (latence FR, attente faible) ;
   - vérifier les joueurs habillés (`rosterSpots`, 20 par équipe entre T−24 et T−18) avant l'envoi des picks confirmés.
3. **Stratégie** : rester en paper trading. « Buteur seul » reste le choix le plus prudent, mais ses gains simulés avec le modèle de prod sont faibles (+1,1 / +8,9 U). Pré-enregistrer la règle « gros désaccord » (écart ≥ 0,4) comme indicateur suivi en paper, sans changer les mises.
4. **Modèle, une fois l'étape 1 faite**, chaque piste rejouée dans le harnais corrigé :
   - calibration Platt ou bêta (🟡, confirmée sur l'ensemble) ;
   - objectif Poisson au buteur (🟡) ;
   - membre neuronal dans l'ensemble (🟡) ;
   - features xG sur la glace, seulement si l'on garde les passes (🟡).
5. **Achats de données, à décider** : props 2025-26 (~26 000 crédits), le seul moyen de valider tout ce qui précède sur une saison jamais vue ; puis l'historique h2h et totaux (~11 000 crédits).

---

## Annexe A — Reproduction

Scripts dans le scratchpad de la session, hors dépôt :
`C:\Users\2507m\AppData\Local\Temp\claude\c--Users-2507m-Desktop-Milan-code-bet2\2d32c04b-1c0d-4265-9841-c36f90afae80\scratchpad\exp\`.

Ils lisent le dépôt et importent le code du bot sans le modifier. Sorties dans `exp/out/`. Ce dossier est temporaire : pour garder les scripts, il faut les copier ailleurs (par exemple un dossier `research/` hors du bot).

| Script | Contenu |
|---|---|
| `common.py` | chargement des prédictions + Pinnacle Shin + prix S2, Δ log-loss avec IC bootstrap par soirée, règle de verdict |
| `h0_books.py` | sharpness de chaque book et du consensus US (§3.1) |
| `h1_market.py` | contrôle de la baseline, H1, H2, H4 |
| `h3_select.py`, `h3b_buckets.py`, `h3c_chrono.py` | simulations des règles de sélection (reproduit +120,9 / +1,6 U) ; réussite par tranche d'écart ; mêmes règles avec le modèle trié par date |
| `h5_extract_xg.py`, `build_feat_xg.py`, `h5_importance.py` | extraction des métriques MoneyPuck (730 155 matchs-joueurs), features xG, importance |
| `wf.py`, `h_compare.py`, `h_bet_variants.py` | walk-forward des variantes (base, xg, xglite, pois, pop, wt, randcal, pidcal ; `--algos lgbm,xgb,cat` pour l'ensemble), comparaison dont H10, impact pari |
| `h17_order.py` | ordre des lignes : harnais (par joueur) vs prod (par date), calibrations sur l'ensemble |
| `fetch_boxscores.py`, `h6_build.py` | boxscores 2021-25, features gardien et voyage |
| `fetch_refs.py`, `h9_refs.py`, `fetch_edge.py` | arbitres et NHL EDGE |
| `h_incr.py` | test d'information incrémentale (goalie, travel, refs, edge, xg) |
| `h13_mlp.py`, `h13_gpu.py` | réseau tabulaire, GPU |
| `h14_fr.py`, `h14_stale.py`, `h14_required_edge.py` | books FR vs Pinnacle (export VPS) ; value des cotes FR figées ; écart de probabilité requis |
| `h15_sources.py` | accès et format des sources candidates |
| `h16_kelly.py` | fractions de Kelly |
| `poll_rosterspots.py`, `poll_rightrail.py` | relevés en direct du 07/10 |

Ordre de lancement : `h5_extract_xg.py` → `h1_market.py` → `wf.py base` (crée le cache de features) → les autres dans n'importe quel ordre (`fetch_*` avant `h6_build.py`, `h9_refs.py` et `h_incr.py`).

## Annexe B — Sources

- Données : [MoneyPuck](https://moneypuck.com/data.htm) (non commercial, à citer) et son [miroir](https://github.com/mattkravec/moneypuck-data) ; API NHL ([référence non officielle](https://github.com/Zmalski/NHL-API-Reference)) ; [Daily Faceoff](https://www.dailyfaceoff.com/starting-goalies) ; [The Odds API](https://the-odds-api.com/liveapi/guides/v4/) (historique des props depuis le 03/05/2023, instantanés de 5 min, coût 10 × marchés × régions).
- Marché : [Kaunitz et al., 2017](https://arxiv.org/abs/1710.02824) (battre les books avec leurs propres cotes, puis être limité) ; [Unabated sur les props NFL](https://unabated.com/post/the-biggest-mistake-youre-making-when-betting-nfl-player-props) ; [étude de sharpness des props MLB](https://www.smartstake.app/learn/sharpest-sportsbooks-mlb-player-props) ; plafond légal du TRJ à 85 % ([ANJ](https://anj.fr/taxonomy/term/228)).
- Méthodes : [Baker & McHale](https://www.researchgate.net/publication/262425087_Optimal_Betting_Under_Parameter_Uncertainty_Improving_the_Kelly_Criterion) (Kelly sous incertitude) ; [xG ajusté au talent du tireur et du gardien](https://arxiv.org/abs/2511.07703) ; [benchmark de calibration sur petits échantillons](https://zenodo.org/records/20140793).
- Contexte ligue 2026-27 : [84 matchs](https://www.espn.com/nhl/story/_/id/49376073/nhl-releases-expanded-84-game-schedule-2026-27-season) ; buts en cage vide ([25 ans de données](https://jschwabish.substack.com/p/empty-net-goals-have-skyrocketed)).
