# Synthèse : phases P0 → P3 et ROI simulé

*2026-10-04. Le détail complet (par marché, tranche de cote, sensibilité au prix) est dans [roi_by_phase.md](roi_by_phase.md) et [roi_by_phase.csv](roi_by_phase.csv).*

## Protocole

- **Données combinées.** `nhl/data/{goalies,lines,skaters,teams}_all.csv` regroupe 2008 à 2025. Il s'agit de la fusion des fichiers `*_2008_to_2024.csv` et `*.csv`, régénérée automatiquement si une source change.
- **Logs de match.**
  - MoneyPuck 2008-2024 : 730 155 matchs-joueurs.
  - API NHL 2025-26 : 1 312 matchs, collectés automatiquement.
  - Les deux sources ont le même schéma. Leur parité a été vérifiée sur 140 matchs : stats identiques à 99,98-100 %, TOI PP corrélé à 0,99.
- **Cotes.** Base brute The Odds API (oct. 2023 → janv. 2025), avec 67 088 cotes buteur et 29 173 cotes passeur rattachées par `playerId`. La probabilité Pinnacle sans marge (no-vig) est disponible pour 37 % des cotes buteur et 96 % des cotes passeur.
- **Walk-forward.** Retrain trimestriel, uniquement sur le passé.
  - Validation : saison 2023-24.
  - Test : oct. 2024 → janv. 2025, jamais utilisé pour régler quoi que ce soit.
- **Cote d'exécution.** Médiane des soft books × 0,94, qui approche Winamax.
- **Edge marché.** Moyenne de (p_no-vig Pinnacle × cote − 1) sur les paris pris. C'est l'EV « vue par le marché sharp ».

## Résultats (prix d'exécution × 0,94)

| Phase | Ce qui change | Paris | **ROI total** | IC 95 % | ROI val | ROI test | Edge marché | LL modèle vs Pinnacle (val, passes) |
|---|---|---|---|---|---|---|---|---|
| Baseline | pipeline d'origine | 223 | **−2,1 %** | [−23 ; +21] | −15,2 % | +6,5 % | −13,2 % | 0,6391 vs 0,6361 (moins bon) |
| P0 | ailiers L/R réintégrés, correctifs bloquants | 288 | **+7,2 %** | [−18 ; +37] | −16,8 % | +20,6 % | −11,9 % | idem |
| P1a | features à parité train/serve, D exclus du buteur, 2009-2026 | 91 | **+17,4 %** | [−31 ; +79] | −3,0 % | +61,7 % | −9,6 % | 0,6368 vs 0,6361 |
| P1b (LGBM) | sans repondération, isotonique temporelle | 125 | +6,6 % | [−29 ; +47] | +4,5 % | +13,7 % | −11,4 % | **0,6335 vs 0,6361 (meilleur)** |
| P1b (ensemble) ✅ | idem, LGBM + XGB + CatBoost | 99 | **+22,3 %** | [−22 ; +78] | +4,7 % | +87,9 % | −11,0 % | **0,6333 vs 0,6361 (meilleur)** |
| P2 réglé par grille ❌ | seuils optimisés sur le ROI de validation | 108 | +22,8 % | [−1 ; +48] | +32,9 % | **−57,0 %** | −10,6 % | sur-apprentissage |
| **P2 a priori ✅** | mélange modèle/Pinnacle (w appris en log-loss), EV ≥ 5 %, Kelly sans plancher, plafond par match | 157 | **+26,0 %** | **[+0,2 ; +55]** | +25,0 % | +31,1 % | −8,9 % | — |
| P3 | config de prod finale + monitoring, tests, timezone, CLV | 157 | **+26,0 %** | [+0,2 ; +55] | +25,0 % | +31,1 % | −8,9 % | identique à P2 ✔ |

Sensibilité au prix (ROI total, P2 a priori) : médiane brute **+13,1 %** sur 830 paris, IC [+3,8 ; +22,7] ; meilleure cote +7,7 %.

## Lecture honnête

1. **Le modèle a vraiment progressé.** Il était moins bon que Pinnacle en log-loss sur les deux marchés. Après P1 :
   - **passes** : il est meilleur que Pinnacle (0,6333 contre 0,6361), avec une AUC de 0,624 contre 0,618 ;
   - **buts** : il est au niveau de Pinnacle (0,5567 contre 0,5574).

   C'est le gain le plus solide de tout le chantier, parce qu'il ne dépend pas du hasard des résultats.
2. **Le ROI monte d'une phase à l'autre (−2,1 % → +26 %), mais avec un bruit énorme.** Avant P2, aucun intervalle de confiance n'exclut zéro. P2 a priori est la première configuration dont l'IC sur toute la période est (de justesse) positif.
3. **La stratégie réglée sur le ROI de validation sur-apprend.** Elle passe de +33 % en validation à −57 % en test. Les seuils de prod sont donc fixés a priori ; seul le poids w est appris, et sur la log-loss.
4. **Contradiction non résolue.** L'edge mesuré contre Pinnacle reste **négatif (−9 %)** alors que le ROI réalisé est positif. Deux explications sont possibles : le modèle bat vraiment Pinnacle sur ces paris (cohérent avec le point 1), ou bien c'est de la chance (passes en test : −59 % sur 15 paris). Seule l'accumulation de paris réels avec CLV permettra de trancher.
5. **Levier structurel.** La médiane des soft books est en moyenne **9-10 % sous la cote juste Pinnacle** : le marché des props joueurs est très margé. La meilleure cote disponible bat la cote juste Pinnacle dans 42 % des cas en buteur. Comparer plusieurs bookmakers (sites légaux FR) rapporterait probablement plus qu'un meilleur modèle.

## Recommandation

- Garder **`paper_trading = true`** au moins 300 paris, ou jusqu'à ce que le CLV moyen (Winamax pris / clôture) soit positif.
- Suivre chaque semaine : CLV, EV de clôture vs Pinnacle no-vig, ROI avec IC. Le snapshot T−5 par match est en place.
- Ne relâcher le kill-switch que si **CLV > 0 et IC du ROI > 0** sur les paris réels.
