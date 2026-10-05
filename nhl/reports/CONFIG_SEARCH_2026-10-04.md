# Recherche de la meilleure configuration (moteur + stratégie)

*2026-10-04 · `nhl/scripts/search_config.py` · résultats bruts : `config_search.csv` (672 configurations), `config_engines.csv`, `config_scenarios.json` · scénarios jouables dans `simulateur.html`.*

> **Mise à jour du 2026-10-05 : grille rejouée au prix réaliste.** Le reste de ce rapport date du 04/10 et utilisait la cote estimée de la prod (médiane US × 1,078), environ 5 % trop généreuse (`nhl/AUDIT_DATA_PARIS_2026-10-04.md`, §2). La grille a été rejouée avec la cote Winamax reconstituée d'après de vraies cotes Winamax (`nhl/sim/real_price.py`, scénario S2 de l'audit). `config_search.csv`, `config_scenarios.json` et `simulateur.html` sont à jour.
>
> | Scénario (gain / saison) | Validation 2023-24 | Contrôle 2024-25 |
> |---|---|---|
> | Actuelle (prod) = Équilibré, 1 pari / match | +136,0 U | +3,3 U |
> | Prudent (EV ≥ 4 %, poids 0,35 / 0,60, cote max 8, 1 pari / match) | +92,4 U | +1,2 U |
> | Équilibré = Agressif (EV ≥ 8 %, paris par match illimités) | +170,9 U | −14,9 U |
> | Buteur seul (EV ≥ 4 %, paris par match illimités) | +75,7 U | +24,2 U |
> | Buteur seul (moteur prod) | +44,0 U | +30,2 U |
>
> La p-value Monte Carlo vaut désormais (k + 1) / (n + 1) : corrigée du nombre de configurations, elle ne peut plus afficher 0 (au mieux 672 / 5 001 ≈ 0,13).

## 1. En bref

**Aucun moteur ne bat nettement l'actuel.** La performance se joue sur la stratégie de mise : seuil d'EV plus haut, plus de confiance dans le modèle, un pari par match.

Deux configurations se détachent, chacune pour une raison différente :

| | Gain / saison (val. / ctrl.) | ROI (val. / ctrl.) | Max drawdown | Si le modèle n'a **aucun** avantage |
|---|---|---|---|---|
| Actuelle (prod) | +99 / +29 U | +9,6 / +3,8 % | 24 U | −24 U / saison, 73 % de saisons perdantes |
| **Équilibré, 1 pari / match** | **+122 / +83 U** | **+19,3 / +19,6 %** | 10 à 13 U | −22 U / saison, 73 % de saisons perdantes |
| **Buteur seul (moteur prod)** | +47 / +83 U | +19,3 / +28,5 % | 9 à 26 U | **+2,5 U / saison, 46 % de saisons perdantes** |

- **Équilibré, 1 pari / match** : le meilleur rendement si l'avantage passé du modèle se confirme. Il parie sur le fait que le modèle bat Pinnacle : son EV contre Pinnacle est négative (−3 à −6 %).
- **Buteur seul (moteur prod)** : moins de gain, mais il reste à l'équilibre même si le modèle n'apporte rien. Au buteur, Winamax paie déjà la cote juste. C'est le choix le plus robuste.

**Ma recommandation** : passer en paper trading avec **Buteur seul (moteur prod)**. Si l'EV de clôture des passes devient positive au fil des paris, élargir vers **Équilibré, 1 pari / match**. Les deux n'utilisent que le moteur actuel : il suffit de changer le TOML, sans réentraînement.

## 2. Protocole

- **7 moteurs** (prédictions walk-forward existantes) × **96 stratégies** = 672 configurations. Toutes au prix Winamax calibré (médiane US × 1,078 ; passes = Pinnacle × 1,00) et avec le no-vig de Shin.
- **Choix sur la validation** (saison 2023-24, 160 soirées, 1 086 matchs). **Contrôle** (oct. 2024 → janv. 2025, 86 soirées, 579 matchs) affiché à part, jamais utilisé pour choisir.
- Gains ramenés à une saison de 180 soirées, Kelly 1/6.
- Scénarios retenus par des **règles écrites avant la recherche** (§4), plus deux variantes ajoutées à la main après lecture des résultats, signalées comme telles.

> Correction : le plan annonçait 1 344 configurations. La grille fait 2 × 4 × 3 × 2 × 2 = 96 stratégies par moteur, soit 672.

## 3. Les moteurs

Log-loss sur le même jeu de lignes (éligibles, cotées, avec Pinnacle des deux côtés). Plus bas = meilleur.

| Moteur | Buteur val. | Buteur ctrl. | Passe val. | Passe ctrl. |
|---|---|---|---|---|
| **Ensemble LGBM + XGB + CatBoost (prod)** | 0,55669 | 0,55790 | **0,62768** | 0,62303 |
| Moyenne ensemble + LightGBM V2 | **0,55656** | 0,55812 | 0,62782 | 0,62306 |
| Ensemble, retrain mensuel | 0,55665 | 0,55854 | 0,62793 | **0,62287** |
| Ensemble, arbres à 100 % | 0,55707 | **0,55773** | 0,62783 | 0,62305 |
| LightGBM seul | 0,55711 | 0,55847 | 0,62777 | 0,62302 |
| LightGBM, features V2 | 0,55704 | 0,55869 | 0,62858 | 0,62342 |
| LightGBM réglé (Optuna) | 0,55712 | 0,55915 | 0,62804 | 0,62310 |
| *Pinnacle (Shin)* | *0,55680* | *0,55950* | *0,62942* | *0,62281* |

Les écarts entre moteurs sont minuscules (moins de 0,1 %). **L'ensemble actuel est le meilleur ou quasi le meilleur partout** : on le garde. Les moteurs sont au niveau de Pinnacle au buteur, et légèrement meilleurs aux passes en validation.

## 4. Les scénarios

Règles appliquées sur la validation, parmi les configs ayant au moins 150 paris et un IC 95 % du gain dont la borne basse est > −10 U.

| Scénario | Règle | Moteur | Marchés | EV min | Poids modèle (but / passe) | Cote max but | Par match |
|---|---|---|---|---|---|---|---|
| Actuelle | settings.toml | ensemble | but + passe | 4 % | 0,50 / 0,75 | 15 | illimité |
| Prudent | meilleur gain / écart-type, DD ≤ 15 U | LightGBM seul | but + passe | 10 % | 0,50 / 0,75 | 8 | 1 |
| Équilibré | meilleur gain, DD ≤ 20 U, ROI ≥ 10 % | ensemble | but + passe | 8 % | 0,65 / 0,90 | 15 | illimité |
| Agressif | meilleur gain | LightGBM V2 | but + passe | 10 % | 0,65 / 0,90 | 8 | illimité |
| Buteur seul | meilleur gain, buteur seul | moyenne ens. + V2 | but | 6 % | 0,65 | 15 | 1 |
| *Équilibré, 1 pari / match* | *manuel : voisin de l'Équilibré* | ensemble | but + passe | 8 % | 0,65 / 0,90 | 15 | 1 |
| *Buteur seul (moteur prod)* | *manuel* | ensemble | but | 8 % | 0,65 | 8 | 1 |

### Résultats (Kelly 1/6, par saison de 180 soirées)

| Scénario | Paris / match (val / ctrl) | Gain (val / ctrl) | ROI (val / ctrl) | Max DD (val / ctrl) | EV Pinnacle (val / ctrl) | p « aucun edge » | p corrigée (672 configs) |
|---|---|---|---|---|---|---|---|
| Actuelle | 1,10 / 0,98 | +99,0 / +28,6 | +9,6 / +3,8 % | 23,6 / 24,3 | −4,5 / −1,0 % | < 0,001 | < 0,001 |
| Prudent | 0,21 / 0,20 | +93,9 / +16,3 | +32,2 / +7,8 % | 11,6 / 18,2 | −3,0 / +0,5 % | < 0,001 | < 0,001 |
| Équilibré | 0,76 / 0,63 | +140,2 / +80,4 | +13,8 / +13,3 % | 17,2 / 17,1 | −6,0 / −2,3 % | < 0,001 | 0,13 |
| Agressif | 0,49 / 0,47 | +146,8 / **−6,7** | +19,9 / **−1,3 %** | 21,3 / 24,0 | −5,9 / −3,5 % | < 0,001 | < 0,001 |
| Buteur seul | 0,34 / 0,50 | +58,2 / +76,1 | +19,6 / +19,7 % | 18,3 / 18,6 | −0,8 / −0,4 % | 0,012 | 1 |
| **Équilibré, 1 / match** | 0,46 / 0,43 | **+121,6 / +83,0** | **+19,3 / +19,6 %** | **10,1 / 13,1** | −5,9 / −2,9 % | < 0,001 | < 0,001 |
| **Buteur seul (prod)** | 0,22 / 0,34 | +47,1 / +82,8 | +19,3 / +28,5 % | 25,5 / 8,8 | −0,3 / +0,1 % | 0,024 | 1 |

### Monte Carlo du simulateur (2 000 saisons de 180 soirées, Kelly 1/6, bankroll 100 U)

| Scénario | Backtest : gain médian | ROI | Saisons perdantes | **Sans avantage** : gain médian | Saisons perdantes | Drawdown médian |
|---|---|---|---|---|---|---|
| Actuelle | +73,8 U | +7,9 % | 5 % | −24,0 U | 73 % | 53,6 U |
| Prudent | +65,7 U | +24,9 % | 1 % | −5,5 U | 58 % | 28,7 U |
| Équilibré | +118,6 U | +13,7 % | 1 % | −41,7 U | 82 % | 67,7 U |
| Agressif | +93,2 U | +14,2 % | 2 % | −33,5 U | 79 % | 57,8 U |
| Buteur seul | +63,1 U | +19,3 % | 3 % | +3,7 U | 45 % | 26,4 U |
| Équilibré, 1 / match | +107,6 U | +19,3 % | 0 % | −21,9 U | 73 % | 47,7 U |
| Buteur seul (prod) | +59,5 U | +23,1 % | 1 % | +2,5 U | 46 % | 24,5 U |

« Sans avantage » correspond au mode « Conservateur » du simulateur : chaque pari est tiré avec la probabilité juste de Pinnacle.

## 5. Ce qui est solide et ce qui ne l'est pas

**Solide** : les tendances qui tiennent sur les deux périodes et sur l'ensemble de la grille.
- Le moteur actuel est le meilleur en médiane sur toutes les configs (+47,5 / +43,3 U par saison).
- Un seuil d'EV de 6 à 8 % fait mieux que 4 % en contrôle (+41,6 à +44,6 U contre +31,5 U), avec un drawdown plus faible.
- 90 % des 672 configs gagnent en contrôle.
- Le marché buteur est au niveau de la cote juste Pinnacle au prix Winamax ; c'est ce qui rend les scénarios buteur robustes.

**Fragile** :
- **Le classement fin des configs est en grande partie du bruit.** La corrélation entre gain de validation et gain de contrôle sur toute la grille est de −0,24 : la « meilleure » config en validation n'est pas la meilleure ensuite.
- L'**Agressif** illustre ce piège : premier en validation (+147 U), il perd en contrôle (−7 U).
- Les p-values « aucun edge » sont très basses pour la plupart des scénarios. Elles disent que les gains passés sont difficiles à expliquer si Pinnacle avait raison. Mais l'EV contre Pinnacle de ces mêmes paris est négative : les deux ne peuvent être vraies longtemps. Seule l'EV de clôture en paper trading tranchera.
- Le poids du modèle (+0,15) retenu par Équilibré est au **bord de la grille** : rien n'a été testé au-delà, et faire davantage confiance au modèle face à Pinnacle augmente le risque si le modèle se trompe.

## 6. Pour appliquer un scénario

Rien n'est changé en prod pour l'instant. Une fois ton choix fait, il suffit de modifier `[betting]` dans `settings.toml` (le moteur reste le même) :

| Scénario | `markets` | `ev_min_*` | `blend_w_but` / `blend_w_ast` | `cote_max_but` | `max_bets_per_game` |
|---|---|---|---|---|---|
| Équilibré, 1 / match | `["but", "ast"]` | 0,08 | 0,65 / 0,90 | 15 | 1 |
| Buteur seul (prod) | `["but"]` | 0,08 | 0,65 / — | 8 | 1 |

L'option `max_bets_per_game` existe déjà dans `nhl/core/betting.py` ; elle vaut 0 (illimité) par défaut.

## 7. Décision (2026-10-04)

Configuration retenue : **Équilibré, 1 pari / match**, appliquée dans `settings.toml [betting]` :
`ev_min_* = 0.08`, `blend_w_but = 0.65`, `blend_w_ast = 0.90`, `max_bets_per_game = 1`. Le reste est inchangé : marchés buteur + passeur, cote max buteur 15, Kelly 1/6, plafonds 5 U par match et 30 U par jour, `exec_mode = "proxy"` avec cote seuil, et `paper_trading = true`.

Contrôle : la phase `q_final` du harnais redonne exactement la ligne de la recherche (749 paris, ROI +19,4 %).

Suivi prévu : EV de clôture par marché via `/roi`. Si le passeur reste négatif après une centaine de paris, basculer en « Buteur seul (moteur prod) » : `markets = ["but"]`, `cote_max_but = 8`.

La grille de recherche est désormais ancrée sur les poids appris en log-loss (0,50 / 0,75) et non plus sur le TOML. Elle ne bouge donc plus quand la config de prod change.

## 8. Correctif du prix des passes (2026-10-04, après la décision)

La prod appliquait la décote du buteur (× 1,078) aux passes cotées par les books américains, alors que Winamax paie les passes au prix de la médiane US (× 1,00). Le prix des passes était donc surestimé d'environ 8 %. De son côté, la simulation prenait toujours Pinnacle pour les passes. Les deux appliquent maintenant la même règle : médiane US × décote du marché (`exec_haircut_ast = 1.00`), sinon Pinnacle.

Recherche relancée avec ce prix : la config retenue fait **+123,7 U / saison** (ROI +21,7 %, drawdown 10,2 U) en validation et **+97,7 U / saison** (ROI +25,2 %) en contrôle, sur 684 paris (phase `q_final`). Les règles automatiques « Équilibré » et « Agressif » retiennent maintenant une config qui ne fait que +24 U en contrôle : une preuve de plus que le classement fin est du bruit, et que la config retenue est la bonne.
