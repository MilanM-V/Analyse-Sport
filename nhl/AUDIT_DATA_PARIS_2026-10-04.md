# Audit data et paris sportifs : moteur NHL

*2026-10-04 · branche `test` (commit `9fc83fe`) · angle : data analyst senior et parieur quantitatif.*
*Fait suite à [AUDIT_COMPLET_2026-10-04.md](AUDIT_COMPLET_2026-10-04.md), au [récap P0 → P3](reports/RECAP_AUDIT_P0_P3_2026-10-04.md) et aux rapports [Winamax](reports/WINAMAX_CALIBRATION_2026-10-04.md), [recherche de config](reports/CONFIG_SEARCH_2026-10-04.md) et [mode découverte](reports/EARLY_SEASON_2026-10-04.md).*
*Les chiffres des §2 à §4 se reproduisent avec `python nhl/scripts/audit_price_sensitivity.py` (§9).*

Les audits précédents portaient surtout sur l'ingénierie : parité train/serve, bugs, tests. Celui-ci pose une autre question : **les chiffres qui justifient la stratégie actuelle tiennent-ils face à un regard de parieur ?** J'ai rejoué le backtest de la config de prod au pari près, testé ses hypothèses une par une, et regardé ce que le bot fait réellement depuis le début de la saison.

## 0. Verdict

**Note : 11,5 / 20** (14 / 20 dans le récap P0 → P3). Le code n'a pas régressé. La note baisse parce que cet audit juge la validité du pari, et que trois hypothèses qui portent les chiffres affichés ne résistent pas à l'examen.

1. **Le gain simulé dépend surtout du prix Winamax supposé.** Le backtest paie chaque pari buteur 1,078 × la médiane des books US. La calibration du 04/10 montre que, sur les lignes où Pinnacle cote les deux côtés (75 % des paris buteur simulés), Winamax paie 1,026 × la médiane US, pas 1,078. Avec un prix segmenté tiré des mêmes données, la période de contrôle passe de **+46,7 U à +3,5 U** (ROI de +25 % à +2 %).
2. **Le seul résultat hors échantillon qui soutenait la config ne survit pas à un prix réaliste.** En contrôle, l'écart au gain attendu par Pinnacle vaut z = +2,2 au prix du backtest, et entre +0,3 et +0,9 aux prix réalistes.
3. **Le modèle est au niveau de Pinnacle, pas au-dessus.** Son avantage en log-loss va de 0 à 0,3 %. Il n'est significatif que dans 1 cas sur 4, et le poids optimal du modèle varie du simple au double d'une saison à l'autre. Le marché passeur fait les deux tiers du gain de validation, puis perd en contrôle (−12 U, ROI −25 %).
4. **Le paper trading actuel ne peut pas trancher.** Le critère de passage en réel (EV de clôture contre Pinnacle > 0) compare deux prix et ne regarde pas les résultats. Or la config choisit, par construction, des paris dont l'EV contre Pinnacle est négative : de −1 % à −11 % selon le prix et la période. Le critère est donc hors de portée de la config actuelle, que le modèle ait raison ou tort. Le bot ne journalise pas non plus les données d'un test qui fonctionnerait.
5. **Le retrain hebdomadaire du VPS entraîne un LightGBM seul**, alors que le moteur validé est l'ensemble LGBM + XGBoost + CatBoost (le LightGBM seul a été rejeté). Dès que son gate passera, probablement à la mi-octobre, la prod changera de moteur sans validation.

**Recommandation.** Rester en paper trading : c'est déjà le cas, et aucun pick n'a été émis depuis le 29/09. Consacrer les prochaines semaines à **mesurer** plutôt qu'à régler : prix Winamax réel, journalisation complète, critère de passage cohérent avec la stratégie (§7). Au prix réaliste, seul le buteur reste positif sur les deux périodes (+15 à +22 U en contrôle, z ≈ 1,1, donc non significatif) : c'est la seule piste qui mérite le paper trading. Retirer le marché passeur. Ne plus raisonner sur les « +123,7 / +97,7 U par saison » affichés dans le TOML, le simulateur et le dashboard.

| Axe | Note | Justification |
|---|---|---|
| Ingénierie et tests | 15 | 110 tests verts ; code de mise partagé entre la prod et la simulation ; dépendances non épinglées ; retrain sur le mauvais moteur |
| Données et features | 14 | Aucune fuite trouvée ; pas encore de feature de marché ; journalisation de prod incomplète |
| Modélisation | 13 | Au niveau de Pinnacle ; avantage mince et instable ; probabilités en paliers |
| Backtest et validation | 9 | Harnais reproductible au pari près, mais prix d'exécution biaisé, contrôle consulté avant le choix, p-values mal rapportées |
| Stratégie de mise | 10 | Kelly 1/6 et plafonds sains ; poids du modèle choisi sur le ROI au bord de la grille ; marché passeur sans preuve ; mode découverte adopté sur du bruit |
| Mesure en paper trading | 7 | Critère hors de portée de la stratégie ; prix Winamax réel non capturé ; aucune référence Pinnacle pour les joueurs non pickés |
| Exploitation (MLOps) | 13 | Bons garde-fous (historique, doublons, void) ; retrain LightGBM seul ; versions non épinglées |
| **Global** | **11,5** | |

---

## 1. État réel du bot au 04/10/2026, 18 h UTC

Source : `db.json` de la branche `dashboard-data`, c'est-à-dire la base du VPS.

- La saison 2026-27 a commencé le 29/09 (34 matchs de saison régulière dans les logs au 03/10).
- **Aucun pick émis** : les tables `picks` et `picks_assists` sont vides, et le portefeuille aussi.
- 478 évaluations de joueurs : 165, 55, 183 et 75 du 1er au 4 octobre.
- Aucun joueur n'a encore joué 10 matchs : seul le mode découverte peut produire des picks, et il n'est actif que depuis le 04/10. Ses filtres expliquent probablement l'absence de pick : EV ≥ 15 % (20 % sans Pinnacle) et l'arrondi de mise (§6, P3).
- Les probabilités servies tombent sur des paliers. Le 04/10, Hertl et Stone ont exactement 0,2878 au buteur, Marner et Eichel 0,5356 aux passes (§6, P2-1).

Au rythme simulé (environ 500 paris par saison, 2,8 par soirée), les 300 paris du critère de passage ne seront pas atteints avant février, et seulement si le mode normal démarre fin octobre.

---

## 2. Le prix Winamax : l'hypothèse qui porte tout

Aucun book français ne cote les props NHL dans The Odds API. Le bot sélectionne et dimensionne donc ses paris sur un **prix proxy** : médiane des books US × 1,078 au buteur et × 1,00 aux passes, repli sur Pinnacle « Oui ». Le backtest utilise la même règle. Ces décotes viennent de 15 matchs Winamax relevés du 1er au 3 octobre.

### 2.1 La calibration, segmentée

Le ratio unique de 1,078 mélange deux populations très différentes.

| Marché | Lignes avec Pinnacle des deux côtés | Autres lignes |
|---|---|---|
| Buteur : Winamax / médiane US | **1,026** (135 lignes) | 1,111 (381 lignes) |
| Passes : Winamax / médiane US | **1,023** (143 lignes) | **0,852** (182 lignes) |

L'écart tient à tranche de cote égale (buteur, cotes 3 à 4,5 : 1,025 contre 1,106 ; cotes 4,5 à 7 : 1,015 contre 1,089). Ce n'est donc pas un effet de longshot : c'est le type de joueur. Winamax est généreux sur les joueurs que Pinnacle ne cote pas (joueurs de profondeur), et aligné sur Pinnacle pour les autres (Winamax / Pinnacle « Oui » = 1,00).

Or **319 des 426 paris buteur simulés (75 %) portent sur des lignes couvertes par Pinnacle**. Pour ces paris, le backtest suppose un prix environ 5 % trop haut, soit plus de la moitié du seuil d'EV de 8 %. Aux passes sans Pinnacle, Winamax paie 15 % de moins que la médiane US, alors que la prod applique × 1,00. En prod, la cote seuil protège : on ne parie pas si Winamax est en dessous. Le biais gonfle donc surtout les projections et le nombre de picks proposés pour rien.

### 2.2 La dérive du marché US

La décote mesurée en 2026 est appliquée aux médianes US de 2023-25. Or le rapport entre books US et Pinnacle a bougé.

| Saison | Buteur : médiane US / Pinnacle « Oui » | Lignes |
|---|---|---|
| 2023-24 (validation) | 0,948 | 15 484 |
| 2024-25 (contrôle) | 0,997 | 9 401 |
| 2026-27 (calibration) | 1,000 | 135 |

Si Winamax suit Pinnacle, comme le montre la calibration, le prix simulé vaut 1,078 × 0,948 ≈ 1,02 × Pinnacle en validation, mais 1,078 × 0,997 ≈ 1,075 × Pinnacle en contrôle. **Le contrôle est la période la plus surévaluée**, alors que c'est elle qui devait servir de preuve.

### 2.3 Le backtest de prod rejoué avec d'autres prix

Config de prod (`settings.toml`, phase `q_final`), mêmes prédictions walk-forward, même `select_bets`. Seule la règle de prix change. Validation : saison 2023-24 (160 soirées). Contrôle : oct. 2024 à janv. 2025 (86 soirées). Le z mesure l'écart entre le gain observé et le gain attendu si Pinnacle avait raison.

| Prix d'exécution | Val. : paris | Val. : gain | Val. : ROI | Ctrl : paris | **Ctrl : gain** | **Ctrl : ROI** | Ctrl : EV Pinnacle | Ctrl : z | Max DD |
|---|---|---|---|---|---|---|---|---|---|
| **S0, backtest actuel** (buteur × 1,078) | 448 | +110,0 U | +21,7 % | 236 | **+46,7 U** | **+25,2 %** | −1,1 % | +2,16 | 10,2 U |
| Décote buteur uniforme × 1,00 | 301 | +76,7 U | +19,2 % | 73 | +8,9 U | +11,2 % | −5,9 % | +0,83 | 16,1 U |
| Décote buteur uniforme × 1,04 | 349 | +89,3 U | +20,6 % | 118 | +16,7 U | +15,0 % | −3,6 % | +1,11 | 14,9 U |
| Décote buteur uniforme × 1,10 | 556 | +112,1 U | +19,1 % | 339 | +46,6 U | +18,2 % | +0,3 % | +1,73 | 14,6 U |
| **S1, prix segmenté** (§2.1) | 484 | +130,1 U | +22,2 % | 196 | **+3,5 U** | **+2,1 %** | −5,4 % | +0,38 | 20,4 U |
| **S2, Winamax = Pinnacle « Oui »** (sinon S1) | 445 | +120,9 U | +24,2 % | 171 | **+1,6 U** | **+1,1 %** | −10,7 % | +0,51 | 13,9 U |
| Prod réaliste S1 : proposé au proxy, pris si prix ≥ seuil | 327 | +109,9 U | +26,8 % | 124 | +16,0 U | +13,8 % | −2,4 % | +0,90 | 14,9 U |
| Prod réaliste S2 : idem | 264 | +75,3 U | +22,8 % | 98 | −0,8 U | −0,9 % | −10,3 % | +0,26 | 16,1 U |

Lecture :
- **La validation reste très positive quel que soit le prix** (+75 à +130 U). C'est la saison qui a servi à tout choisir (§4.3).
- **Le contrôle s'effondre dès que le prix est réaliste** : de +46,7 U à une fourchette de −0,8 à +16 U, et z passe sous 1. Pour que le contrôle reste nettement gagnant, il faut que Winamax paie au moins 4 à 10 % de plus que la médiane US **sur les paris choisis**, ce que la calibration contredit pour les trois quarts d'entre eux.
- Les projections « +123,7 U par saison (validation), +97,7 U (contrôle) » du TOML, de `simulateur.html` et de la carte « projection » du dashboard sont des chiffres S0.

Par marché, aux prix réalistes, les deux marchés se séparent nettement :

| Marché | S1 : validation | S1 : contrôle | S2 : validation | S2 : contrôle |
|---|---|---|---|---|
| Buteur | +16,5 U (z +1,10) | **+21,9 U** (z +1,16) | +41,3 U (z +2,54) | **+15,0 U** (z +1,06) |
| Passes | +113,6 U (z +4,35) | **−18,4 U** (z −0,79) | +79,5 U (z +4,08) | **−13,4 U** (z −0,47) |

Le buteur reste positif sur les deux périodes quel que soit le prix, sans être significatif en contrôle. Les passes gagnent beaucoup une saison, puis perdent la suivante. Le contrôle total proche de zéro est la somme de ces deux mouvements opposés.

Deux points vérifiés sans effet notable :
- **Composition des books.** Le backtest prend tous les books hors Pinnacle, la prod 7 books US. Le ratio médian entre les deux médianes vaut 1,000 ; l'historique est même 0,5 % plus prudent en moyenne.
- **Univers des joueurs.** La prod n'évalue que les joueurs des unités d'avantage numérique listées par RotoWire, le backtest tous les joueurs à ATOI ≥ 13. Seuls 63 paris simulés (9 %) sortent de cet univers, pour −2,6 U.

---

## 3. D'où vient le gain simulé (prix S0)

| Marché | Période | Paris | Gain | ROI | Réussite | p_final moyen | No-vig Pinnacle moyen | Gain attendu si Pinnacle a raison | z |
|---|---|---|---|---|---|---|---|---|---|
| Passes | val. | 222 | +73,4 U | +23,5 % | 48,2 % | 45,4 % | 36,9 % | −23,3 U | **+3,75** |
| Passes | ctrl | 36 | −12,0 U | −25,1 % | 30,6 % | 43,3 % | 34,8 % | −4,3 U | −0,76 |
| Buteur | val. | 226 | +36,6 U | +19,0 % | 32,3 % | 31,9 % | 31,1 % | −0,6 U | +1,76 |
| Buteur | ctrl | 200 | +58,7 U | +42,7 % | 32,5 % | 27,3 % | 28,0 % | +3,0 U | **+2,82** |

- **Passes.** En validation, les paris gagnent 11 points de plus que ce que prévoyait Pinnacle (z = +3,75) ; en contrôle, c'est l'inverse. Sur l'ensemble des lignes, Pinnacle est bien calibré les deux saisons (35,9 % prédit pour 35,1 % observé, puis 34,8 % pour 34,0 %). Il n'y a donc pas de biais de marché exploitable : le modèle a eu raison une saison et tort la suivante. Le poids du modèle aux passes (0,90) est pourtant le plus élevé de la config.
- **Buteur.** Au prix S0, l'EV contre Pinnacle est nulle (−0,2 % en validation, +1,1 % en contrôle) : le pari repose sur le prix supposé (§2). Le gain du contrôle vient d'une réussite au-dessus des attentes (32,5 % contre 28,0 %). C'est le signal le plus intéressant du projet. Au prix réaliste, il diminue sans disparaître : +15 à +22 U en contrôle, z ≈ 1,1 (§2.3).
- **Paris sans référence Pinnacle.** 113 paris (17 %), surtout des buteurs à cote moyenne 7, rapportent 21 % du gain (+33,6 U). Le critère de passage en réel ne peut pas les mesurer (§6, P1-3).
- **Concentration.** Les 5 meilleurs paris font +39,0 U sur +156,7 U ; sans les 10 meilleurs, le gain tombe à +96,4 U. Quatre paris à cote 10 à 16 rapportent +23,1 U.

---

## 4. Le modèle bat-il Pinnacle ?

### 4.1 Sur toutes les lignes éligibles cotées par Pinnacle

Différence de log-loss modèle − Pinnacle (Shin), en millinats par ligne : négatif = modèle meilleur. IC 95 % par bootstrap sur les soirées.

| Marché | Période | Lignes | Δ log-loss | IC 95 % | Poids optimal du modèle (log-loss) |
|---|---|---|---|---|---|
| Passes | val. | 15 144 | −1,74 | [−3,19 ; −0,34] | 0,75 |
| Passes | ctrl | 8 062 | +0,23 | [−1,77 ; +1,98] | 0,45 |
| Buteur | val. | 13 728 | −0,11 | [−1,42 ; +1,18] | 0,50 |
| Buteur | ctrl | 6 887 | −1,60 | [−3,34 ; +0,05] | 0,85 |

- L'avantage est réel par endroits, mais mince : au mieux 1,7 millinat par ligne, soit 0,3 % de la log-loss.
- Il est instable. Le poids optimal passe de 0,75 à 0,45 aux passes et de 0,50 à 0,85 au buteur. Le TOML utilise 0,65 et 0,90 : aux passes, c'est deux fois l'optimum du contrôle.
- Sur les 15 matchs Winamax, aux passes : log-loss du modèle 0,668, Pinnacle 0,665, prix brut Winamax 0,659. Le modèle fait moins bien que les deux books.

### 4.2 Sur les picks

Test de vraisemblance : sur les paris choisis, les résultats donnent-ils raison à `p_final` ou au no-vig Pinnacle ? z > 2 signifie que le modèle a raison.

| Marché | Période | Picks | Écart moyen p_final − Pinnacle | z |
|---|---|---|---|---|
| Passes | val. | 216 | +8,4 pts | +1,98 |
| Passes | ctrl | 36 | +8,5 pts | −1,22 |
| Buteur | val. | 178 | +4,2 pts | +0,13 |
| Buteur | ctrl | 141 | +3,2 pts | +1,64 |

Aucune cellule n'atteint z = 2, et les passes se contredisent d'une période à l'autre.

### 4.3 La recherche de configuration

- **Les p-values corrigées du rapport sont fausses.** `search_config.null_pvalue` tire 5 000 simulations. Pour 5 des 7 scénarios, aucune ne dépasse le gain observé : p = 0, et 0 × 672 = 0 est affiché « < 0,001 » après Bonferroni. La résolution réelle est de 1/5 000, donc la borne corrigée honnête vaut environ 0,13 (0,4 au seuil de 95 %). Avec un z analytique, la config retenue donne en validation p = 2,9·10⁻⁵, soit 0,02 après correction. C'est significatif, mais sur la période où l'on a choisi, parmi 672 configs, celle qui y gagnait le plus : c'est précisément le cas où le gain observé surestime le gain futur.
- **Le contrôle n'est plus vierge.** La config retenue, « Équilibré, 1 pari / match », est une variante ajoutée à la main après lecture des résultats, contrôle compris (CONFIG_SEARCH §2 et §4). Son poids (+0,15) est au bord de la grille.
- Le rapport le dit lui-même : la corrélation entre gain de validation et gain de contrôle sur la grille vaut −0,24. Le classement fin des configs est du bruit.

---

## 5. Le coût d'une erreur, et le temps qu'il faut pour la voir

- **Si Pinnacle a raison**, c'est-à-dire si le modèle n'apporte rien, la config perd **18 à 44 U par saison au prix réaliste** (S2), et 3 à 27 U au prix S0, pour 300 à 570 U misés. Sur une bankroll de 100 U, ce n'est pas un risque de ruine mais une érosion lente.
- **Le ROI réalisé ne tranchera pas en une saison.** Aux cotes jouées, un pari de 1 U a un écart-type de 1,75 U. Détecter un ROI de +5 % à 2 sigmas demande environ 4 900 paris, soit une dizaine de saisons au rythme du bot. Une saison de paper trading positive ou négative ne prouvera rien.
- **Ce qui peut trancher en une saison** : la qualité des probabilités contre Pinnacle, mesurée sur toutes les lignes évaluées (environ 100 par soirée et par marché) et sur les picks (§7).

---

## 6. Problèmes classés

### P0 : à traiter avant de tirer la moindre conclusion

**P0-1. Prix d'exécution simulé surévalué sur la majorité des paris**
- Où : `[betting] exec_haircut = 1.078`, appliqué uniformément par `simulate_roi.add_prod_price`, `search_config.py`, `export_simulator_data.py`, et par `shared/odds_api.apply_proxy` en prod.
- Effet : en contrôle, les projections affichées sont de 3 à 30 fois trop optimistes selon le scénario de prix, voire de signe contraire (§2.3).
- Correctif :
  1. Décote par segment (couverture Pinnacle × tranche de cote), ou prix ancré sur Pinnacle « Oui » quand il existe.
  2. Relancer `search_config.py` avec ce prix.
  3. Afficher une fourchette (S0 / S1 / S2) au lieu d'un seul chiffre dans le TOML, le simulateur et le dashboard.
  4. Recalibrer avec au moins 100 matchs, relevés à T−15 (l'heure réelle des picks) et non à T−5, sur plusieurs semaines de la saison.

**P0-2. Le paper trading ne mesure pas ce qu'il faut**
- `database.closing_ev_summary` calcule `closing_p_novig × cote − 1`. Cette quantité ne dépend pas des résultats : elle dit si l'on a battu le prix juste de Pinnacle. La stratégie, elle, mise là où le modèle contredit Pinnacle, à un prix proche de Pinnacle « Oui ». Son EV de clôture attendue est négative (−1 à −11 %, §2.3) : le critère « borne basse de l'IC > 0 » est hors de portée de la config actuelle, même si le modèle a raison, et il ne teste jamais si le modèle a raison. **Le critère et la stratégie se contredisent : l'un des deux doit changer** (§7).
- La « clôture » est relevée à T−5, une dizaine de minutes après le pick. Les lignes de props bougent peu dans ce délai : ce n'est pas un CLV, c'est l'EV contre Pinnacle au moment du pari.
- Sans `/pris`, la cote retenue est le proxy (`COALESCE(cote_reelle, cote)`). Le paper trading rejoue alors l'hypothèse de prix au lieu de la tester.
- La table `players`, qui enregistre toutes les évaluations, n'a ni `p_novig`, ni `p_model` par marché, ni cote passeur, ni `pin_yes` / `pin_no`. Dans l'export du VPS, ces colonnes sont vides sur les 478 lignes. Impossible, donc, de mesurer le modèle contre Pinnacle sur la centaine de lignes par soirée qui ne deviennent pas des picks.
- `get_roi_stats` calcule un ROI à mise plate, alors que la simulation mise en Kelly : les deux ROI ne sont pas comparables.

**P0-3. Le retrain hebdomadaire change de moteur**
- `services.job_weekly_retrain` lance `train_models.py --live` sans `--algos`, et `DEFAULT_ALGOS = ("lgbm",)`. Le modèle validé (walk-forward, simulateur, recherche de config) est `lgbm+xgb+cat`. Le LightGBM seul avait été rejeté.
- Le gate compare ce LightGBM à l'ensemble en place sur au moins 2 000 lignes postérieures au 16/04/2026. Avec des écarts de log-loss de l'ordre de 0,001, c'est un pile ou face. Ce seuil de lignes sera atteint vers la mi-octobre.
- Si le gate passe, `models/live/` est servi en priorité (`inference.model_path`), mais le simulateur et sa version (`sim/version.py`) ne regardent que `models/`.
- Le job est déclaré « lundi », mais avec python-telegram-bot 22.7, `days=(0,)` signifie **dimanche** (convention changée en v20).
- Correctif : passer `--algos lgbm,xgb,cat`, ou changer `DEFAULT_ALGOS` ; n'accepter un nouveau modèle que si l'IC bootstrap de la différence de log-loss est entièrement négatif ; alerter quand `models/live/` diffère du modèle simulé.

### P1 : stratégie

**P1-1. Marché passeur : aucune preuve hors échantillon**
- En contrôle : −12,0 U (36 paris, z = −0,76) ; log-loss du modèle égale à celle de Pinnacle ; sur les 15 matchs Winamax, modèle moins bon que les deux books. Le poids 0,90 vaut deux fois l'optimum du contrôle.
- C'est pourtant le gain de validation des passes (+73 U) qui a fait gagner la config retenue.
- Correctif : `markets = ["but"]` jusqu'à preuve, ce que recommandait le rapport de config (« Buteur seul (moteur prod) »). À défaut, `blend_w_ast` au poids appris en log-loss sur les deux saisons réunies : 0,65 (0,60 au buteur).

**P1-2. Poids du mélange choisi sur le ROI**
- La grille décale le poids appris en log-loss (0,50 / 0,75) de ±0,15 et garde le meilleur ROI de validation : +0,15, au bord de la grille. Régler un paramètre de probabilité sur le ROI de quelques centaines de paris revient à l'ajuster sur le bruit.
- Correctif : poids appris en log-loss sur une fenêtre glissante de deux saisons, éventuellement tiré vers 0,5. Plafonner l'écart |p_model − p_novig| : au-delà d'environ 10 points, un désaccord avec Pinnacle est plus souvent une erreur du modèle qu'un edge.

**P1-3. Paris sans référence Pinnacle**
- 17 % des paris simulés, cote moyenne d'environ 7, 21 % du gain, et aucune mesure possible en paper (pas de `closing_p_novig`).
- Correctif : estimer un no-vig depuis le seul côté « Oui » de Pinnacle et sa marge moyenne observée, ou suivre ces paris à part, ou les exclure.

**P1-4. Mode découverte adopté sur du bruit**
- Le meilleur des 3 seuils testés en validation rapporte +6,5 U sur 50 picks, pour un écart-type d'environ 8 U. En contrôle : −0,3 U. EV contre Pinnacle négative (−2,3 % et −5,8 %), et gain attendu sans avantage négatif dans les 6 cas.
- La règle d'activation (« au moins un seuil positif en validation ») est très permissive : sans aucun edge, chaque seuil a à peu près une chance sur deux d'afficher un gain positif sur 50 picks (gain attendu de −0,4 à −2,3 U pour un écart-type d'environ 8 U).
- C'est le seul mode actif jusqu'à fin octobre.
- Correctif : le désactiver, ou l'assumer comme pur suivi d'information. Il est déjà exclu du critère de passage.

**P1-5. Dépendances non épinglées**
- `requirements.txt` ne fixe aucune version. Les modèles sont des pickles scikit-learn, LightGBM, XGBoost et CatBoost. Le watchdog lance `pip install -r` à chaque pull. En local : Python 3.14 et scikit-learn 1.8 ; en CI : Python 3.12.
- Un VPS réinstallé peut ne plus charger les modèles, ou charger un isotonique au comportement différent.
- Correctif : fichier de versions figé (pip freeze du VPS), versions enregistrées dans le bundle du modèle, contrôle au chargement.

### P2 : qualité du signal

**P2-1. Probabilités en paliers.** La calibration isotonique produit 33 valeurs distinctes entre 0,15 et 0,45 au buteur, 51 entre 0,25 et 0,65 aux passes. L'écart moyen est de 0,8 à 0,9 point, avec des paliers allant jusqu'à 2,4 points au buteur et 6,7 points aux passes. Le modèle ne distingue pas les joueurs d'un même palier, et l'EV avance par sauts d'environ 3 points autour de p = 0,30. À tester en walk-forward, jugé sur la log-loss : isotonique interpolée, calibration bêta, ou Platt sur le mélange.

**P2-2. Features de marché.** La collecte du total implicite et des cotes 1N2 a commencé (5 lignes dans `match_context`). Plutôt que d'attendre une saison, on peut acheter l'historique h2h et totals de la période backtestée (1 665 matchs). Au pire, à 20 crédits par match (2 marchés, région eu, coût historique × 10), cela fait environ 33 000 crédits sur les quelque 98 000 restants. L'endpoint historique groupé (`/historical/sports/{sport}/odds`), qui renvoie tous les matchs d'un instantané, coûte beaucoup moins : à vérifier sur un appel test. On pourrait alors entraîner un modèle de second niveau (p_model + total implicite de l'équipe + p_novig) sur 2023-25, avec le même protocole.

**P2-3. Compos RotoWire.** D'après `compos_live.txt`, les compos lues sont des blocs de 4 attaquants + 1 défenseur, c'est-à-dire les unités d'avantage numérique. Le parseur ne trouve visiblement pas les blocs « LINE 1 » / « LINE 2 » et applique son repli. L'univers de prod est donc d'environ 10 joueurs par équipe. L'impact sur le backtest est faible (§2.3), mais le comportement doit être corrigé ou documenté. Le gardien est pris sans son statut « confirmé ».

### P3 : hygiène

- **Combinés.** Le « COMBINÉ SÉCURISÉ » est toujours construit et proposé dès que deux picks le permettent, alors que l'audit du 04/10 les disait abandonnés. Le libellé est trompeur : un combiné compose aussi les erreurs d'EV. Ces combinés ne sont jamais résolus (`picks_parlays` est absent de l'updater) et misent 0,25 U fixe. Le combiné « synergie » est mort avec `max_bets_per_game = 1`, et son coefficient × 1,294 suppose que MyMatch paie le produit des cotes, ce qu'il ne fait pas. Les retirer, ou les résoudre et les mesurer.
- **Arrondi des mises.** `round()` arrondit au pair : `round(0.5) = 0`, `round(2.5) = 2`. En mode normal, une mise Kelly doit dépasser 1,5 % de Kelly plein pour atteindre 0,5 U. L'EV exigée monte donc avec la cote : 10,5 % à cote 8, 21 % à cote 15, et ce seuil dépend de la bankroll. En mode découverte, une mise de 0,5 U devient 0 : seuls les paris à Kelly ≥ 1 U passent, soit une EV ≥ 18 % à cote 5. L'effet est plutôt protecteur, mais il n'est ni décidé ni documenté.
- **Documentation périmée.** Le TOML annonce « +83 U en contrôle », chiffre antérieur au correctif des passes (+97,7 U), et l'audit du 04/10 dit les combinés abandonnés.
- **Fenêtres de dates.** `get_roi_stats` et `closing_ev_summary` utilisent `datetime.now()` (fuseau système) au lieu de `paris_now()`.

---

## 7. Protocole de mesure proposé, à fixer avant de regarder les résultats

Objectif : savoir en une saison, et non en dix, si le modèle bat Pinnacle et à quel prix Winamax on exécute réellement.

**D'abord, trancher l'incohérence entre critère et stratégie (P0-2) :**
- **Option A, marché efficient (le défaut prudent).** Garder le critère d'EV de clôture contre Pinnacle, et ne miser que lorsque le prix Winamax réel bat le prix juste de Pinnacle, c'est-à-dire poids du modèle à 0 pour la sélection. Peu de paris (4,4 % des lignes buteur de la calibration étaient à EV > 0, 1,5 % au-dessus de 4 %), mais un edge mesurable et peu variable. Cette option exige le prix Winamax réel.
- **Option B, le modèle bat Pinnacle.** Garder la stratégie, mais juger le modèle sur les résultats (points 3 et 4 ci-dessous), en acceptant beaucoup plus de variance.

**Puis mettre en place la mesure :**
1. **Relever le prix Winamax réel chaque soir.** Sauvegarder les pages Winamax des matchs à l'heure des picks (T−15) et les passer à `parse_winamax_pages.py`. On obtient à la fois la calibration continue de la décote par segment, le prix réel de chaque pick et l'EV réelle.
2. **Journaliser complètement** dans `players`, pour les deux marchés et tous les joueurs évalués : `p_model`, `p_final`, `pin_yes`, `pin_no`, `p_novig`, médiane US et cote proxy.
3. **Critère de modèle.** Différence de log-loss modèle − Pinnacle sur toutes les lignes évaluées avec Pinnacle des deux côtés, avec IC par soirée. Plus le test de vraisemblance `p_final` / `p_novig` sur les picks. Seuil : borne haute de l'IC < 0 et z > 2, après au moins 300 picks.
4. **Critère d'exécution.** EV au prix Winamax réel, calculée contre `p_final` et contre Pinnacle, suivie à part. Le ROI réalisé reste une information, pas un critère (§5).
5. **Passage en réel progressif.** Unité ≤ 0,5 % de la bankroll pendant les 300 premiers paris réels, puis 1 % si les critères tiennent. Aucun réglage de config en cours de saison sur la base du ROI.

---

## 8. Ce qui est solide

- **Reproductibilité.** Le harnais rejoue la config de prod au pari près (684 / 684, +156,7 U). La prod et la simulation partagent `select_bets`. 110 tests passent en 11 s.
- **Pas de fuite.** Une seule fonction de features pour l'entraînement, la simulation et la prod ; `shift(1)` systématique ; moyennes de ligue « à date » ; priors de la saison précédente. Je n'ai trouvé aucune information future dans les features.
- **Référence de marché.** Le no-vig de Shin est le bon choix : Pinnacle est bien calibré (25,4 % prédit pour 25,7 % observé au buteur en 2023-24).
- **Gestion du risque.** Kelly 1/6 sans plancher, plafonds par pari, par match et par jour ; un pari par match, donc pas de corrélation à l'intérieur d'un match.
- **Garde-fous de prod.** Paper trading obligatoire, cote seuil affichée (protection réelle contre un proxy trop optimiste), mode découverte exclu du critère, garde-fou d'historique, résolution `void`, déduplication des picks.
- **Culture statistique.** Période de contrôle déclarée, règles d'adoption écrites à l'avance, rapports qui signalent eux-mêmes leurs fragilités (corrélation −0,24, concentration des gains).
- **Calibration Winamax.** C'est une vraie mesure de terrain (15 matchs, 603 crédits), et c'est elle qui rend cet audit possible. Il faut la prolonger, pas la remplacer.

---

## 9. Annexe : méthode et reproduction

- **Script.** `python nhl/scripts/audit_price_sensitivity.py` est en lecture seule et tourne en une dizaine de secondes. Prérequis, non versionnés : `nhl/reports/preds_q_final.parquet`, `nhl/data/odds/odds_wide.parquet`, `nhl/data/odds/winamax_calibration_rows.parquet`.
- **Prix S1.** Médiane US × ratio Winamax / médiane US du segment : marché × Pinnacle des deux côtés × tranche de cote US. Une tranche de moins de 10 lignes prend le ratio de son segment. Les lignes couvertes par Pinnacle reçoivent un ratio unique, car il ne varie pas d'une tranche à l'autre.
- **Prix S2.** Pinnacle « Oui » × ratio Winamax / Pinnacle (1,00) quand Pinnacle cote, S1 sinon.
- **« Prod réaliste ».** Picks sélectionnés au prix proxy de la prod, gardés seulement si le prix estimé dépasse la cote seuil, puis réglés au prix estimé avec la mise d'origine.
- **z analytique.** Gain observé moins gain attendu si les résultats suivent `p_novig` (ou 1 / cote sans Pinnacle), divisé par l'écart-type sous la même hypothèse.
- **Log-loss.** Lignes éligibles avec Pinnacle des deux côtés ; bootstrap de 2 000 tirages par soirée.
- **État réel du bot.** `git show Analyse-Nhl/dashboard-data:db.json`, export du 04/10 à 18:11 UTC.
- **Tests.** `pytest tests/` : 110 passed.
- **Limites.** La calibration repose sur 15 matchs de la première semaine de saison. Les scénarios S1 et S2 sont des hypothèses plausibles, pas des mesures, et il n'existe aucune cote Winamax historique pour 2023-25. Les conclusions sur le contrôle portent sur 86 soirées.
