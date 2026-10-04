# Calibration du prix Winamax : 15 matchs réels

*2026-10-04 · scripts `nhl/scripts/parse_winamax_pages.py` et `nhl/scripts/winamax_calibration.py` · résultats bruts : `winamax_calibration.json`.*

## 1. En bref

**Winamax paie nettement mieux que ce que le bot supposait.** Au buteur, sa cote vaut 1,078 fois la médiane des books américains, alors que le bot supposait 0,94. Aux passes, elle est égale à la cote Pinnacle, alors que le bot supposait 0,90.

Les décotes sont donc passées à **`exec_haircut = 1.078`** et **`pin_haircut = 1.00`**, conformément à la règle fixée avant l'analyse. Conséquence simulée sur oct. 2023 → janv. 2025 :

| | Avant calibration | **Après calibration** | Buteur seul (scénario, non adopté) |
|---|---|---|---|
| Paris | 42 | **1 769** | 1 046 |
| Paris par soirée active | ≈ 1,2 | **≈ 7** | ≈ 4 |
| Gain net | +26,1 U | **+101,6 U** [−2,8 ; +202,5] | +63,7 U [−13,7 ; +143,0] |
| ROI | +79,1 % | **+8,0 %** [−0,2 ; +16,1] | +9,7 % [−2,1 ; +22,2] |
| Max drawdown | 2,4 U | **24,3 U** | 27,3 U |
| Edge vs Pinnacle (Shin) | −13,1 % | **−3,5 %** | **+1,4 %** |

**Le volume n'est plus ridicule, mais le risque change d'échelle.** Un drawdown de 24 U correspond à un quart d'une bankroll de 100 U.

**Le marché buteur est le premier signal positif mesuré.** Au prix Winamax réel, son edge contre la cote juste Pinnacle est positif en validation (+1,0 %) comme en contrôle (+1,9 %). Le marché passeur reste à −9,1 %.

## 2. Données

- **Winamax** : 16 pages sauvegardées, soit 15 matchs distincts (1er au 3 octobre 2026 ; la page Edmonton-Seattle était en double). Ce sont les dernières cotes avant le coup d'envoi. Après extraction : 536 cotes buteur, 539 « 1 passe ou plus », 430 « 1 point ou plus ».
- **Référence** : The Odds API historique, instantané 5 minutes avant chaque match, buteur et passes, régions US et EU. **603 crédits** consommés (plafond fixé à 800), il en reste 98 825.
- **Rapprochement** :

| Marché | Cotes Winamax | Avec médiane US | Avec Pinnacle (2 côtés) | Avec résultat |
|---|---|---|---|---|
| Buteur | 536 | 516 | 135 | 512 |
| Passe | 539 | 325 | 145 | 514 |

  Les cotes sans résultat concernent des joueurs non alignés (Zach Hyman, Jake DeBrusk, Bowen Byram…) et les deux Elias Pettersson de Vancouver, volontairement exclus car homonymes.

## 3. Décote réelle de Winamax

IC 95 % par bootstrap sur les matchs.

| Marché | Référence | Médiane Winamax / référence | IC 95 % | Hypothèse avant |
|---|---|---|---|---|
| Buteur | médiane books US | **1,078** | [1,069 ; 1,093] | 0,94 |
| Buteur | Pinnacle « Oui » | **1,00** | [1,00 ; 1,04] | 0,90 |
| Passe | médiane books US | 1,00 | [0,96 ; 1,02] | — |
| Passe | Pinnacle « Oui » | **1,00** | [1,00 ; 1,02] | 0,90 |

**Par tranche de cote (buteur, Winamax / médiane US)** : environ 1,01 sous la cote 2, entre 1,02 et 1,03 de 2 à 4,5, 1,08 de 4,5 à 7, et **1,15 au-delà de 7**. Winamax est surtout généreux sur les longshots. Avec une décote par tranche au lieu d'une décote uniforme, la simulation donne 1 379 paris, +128,4 U, un ROI de +12,7 % et un drawdown de 23,3 U. Ces chiffres sont du même ordre que la décote uniforme.

## 4. Winamax contre la cote juste Pinnacle

EV = probabilité Pinnacle sans marge (Shin) × cote Winamax − 1, sur les lignes où Pinnacle cote les deux côtés.

| Marché | Lignes | EV moyenne | Part à EV > 0 | Part à EV > 4 % |
|---|---|---|---|---|
| Buteur | 135 | −9,6 % | 4,4 % | 1,5 % |
| Passe | 145 | −7,5 % | 4,8 % | 0,7 % |

Prise seule, une cote Winamax est rarement au-dessus de la cote juste. Le bot ne gagne donc que si le modèle sait **quelles** lignes le sont : il ne suffit pas de parier sur toutes les cotes généreuses.

## 5. Le modèle aux vrais prix Winamax (15 matchs)

Toutes les probabilités sont calculées uniquement avec les données antérieures au jour du match. Les filtres de prod sont appliqués, sauf « 10 matchs joués », impossible en début de saison : les joueurs n'avaient joué que 1 ou 2 matchs.

- **Log-loss au buteur** (135 lignes) : modèle 0,595, Pinnacle 0,600, Winamax (prix brut) 0,598. Le modèle fait au moins aussi bien que le marché.
- **Log-loss aux passes** (144 lignes) : modèle 0,668, Pinnacle 0,665, Winamax 0,659. Le modèle fait moins bien que le marché.
- **Paris que le bot aurait pris** : 49 (27 buteur, 22 passeur), mise 39,5 U, gain **+16,3 U**. Leur EV moyenne contre Pinnacle est de −5,8 %.

  Sur 15 matchs, ce gain est du bruit et ne prouve rien. Il confirme seulement que la chaîne complète (extraction, prix, sélection, mise) fonctionne sur des cotes Winamax réelles.

> Un piège évité : sans le filtre « attaquants seulement » au buteur, le modèle sélectionnait des défenseurs à cote 12-15 (Trouba, Middleton…) avec des EV absurdes. Le modèle buteur n'est entraîné que sur des attaquants, et la prod applique bien ce filtre.

## 6. Décision et changements

Règle fixée avant l'analyse : si l'IC 95 % de la décote mesurée exclut la valeur actuelle, la médiane mesurée la remplace.

- `exec_haircut` : 0,94 → **1,078** (IC [1,069 ; 1,093] : exclut 0,94).
- `pin_haircut` : 0,90 → **1,00** (IC [1,00 ; 1,04] : exclut 0,90).
- `simulateur.html` régénéré ; nouvelle phase `q_winamax` dans le harnais ; 83 tests verts.
- Le marché passeur est **conservé**. La règle de P1 (gain de validation positif) reste satisfaite (+40,3 U sur la période). Mais son edge Pinnacle de −9,1 % est le signal à surveiller.

## 7. Limites

- **15 matchs en début de saison**, un seul instantané par match. La décote buteur est solide (516 paires, IC étroit) ; celle des passes repose sur 145 lignes Pinnacle.
- Les cotes Winamax sont celles juste avant le match. Le bot envoie ses picks environ 15 minutes avant : l'écart devrait être faible, mais il n'est pas mesuré.
- Les phases `q_*` antérieures ont été calculées avec 0,94 / 0,90. Les rejouer aujourd'hui donnerait les chiffres calibrés.
- **Variance** : 1 769 paris en 246 soirées, c'est environ 7 paris et 5 U misés par soirée active, avec des pertes de 24 à 27 U possibles en série. Kelly 1/6 et les plafonds limitent les mises, mais pas la durée des séries perdantes.

## 8. Recommandations

1. **Rester en paper trading** et juger sur l'EV de clôture (`/roi`), **séparément par marché**.
2. **Après une centaine de paris passeur**, si leur EV de clôture reste négative, passer en buteur seul (`markets = ["but"]`). Simulé : +63,7 U, edge Pinnacle positif sur les deux périodes, drawdown 27 U.
3. **Refaire cette calibration** une fois par mois avec quelques pages Winamax : coût d'environ 40 crédits par match, script prêt.
4. **Bankroll** : avec un drawdown simulé de 24 U, une unité de 1 % de la bankroll réelle est un maximum raisonnable.
