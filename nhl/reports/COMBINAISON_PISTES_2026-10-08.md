# Combiner les pistes prometteuses : de combien le moteur s'améliore ?

*2026-10-08 · branche `test` · aucune modification du bot (ni code, ni modèle, ni réglage). Tests faits à côté, avec les données du dépôt, l'API NHL publique et 13 291 crédits The Odds API pour les cotes 2025-26. Suite de [TESTS_PISTES_PINNACLE_2026-10-07.md](TESTS_PISTES_PINNACLE_2026-10-07.md).*

---

## En une phrase

**Mises ensemble, les pistes prometteuses rendent le moteur un peu plus précis, et c'est confirmé sur une saison qu'il n'avait jamais vue. Assez pour passer devant Pinnacle au buteur, pas assez pour que la différence se voie déjà en euros.**

## Les 3 chiffres à retenir

1. **Passes : amélioration réelle.** Sur la saison 2025-26, jamais vue, le moteur combiné fait **−0,96 millinat** par joueur évalué par rapport au moteur actuel, fourchette [−1,55 ; −0,36]. Toute la fourchette est sous zéro : ce n'est pas de la chance.
2. **Buteur : le moteur combiné passe devant Pinnacle.** Sur 2025-26, le moteur actuel était à **égalité** avec Pinnacle (−0,03 millinat). Mélangé aux cotes de Pinnacle comme le fait le bot, il gagnait −0,64, sans preuve. Le moteur combiné mélangé fait **−1,16, fourchette [−1,93 ; −0,35] : il bat Pinnacle**.
3. **En argent, impossible de trancher en une saison.** Sur les buteurs 2025-26, au vrai prix des books français, le moteur actuel aurait gagné **+44,5 U** et le moteur combiné **+28,4 U**. Ça semble contredire les points 1 et 2, mais une saison de ~500 paris varie naturellement de **±42 U** (un écart-type) : ces deux chiffres sont statistiquement identiques. Les deux moteurs sont gagnants sur cette saison, sans que ce soit une preuve.

**Le meilleur compromis mesuré** : trois pistes, la calibration lisse, le réseau de neurones et le xG sur la glace (§4, « C2 + C4 + C5 »). Sur 2025-26, l'amélioration est réelle aux **deux** marchés : buteur −0,61 [−1,10 ; −0,16], passes −0,85 [−1,32 ; −0,36]. Attention, pour le buteur, ce choix a été fait après avoir vu les résultats : il faudra le confirmer en paper trading.

---

## Comment lire ce document

Tu n'as pas besoin de connaître les statistiques pour suivre. Sept notions suffisent.

**1. Ce que fait le moteur.** Pour chaque joueur et chaque match, le moteur annonce une probabilité, par exemple « 27 % de chances que McDavid marque ». Il ne dit jamais « il va marquer ». Le bot parie quand cette probabilité, multipliée par la cote d'un book français, dépasse 1,08 : c'est une « EV de +8 % ».

**2. La note du moteur : la log-loss.** Pour savoir si ces probabilités sont bonnes, on les compare à ce qui s'est vraiment passé. La log-loss est une **note de pénalité** :
- annoncer 90 % pour un but qui n'arrive pas coûte très cher ;
- annoncer 25 % pour un but qui n'arrive pas coûte peu ;
- **plus la note est basse, meilleur est le moteur.**

C'est comme noter un météorologue sur ses probabilités de pluie : on ne lui reproche pas un jour de pluie annoncé à 30 %, mais on le pénalise lourdement s'il annonçait 95 % de soleil.

**3. Le millinat (mnat).** Les écarts entre deux moteurs sont minuscules, alors on les compte en millièmes de note : **1 mnat = 0,001 point par joueur évalué**, environ 0,2 % de la note totale. « −1 mnat » paraît dérisoire. C'est pourtant à peu près l'écart qui sépare le moteur de Pinnacle, le bookmaker le plus précis du monde. Dans ce métier, un millinat est une vraie différence.

**4. Pinnacle, la référence.** Pinnacle est le bookmaker dont les cotes sont les plus justes. En retirant sa marge, on obtient sa probabilité « juste ». **Battre Pinnacle**, c'est avoir une meilleure note que lui sur les mêmes joueurs. Le bot ne parie jamais avec sa seule probabilité : il la **mélange** avec celle de Pinnacle (65 % modèle, 35 % Pinnacle au buteur), et c'est ce mélange qui compte.

**5. La fourchette [a ; b].** Chaque chiffre vient avec une fourchette de confiance à 95 % :
- toute la fourchette sous 0, par exemple [−2,1 ; −0,3] : **l'amélioration est réelle** ✅ ;
- fourchette qui traverse 0, par exemple [−1,2 ; +0,4] : **le gain peut venir du hasard** 🟡 ;
- valeur positive : le changement dégrade le moteur ❌.

**6. Trois saisons, et pourquoi la dernière compte le plus.**
- **2023-24** et **2024-25** : les pistes ont été choisies en regardant ces deux saisons (rapport du 07/10). Y mesurer leur combinaison, c'est réviser avec le corrigé : les chiffres sont flatteurs.
- **2025-26** : une saison complète que personne n'avait regardée pour choisir les pistes. C'est **l'examen**. Les vraies cotes buteur de cette saison ont été achetées pour pouvoir aussi y comparer le moteur à Pinnacle et simuler les paris.

**7. L'argent.** La simulation rejoue les paris que le bot aurait pris, avec ses vraies règles (EV ≥ 8 %, Kelly 1/6, plafonds), au prix réaliste des books français : la cote Winamax reconstituée, faute d'historique de cotes françaises. Une saison, ce sont quelques centaines de paris : **la chance pèse énormément** (§6). Le **z** mesure à quel point le résultat dépasse ce que prévoyaient les probabilités de Pinnacle : au-delà de 2, c'est difficile à expliquer par la seule chance.

---

## 1. Ce qu'on a combiné

Toutes les pistes jugées **validées ou prometteuses** le 07/10, sauf celles qui ne se mesurent pas sur le passé (§8).

| Code | Piste | En clair |
|---|---|---|
| **C1** | Réglage fin sur un échantillon tiré au hasard | Aujourd'hui, le moteur garde les 15 % de matchs les plus récents pour corriger ses probabilités, et n'apprend donc jamais dessus. C1 garde plutôt 15 % de matchs tirés au hasard : le moteur apprend sur toutes les saisons, y compris la dernière. |
| **C2** | Correction lisse (Platt) | La correction actuelle (« isotonique ») est un escalier : elle donne exactement la même probabilité à des joueurs différents. C2 la remplace par une courbe lisse. |
| **C3** | Compter les buts (Poisson) | Ajoute un modèle qui prédit un nombre de buts (0, 1, 2…) au lieu d'un simple oui / non. |
| **C4** | Un deuxième cerveau (réseau de neurones) | Ajoute un réseau de neurones, qui raisonne autrement que les arbres de décision du moteur ; on fait la moyenne des deux avis. |
| **C5** | La qualité des occasions (xG en saison) | Ajoute 12 statistiques de qualité de tir de la saison en cours, dont les occasions créées par l'équipe quand le joueur est sur la glace. |

Le point de départ, **M0**, est le moteur **tel que le bot le sert aujourd'hui**, recalculé sur les mêmes données que les variantes. (Les simulations publiées avant le 07/10 utilisaient un moteur légèrement différent : voir le défaut « H17 » du rapport précédent.)

Les combinaisons comparées :
- **M_tout** : les 5 pistes ensemble, sur les deux marchés ;
- **M_ciblé** : seulement les pistes jugées prometteuses pour chaque marché le 07/10 (buteur : C1 + C2 + C3 + C4 ; passes : C2 + C4 + C5) ;
- **C2 + C4 + C5** : le meilleur compromis apparu en analysant les résultats (§4).

Pour le xG de la saison 2025-26, les données ont été **reconstruites** à partir des tirs publiés par MoneyPuck et des présences sur la glace de l'API NHL. Avant de s'en servir, la reconstruction a été comparée aux vraies données MoneyPuck sur 300 matchs de 2024-25 : corrélation de **0,976 à 0,9996** selon la statistique, moyennes quasi identiques. Elle est fiable, ce qui prouve aussi que le xG est faisable en production.

---

## 2. Résultat 1 : la qualité des prévisions, piste par piste

On ajoute les pistes une par une, dans un ordre fixé à l'avance. **Les étapes se cumulent** : la ligne « + C2 » contient C1 et C2, la ligne « + C3 » contient C1, C2 et C3, etc. Chaque ligne donne l'écart de note avec le moteur actuel M0, en millinats (**négatif = mieux**). La barre visualise le gain sur 2025-26, la saison qui compte (1 bloc = 0,1 mnat).

### Buteur

| Étape | 2023-24 | 2024-25 | **2025-26 (l'examen)** | | Verdict 2025-26 |
|---|---|---|---|---|---|
| M0, moteur actuel | 0 | 0 | **0** | | — |
| + C1 échantillon au hasard | −0,69 | +0,14 | **−0,33** [−0,91 ; +0,27] | ███ | 🟡 |
| + C2 correction lisse | −1,00 | −0,20 | **−0,47** [−0,93 ; +0,02] | █████ | 🟡 |
| + C3 compter les buts | −1,05 | −0,31 | **−0,47** [−0,93 ; +0,02] | █████ | 🟡 |
| + C4 deuxième cerveau | −1,38 | −0,44 | **−0,37** [−0,89 ; +0,14] | ████ | 🟡 |
| + C5 xG = **M_tout** | −1,07 | −0,60 | **−0,49** [−1,02 ; +0,03] | █████ | 🟡 |
| **C2 + C4 + C5** (§4) | −0,72 | −0,65 | **−0,61** [−1,10 ; −0,16] | ██████ | ✅ |

**Lecture.** Au buteur, chaque marche améliore un peu la note, mais la fourchette frôle zéro sans le franchir franchement : c'est **probable, pas prouvé**. Seul le paquet C2 + C4 + C5 passe la barre, et il a été repéré après coup. Au buteur, le moteur gagne donc environ un demi-millinat.

### Passes

| Étape | 2023-24 | 2024-25 | **2025-26 (l'examen)** | | Verdict 2025-26 |
|---|---|---|---|---|---|
| M0, moteur actuel | 0 | 0 | **0** | | — |
| + C1 échantillon au hasard | −0,63 | −0,76 | **−0,19** [−0,71 ; +0,35] | ██ | 🟡 |
| + C2 correction lisse | −0,57 | −0,71 | **−0,54** [−1,04 ; −0,05] | █████ | ✅ |
| + C3 compter les passes | −0,71 | −0,75 | **−0,55** [−1,04 ; −0,08] | ██████ | ✅ |
| + C4 deuxième cerveau | −0,60 | −0,51 | **−0,65** [−1,18 ; −0,15] | ███████ | ✅ |
| + C5 xG = **M_tout** | −0,84 | −1,08 | **−0,96** [−1,55 ; −0,36] | ██████████ | ✅ |
| M_ciblé passes = C2 + C4 + C5 | −0,40 | −0,78 | **−0,85** [−1,32 ; −0,36] | █████████ | ✅ |

**Lecture.** Aux passes, le gain se construit marche après marche et **tient sur la saison jamais vue** : presque un millinat entier avec toutes les pistes. C'est l'amélioration la plus solide de toute l'étude.

---

## 3. Résultat 2 : qui apporte quoi dans la combinaison ?

On repart du moteur complet et on **retire une piste à la fois**. Si le moteur se dégrade sans elle, elle était utile. Chiffre = millinats perdus quand on la retire (**positif = la piste aide**).

| Piste retirée de M_tout | Buteur 2023-24 / 2024-25 / **2025-26** | Passes 2023-24 / 2024-25 / **2025-26** | Ce qu'il faut en retenir |
|---|---|---|---|
| C1 échantillon au hasard | +0,30 / −0,09 / **−0,15** | +0,42 / +0,33 / **+0,12** | utile aux passes ; au buteur, plutôt nuisible en 2025-26 |
| C2 correction lisse | +0,13 / +0,04 / **+0,09** | −0,05 / +0,48 / **+0,24** | utile aux deux, surtout aux passes |
| C3 compter les buts | +0,02 / −0,00 / **+0,02** | +0,02 / +0,08 / **−0,01** | **n'apporte rien** une fois les autres là |
| C4 deuxième cerveau | +0,26 / +0,24 / **+0,16** | −0,22 / +0,25 / **+0,07** | utile au buteur, régulièrement |
| C5 xG | −0,31 / +0,16 / **+0,12** | +0,23 / +0,58 / **+0,31** | **la plus utile aux passes**, et un peu au buteur en 2025-26 |

**En résumé :**
- **Le xG (C5)** est le meilleur ajout aux passes.
- **Le deuxième cerveau (C4)** aide le buteur.
- **La correction lisse (C2)** aide un peu partout et supprime les « paliers » : avec M0, seulement 112 probabilités différentes entre 15 % et 50 % au buteur ; avec la correction lisse, plus de 14 000.
- **Compter les buts (C3)** ne sert plus à rien en combinaison : à abandonner.
- **L'échantillon au hasard (C1)** aide les passes mais pas le buteur.

---

## 4. Le meilleur compromis : C2 + C4 + C5

En retirant ce qui n'aide pas (C3 partout, C1 au buteur), il reste **correction lisse + deuxième cerveau + xG**, la même formule pour les deux marchés. Elle avait été définie à l'avance pour les passes (« M_ciblé passes ») ; pour le buteur, on l'a repérée en lisant le §3.

| C2 + C4 + C5 | Buteur | Passes |
|---|---|---|
| vs moteur actuel, 2025-26 | **−0,61** [−1,10 ; −0,16] ✅ | **−0,85** [−1,32 ; −0,36] ✅ |
| vs moteur actuel, 2023-24 / 2024-25 | −0,72 / −0,65 | −0,40 / −0,78 |
| Mélange avec Pinnacle vs Pinnacle, 2025-26 | **−1,20** [−1,92 ; −0,46] ✅ | (pas de cotes passes achetées) |

C'est le paquet qu'on recommanderait d'ajouter au bot. Comme le choix a été fait en partie après avoir vu 2025-26, il doit être **confirmé en paper trading** avant d'y mettre de l'argent.

---

## 5. Résultat 3 : contre Pinnacle

Écart de note avec la probabilité juste de Pinnacle, sur les buteurs que Pinnacle cotait (13 737 lignes en 2025-26). « Modèle seul » = la probabilité du moteur. « Mélange » = ce que le bot utilise vraiment : 65 % moteur, 35 % Pinnacle.

| Moteur | Modèle seul, 2025-26 | **Mélange, 2025-26** | Mélange, 2024-25 |
|---|---|---|---|
| M0, moteur actuel | −0,03 [−1,24 ; +1,17] : égalité | **−0,64** [−1,44 ; +0,15] 🟡 | −1,17 [−2,22 ; −0,15] |
| M_tout | −0,85 [−2,02 ; +0,37] | **−1,16** [−1,93 ; −0,35] ✅ | −1,48 [−2,51 ; −0,51] |
| C2 + C4 + C5 | −1,00 [−2,09 ; +0,13] | **−1,20** [−1,92 ; −0,46] ✅ | −1,54 [−2,52 ; −0,61] |

**Lecture.** Sur la saison jamais vue, le moteur actuel n'arrive pas à prouver qu'il bat Pinnacle. Le moteur combiné, mélangé à Pinnacle, **le bat avec une fourchette entièrement négative**.

On peut aussi réapprendre le dosage du mélange pour chaque moteur, au lieu de garder 65 / 35. Avec un dosage appris sur 2023-25 puis appliqué à 2025-26 :
- moteur actuel : −0,70 [−1,32 ; −0,09] ;
- M_tout : −1,16 [−1,99 ; −0,29].

Même conclusion. Le dosage appris pour M_tout est de 70 % moteur, 30 % Pinnacle : le moteur combiné mérite un peu plus de confiance que l'actuel (50 / 50).

---

## 6. Résultat 4 : en argent

Paris simulés avec les vraies règles du bot, au prix Winamax reconstitué, bankroll de 100 U. **2025-26** : buteurs seulement (les seules cotes achetées).

| Moteur | Buteur seul, 2025-26 | Règle « gros désaccord », 2025-26 | Config de prod (buteur + passes), 2023-24 / 2024-25 |
|---|---|---|---|
| M0, moteur actuel | 517 paris, **+44,5 U**, ROI +14,0 %, z 1,1 | 73 paris, +4,1 U | +96,0 U / +16,4 U |
| M_tout | 496 paris, **+28,4 U**, ROI +9,9 %, z 0,8 | 62 paris, −2,4 U | +43,9 U / +5,6 U |
| M_ciblé | 516 paris, **+26,6 U**, ROI +8,8 %, z 0,7 | 29 paris, +2,8 U | +87,0 U / −0,4 U |

**Pourquoi le meilleur moteur ne gagne pas plus.** Ce n'est pas une contradiction, c'est la chance :
- **Une saison de ~500 paris a un écart-type d'environ 42 U.** Un moteur parfaitement identique, rejoué sur une autre saison, pourrait aussi bien faire +5 U que +85 U. +44 et +28 sont donc statistiquement le même résultat.
- **Démonstration involontaire.** Pendant l'étude, le moteur actuel a été recalculé sur la carte graphique au lieu du processeur. Ses probabilités ont changé de moins d'1 point en moyenne, et sa note est restée la même à 0,3 millinat près. Pourtant, sur 2023-24, ses paris simulés passent de **+39 U à +96 U**. Quelques paris à grosse cote qui basculent d'un côté ou de l'autre du seuil suffisent.
- **Conséquence.** Les euros d'une saison ne peuvent pas départager deux moteurs aussi proches. Il faudrait des milliers de paris. La note (log-loss), elle, se mesure sur toutes les lignes évaluées (~18 000 au buteur, ~30 000 aux passes en 2025-26) : c'est pour ça qu'on la croit davantage.

**La bonne nouvelle** : tous les moteurs testés sont **gagnants sur la saison jamais vue** au vrai prix des books français. C'est encourageant mais pas une preuve (z ≈ 1). En revanche, la règle « gros désaccord » ne se confirme pas sur 2025-26 : gains autour de zéro.

---

## 7. Résultat 5 : des probabilités plus fiables

« 25 % » doit vouloir dire « 1 fois sur 4 ». Réussite observée sur 2025-26, par tranche de probabilité annoncée (buteur) :

| Probabilité annoncée | M0 : annoncé → observé | M_tout : annoncé → observé |
|---|---|---|
| 15 à 20 % | 17,1 % → 18,1 % | 17,5 % → 18,5 % |
| 20 à 25 % | 21,9 % → 23,1 % | 22,5 % → 22,2 % |
| 25 à 30 % | 26,9 % → 27,4 % | 27,4 % → 27,4 % |
| 30 à 35 % | 32,9 % → 33,7 % | 32,3 % → 32,1 % |

Les deux moteurs sont bien réglés. Le moteur combiné colle encore mieux dans la zone où le bot parie le plus (20 à 35 %). Et surtout, il ne met plus des dizaines de joueurs sur la même probabilité : 14 569 valeurs différentes entre 15 et 50 %, contre 112 pour M0.

---

## 8. Ce qui ne se mesure pas encore

Trois pistes validées le 07/10 ne peuvent pas être chiffrées sur le passé :
- **Feuille de match officielle** : l'API NHL publie les 20 joueurs habillés entre 24 et 18 minutes avant le match. Elle évite de parier sur un joueur retiré au dernier moment. C'est de la **sécurité**, pas de la précision.
- **Lignes et unités d'avantage numérique Daily Faceoff** : aucun historique n'existe. Il faut d'abord les enregistrer chaque jour pendant 2 à 3 mois, puis les tester.
- **Lenteur des books français** : ils ne suivent pas toujours les mouvements de Pinnacle, mais leur marge (~12 %) absorbe ces écarts. Attente faible.

---

## 9. Ce que ça change pour le bot

**Si tu décides d'améliorer le moteur**, voici ce qu'il faudrait faire, du plus simple au plus lourd :
1. **Correction lisse (C2)** : changer une ligne de calibration dans le modèle. Effort faible.
2. **Deuxième cerveau (C4)** : ajouter un réseau de neurones à l'ensemble, entraîné sur le même PC (environ 2 minutes par entraînement). Effort moyen.
3. **xG sur la glace (C5)** : nouveau pipeline de données qui télécharge chaque nuit les tirs MoneyPuck (miroir public, usage non commercial) et les présences de l'API NHL. Il a été prototypé et vérifié pendant cette étude. Effort élevé.
4. Ne pas ajouter **compter les buts (C3)**, inutile en combinaison.
5. Réentraîner, puis aligner le simulateur sur le bot (défaut H17), pour que les projections décrivent enfin le moteur servi.

**Côté argent, rien ne change** : les simulations ne permettent pas de dire qu'un moteur gagne plus qu'un autre. Rester en paper trading, juger sur la note (log-loss contre Pinnacle sur toutes les lignes évaluées) plutôt que sur le ROI, et garder « buteur seul » comme choix prudent.

| Décision | Ce que ça apporte, d'après les tests | Risque | Ton choix |
|---|---|---|---|
| Ajouter C2 + C4 + C5 au moteur | ✅ −0,6 mnat au buteur, −0,85 aux passes sur 2025-26 ; bat Pinnacle au buteur (mélange) | choix partiellement a posteriori → valider en paper | ☐ |
| Ajouter seulement C2 (correction lisse) | 🟡 −0,27 au buteur, −0,24 aux passes sur 2025-26 ; le mélange avec Pinnacle bat déjà Pinnacle au buteur (−0,87 [−1,63 ; −0,09] ✅) ; quasi gratuit | faible | ☐ |
| Abandonner C3 (compter les buts) | n'apporte rien combiné | aucun | ☐ |
| Garder l'échantillon au hasard (C1) seulement aux passes | utile aux passes, pas au buteur | moyen | ☐ |

---

## 10. Défauts découverts en route

- **`build_odds_table.py`** ne reconnaît pas « Montréal Canadiens » (avec accent), le nom qu'utilise désormais The Odds API : les 82 matchs de Montréal disparaissaient du parsing 2025-26. Contourné en mémoire pour cette étude, non corrigé dans le dépôt. La prod n'est pas touchée : elle utilise `nhl_team_key`.
- **`nhl/sim/phases._p1_load`** (chargeur du simulateur) met à 0 la feature « matchs joués » sur toutes les saisons à partir de 2025-26. Sans effet sur les simulations déjà publiées, mais tout futur test sur 2025-26 avec ce chargeur serait faux. Cette étude a reconstruit les features comme le fait la prod.

---

## Glossaire

| Mot | En clair |
|---|---|
| **Calibration** | Faire en sorte que « 30 % » veuille vraiment dire « 3 fois sur 10 ». |
| **Isotonique** | Méthode de calibration actuelle : une courbe en escalier, d'où des « paliers » où plusieurs joueurs reçoivent la même probabilité. |
| **Platt** | Autre méthode de calibration : une courbe lisse en S. |
| **Ensemble** | Plusieurs modèles dont on mélange les avis (ici LightGBM, XGBoost, CatBoost, et le réseau de neurones). |
| **Réseau de neurones** | Famille de modèle qui « pense » différemment des arbres de décision. |
| **xG (expected goals)** | Qualité d'un tir : la probabilité qu'il devienne un but, selon sa position, son type, etc. |
| **xG sur la glace** | xG de toute l'équipe pendant que le joueur est sur la glace : les occasions créées par sa ligne. |
| **Walk-forward** | Test honnête : le moteur n'apprend que sur le passé, puis prédit la suite, comme en vrai. |
| **U (unité)** | Unité de mise : 1 U = 1 % de la bankroll de départ des simulations. |
| **ROI** | Gain divisé par la somme misée. |
| **z** | De combien d'« écarts-types » le gain dépasse ce que prévoyait Pinnacle. Au-delà de 2 : difficile à attribuer à la chance. |
| **Écart-type** | Ampleur normale des variations dues au hasard. |
| **Prix S2** | Cote Winamax reconstituée à partir de Pinnacle et des books américains. |

---

## Annexe — Méthode et reproduction

- **Protocole.**
  - Chaque moteur est entraîné uniquement sur le passé, aux mêmes dates que le simulateur du bot, plus trois dates pour 2025-26 (1er octobre, 1er janvier, 1er avril).
  - Notes comparées sur les lignes que le bot aurait évaluées (règles d'éligibilité de la prod) : 13 728 / 6 887 lignes buteur et 15 144 / 8 062 lignes passes en 2023-24 / 2024-25 ; 18 214 lignes buteur et 30 361 lignes passes en 2025-26.
  - Fourchettes : bootstrap par soirée, 95 %.
  - Ordre de l'escalier, contenu de M_tout et de M_ciblé fixés avant les calculs (plan du 08/10).
- **Contrôles.**
  - La référence « simulations publiées » redonne exactement les chiffres du rapport du 07/10 : +120,9 / +1,6 U pour la config de prod.
  - Le moteur actuel recalculé (XGBoost et CatBoost sur la carte graphique) a la même note que la version processeur à ±0,3 mnat.
  - Le cadre de features reconstruit est identique au cache du simulateur sur les 686 004 lignes jusqu'en 2024-25.
  - Le xG 2025-26 reconstruit a une corrélation de 0,976 à 0,9996 avec MoneyPuck (300 matchs de 2024-25).
- **Coûts.** 13 291 crédits The Odds API pour les cotes buteur 2025-26 (1 312 matchs, instantané ~15 minutes avant le match, Pinnacle + 7 books américains). Il en reste 84 869. Environ 4 h de calcul sur le PC.
- **Scripts** (scratchpad de la session, hors dépôt) :
  - `fetch_odds_2025.py`, `odds_2025_parse.py` : cotes 2025-26 ;
  - `build_feat_full.py` : features ;
  - `xg_rebuild.py`, `xg_parity.py` : xG 2025-26 et contrôle de parité ;
  - `combo_members.py` : entraînement des modèles ;
  - `combo_eval.py`, `combo_summary.py` : combinaisons, notes, paris et tableaux.

  Dossier : `C:\Users\2507m\AppData\Local\Temp\claude\c--Users-2507m-Desktop-Milan-code-bet2\2d32c04b-1c0d-4265-9841-c36f90afae80\scratchpad\exp\`.
