# Récap : exécution des phases P0 → P3 de l'audit du 2026-10-04

*2026-10-04 · branche `test`, 4 commits (P0 `f677c21`, P1 `dd1f191`, P2 `8440325`, P3 `0b0ec28`), rien de poussé.*
*Audit de départ : [AUDIT_COMPLET_2026-10-04.md](../AUDIT_COMPLET_2026-10-04.md).*

## 1. En bref

**Note : 12,5 → 14 / 20.** Les 4 problèmes critiques de l'audit sont corrigés et testés. La simulation reproduit désormais **exactement** ce que fait le bot en production. Le moteur est plus propre, mieux mesuré, et beaucoup moins variable.

Le prix de cette honnêteté : **le volume chute de 208 à 42 paris** sur la période simulée (oct. 2023 → janv. 2025). Trois raisons :
- le marché passeur est simulé au prix qu'il aura vraiment (Pinnacle × 0,90, seul book à le coter), et non plus au prix des books US ;
- le no-vig Pinnacle de Shin, plus juste que le multiplicatif, montre que le modèle bat rarement Pinnacle ;
- l'éligibilité de la prod est alignée sur celle de la simulation.

**L'edge n'est toujours pas démontré.** Le gain simulé de la config finale (+26,1 U) vient à 64 % d'un seul pari à cote 12,22. Sans lui : +9,3 U sur 41 paris, avec un IC qui contient zéro. **`paper_trading = true` reste obligatoire.** Le critère de passage en réel est maintenant écrit dans le TOML : 300 paris avec une EV de clôture contre Pinnacle dont la borne basse de l'IC 95 % est positive.

| | Avant (config simulée au 04/10) | Prod réelle au 04/10 | **Après P0 → P3** |
|---|---|---|---|
| Paris simulés | 208 | 93 | **42** |
| Gain net | +45,9 U | +23,6 U | **+26,1 U** |
| ROI | +24,9 % | +30,8 % | **+79,1 %** |
| Écart-type du P&L par soirée | 2,26 U | 2,51 U | 3,09 U |
| **Max drawdown** | 10,7 U | 7,8 U | **2,4 U** |
| Edge vs Pinnacle (moyenne) | −8,7 % | −8,4 % | −13,1 % (Shin, plus sévère) |
| Tests automatisés | 40 | 40 | **79** |

---

## 2. Protocole suivi

Pour chaque phase :
1. **Tests d'abord.** Chaque bug a un test qui échoue sur l'ancien code et passe sur le nouveau. Pour P0, les 12 tests ont été vérifiés en échec sur l'ancien code.
2. **`pytest` vert** avant chaque commit.
3. **Mesure** avec `nhl/scripts/simulate_roi.py`, sur des phases `q_*` dont les paramètres sont figés, donc rejouables. Le tableau est produit par `nhl/scripts/compare_phases.py`.
4. **Règle d'adoption fixée avant les résultats** :
   - un correctif de bug est adopté dans tous les cas ;
   - un changement de modèle ou de stratégie n'est adopté que si la log-loss de validation n'est pas pire, que le gain net de validation n'est pas pire, et que le max drawdown ne se dégrade pas de plus de 20 %.
   - La période oct. 2024 → janv. 2025 a déjà servi à choisir des pistes : elle n'est plus qu'un **contrôle** et ne décide de rien.

Nouvelles mesures de variance dans le harnais : IC 95 % du gain net (bootstrap par soirée), écart-type du P&L par soirée, pire soirée, **max drawdown**. Le harnais calcule aussi un **prix « prod »**, qui applique exactement la règle de `apply_proxy` (passes = Pinnacle × 0,90).

**Contrôles de reproductibilité :**
- `q_ref` reproduit la config du 04/10 au pari près (208 paris, +24,9 %).
- Le walk-forward complet ré-entraîné (`q_p1_ref`) reproduit `q_p1_devig` au pari près : le pipeline est déterministe.
- `q_p3`, qui lit la config dans `settings.toml`, est **strictement identique** à `q_p2`, sur toutes les variantes de prix, tous les marchés et toutes les périodes.
- L'ancienne phase historique, rejouée via le nouveau module `nhl/sim/legacy.py`, redonne exactement la ligne « P0 » de la synthèse (288 paris, +7,2 %).

---

## 3. Évolution phase par phase (prix de la prod, tous marchés)

| Phase | Période | Paris | Mise (U) | **Gain net (U)** | IC 95 % gain | **ROI** | IC 95 % ROI | σ / soirée (U) | Pire soirée | **Max drawdown (U)** | Edge Pinnacle |
|---|---|---|---|---|---|---|---|---|---|---|---|
| q_ref | validation | 170 | 154,5 | **+31,8** | [+1,8 ; +63,5] | **+20,6 %** | [+1,2 ; +38,0] | 1,77 | −2,9 | **10,7** | −9,9 % |
| q_ref | contrôle | 38 | 29,5 | **+14,0** | [−12,9 ; +55,3] | **+47,6 %** | [−43,7 ; +183,4] | 3,22 | −1,5 | **7,3** | −2,4 % |
| q_ref | total | 208 | 184,0 | **+45,9** | [+3,8 ; +97,2] | **+24,9 %** | [+2,2 ; +52,1] | 2,26 | −2,9 | **10,7** | −8,7 % |
| q_prod | validation | 68 | 58,0 | **+7,2** | [−12,5 ; +26,7] | **+12,3 %** | [−23,3 ; +42,8] | 1,55 | −2,5 | **6,0** | −11,4 % |
| q_prod | contrôle | 25 | 18,5 | **+16,4** | [−8,3 ; +57,7] | **+88,7 %** | [−47,1 ; +289,4] | 3,62 | −1,5 | **4,3** | +3,9 % |
| q_prod | total | 93 | 76,5 | **+23,6** | [−9,1 ; +69,7] | **+30,8 %** | [−12,7 ; +90,4] | 2,51 | −2,5 | **7,8** | −8,4 % |
| q_p0 | validation | 71 | 59,0 | **+8,9** | [−8,7 ; +29,1] | **+15,0 %** | [−15,8 ; +46,4] | 1,49 | −2,5 | **6,7** | −11,6 % |
| q_p0 | contrôle | 23 | 16,5 | **+19,9** | [−4,5 ; +58,3] | **+120,7 %** | [−28,5 ; +330,5] | 3,82 | −1,5 | **4,3** | +4,5 % |
| q_p0 | total | 94 | 75,5 | **+28,8** | [−3,0 ; +72,6] | **+38,1 %** | [−3,8 ; +95,9] | 2,48 | −2,5 | **6,7** | −8,8 % |
| q_p1 | validation | 30 | 23,0 | **+9,2** | [−2,8 ; +22,6] | **+39,8 %** | [−13,5 ; +87,1] | 1,31 | −1,5 | **2,4** | −17,5 % |
| q_p1 | contrôle | 12 | 10,0 | **+17,0** | [−6,2 ; +54,3] | **+169,5 %** | [−66,2 ; +498,0] | 5,24 | −1,5 | **2,3** | +19,0 % |
| q_p1 | total | 42 | 33,0 | **+26,1** | [−1,6 ; +69,6] | **+79,1 %** | [−5,3 ; +202,7] | 3,09 | −1,5 | **2,4** | −13,1 % |
| q_p2 = q_p3 | total | 42 | 33,0 | **+26,1** | [−1,6 ; +69,6] | **+79,1 %** | [−5,3 ; +202,7] | 3,09 | −1,5 | **2,4** | −13,1 % |

`q_ref` est simulé au prix « médiane soft × 0,94 », comme avant l'audit ; toutes les autres phases au prix réel de la prod. L'edge Pinnacle de `q_p1` et des suivantes est mesuré avec le no-vig de Shin, plus sévère que le multiplicatif : il n'est pas directement comparable aux lignes précédentes.

### Par marché (total de la période)

| Phase | Buteur : paris / gain / ROI / drawdown | Passeur : paris / gain / ROI / drawdown |
|---|---|---|
| q_ref | 52 / +22,8 U / +60,7 % / 5,1 U | 156 / +23,1 U / +15,8 % / 15,6 U |
| q_prod | 55 / +20,3 U / +50,6 % / 5,1 U | 38 / +3,3 U / +9,1 % / 7,5 U |
| q_p0 | 52 / +22,8 U / +60,7 % / 5,1 U | 42 / +6,0 U / +15,8 % / 7,6 U |
| q_p1 → q_p3 | 16 / +21,6 U / +172,4 % / 2,3 U | 26 / +4,6 U / +22,2 % / 4,1 U |

### Ce qu'il faut en lire

- **L'écart simulation ↔ prod était énorme.** La config affichée à +45,9 U ne valait que +23,6 U au prix et avec les règles réelles de la prod. Presque tout l'écart vient du marché passeur : 156 paris simulés contre 38 réellement jouables.
- **P0 récupère un peu de gain** (+5,2 U) en alignant l'éligibilité, et réduit le drawdown.
- **P1 divise le drawdown par près de 3** (6,7 → 2,4 U) à gain de validation égal. C'est le gain le plus solide de la série. Il vient d'un no-vig plus juste : le multiplicatif surestimait le « Oui » (buteur : 26,7 % prédit contre 24,9 % observé), ce qui gonflait des EV illusoires.
- **La variance par soirée augmente** (σ 2,48 → 3,09 U), parce qu'il y a moins de paris et des cotes plus hautes. Le risque de ruine baisse pourtant (drawdown et pire soirée en baisse).
- **Concentration** : un seul pari buteur à 12,22 rapporte +16,8 U sur +26,1 U. Il existe dans toutes les phases depuis l'origine : c'est ce même pari qui gonflait le « ROI test » de l'audit initial.

---

## 4. Décisions prises par les règles fixées à l'avance

| Décision | Règle | Mesure | Verdict |
|---|---|---|---|
| Garder le marché passeur au prix de prod | gain de validation > 0 et IC du ROI pas entièrement négatif | +5,7 U, IC [−25,9 ; +55,4] % | ✅ conservé (mais edge Pinnacle −18,6 % : à surveiller en paper) |
| No-vig Pinnacle | meilleure log-loss en validation 2023-24 | Shin : 0,54833 (but) et 0,62926 (passe) contre 0,54902 / 0,62984 pour le multiplicatif | ✅ **Shin** |
| Poids du mélange modèle / Pinnacle | réappris en log-loss de validation | 0,65 → **0,50** (but), 0,80 → **0,75** (passe) | ✅ (pipeline vérifié : le multiplicatif redonne exactement 0,65 / 0,80) |
| Arbres ré-entraînés sur 100 % (`refit_full`) | log-loss et gain de validation non pires | log-loss but 0,5571 > 0,5567 ; gain val +4,3 < +9,2 U | ❌ rejeté (option conservée, désactivée) |
| Poids et isotonique sur deux moitiés (`split_calib`) | idem | gain val −25,4 U, drawdown 30 U | ❌ rejeté : l'isotonique sur un bloc deux fois plus petit se décalibre et fait sur-parier |

---

## 5. Ce qui a été fait

### P0 : correctifs bloquants (commit `f677c21`)
- **Historique tronqué** : `FeatureEngine.refresh` refuse de servir si les logs commencent après le 2009-10-01. Le bot alerte sur Telegram et n'émet aucun pick.
- **Gate du retrain hebdomadaire** : la comparaison se fait seulement sur les lignes postérieures au `train_cutoff` du modèle en place, avec au moins 2 000 lignes, sinon le modèle en place est conservé. Le résultat du gate est envoyé sur Telegram.
- **Cotes** : `/events` est filtré par date (fenêtre de la soirée) et par affiche exacte. Le match du lendemain d'un back-to-back n'est plus mélangé à celui du soir.
- **Éligibilité** : les matchs joués de la saison sont calculés depuis les logs (le CSV retombait sur la saison précédente). Les passeurs sont éligibles à domicile et à l'extérieur, comme en simulation.
- **Paris annulés** : un joueur absent du boxscore d'un match terminé donne un pari `void`, mise rendue. La résolution se fait par `playerId` (nouvelle colonne). Le portefeuille distingue les marchés : le bug connu des `pick_id` buteur / passeur qui se chevauchent est corrigé.
- Import absolu dans `updater.py` ; dates du portefeuille en heure de Paris.

### P1 : mesure fiable (commit `dd1f191`)
- `shared/devig.py` : dévig multiplicatif, additif, power et Shin ; Shin en prod.
- `/roi` affiche l'**EV de clôture** contre Pinnacle et le verdict de passage en réel (`[mode] go_live_min_bets = 300`).
- La période oct. 2024 → janv. 2025 est déclarée « contrôle uniquement » dans le harnais et dans `PISTES_AMELIORATION.md`.
- Profil PSI recalculé sur la population réellement servie (ATOI ≥ 13, ≥ 10 matchs), sans ré-entraîner : prédictions vérifiées identiques.
- `simulateur.html` utilise maintenant le prix et le dévig de la prod.

### P2 : information (commit `8440325`)
- Options `refit_full` et `split_calib` du modèle, évaluées puis rejetées ; `params` appliqué aussi à XGBoost et CatBoost.
- `nhl/core/odds_logging.py` : à chaque vague, journalisation de la ligne de total de buts, des cotes 1N2 (probabilité de Shin) et des gardiens titulaires (table `match_context`), pour de futures features.
- Cotes points et tirs cadrés journalisées derrière `[betting] log_extra_markets = false` (désactivé, comme décidé).

### P3 : dette technique (commit `0b0ec28`)
- `nhl/sim/legacy.py` regroupe l'ancien modèle, l'ancien Kelly 1/8 et l'ancien seuil d'EV. Ils servent seulement aux phases historiques, aux scripts de recherche et au dashboard Streamlit hérité.
- Code mort supprimé : `shared/kelly.py`, `nhl/core/kelly.py`, `train_production_models.py`, `ensemble_*.joblib`, fonctions mortes de `market_filter`, seuils OMEGA et section `[kelly]` du TOML, colonnes héritées des logs.
- `nhl/core/odds.py` : adaptateur NHL des cotes. **`shared/` n'importe plus rien de `nhl/`** (vérifié par un test).
- CI versionnée (`.github/workflows/tests.yml`), Python 3.12, sur `main` et `test`.
- Dashboard : publication sur la branche `dashboard-data` via un clone séparé. Le bot ne committe plus dans le dépôt de code.
- Exceptions silencieuses remplacées par des erreurs typées et loggées (vérifié par un test).

---

## 6. Bugs découverts en cours de route

| Bug | Effet | Correction |
|---|---|---|
| Noms d'équipes de The Odds API : « Montréal Canadiens », « St Louis Blues », « Utah Mammoth » | aucune cote n'était récupérée pour les matchs de Saint-Louis, Montréal et Utah, déjà avec l'ancien appariement par sous-chaîne (vérifié) | comparaison via `nhl_team_key` (noms normalisés → abréviation), testée |
| `tune_betting.py` réécrivait `betting_params_p1b_ens.json` | les phases historiques `p2*` auraient changé de paramètres | fichier séparé par méthode de dévig |
| Les phases historiques lisaient `home_only` dans le TOML | rejouer `baseline` après P0 donnait 590 paris au lieu de 288 | éligibilité historique figée dans `phases.py` |
| L'ancienne `baseline` (223 paris) contenait le bug des ailiers | n'est plus reproductible, puisque le bug est corrigé dans le code partagé | documenté ; le rejeu redonne la ligne « P0 » (288 paris) |
| Les modèles servis ont été picklés avant l'attribut `params` | `repr()` scikit-learn plante (les prédictions sont correctes) | noté ; disparaîtra au prochain ré-entraînement |

---

## 7. Tests

| Étape | Tests | Ajouts |
|---|---|---|
| Départ | 40 | — |
| Après P0 | 52 | historique, gate, events de cotes et alias d'équipes, matchs de la saison, `home_only`, void, `pick_id` par marché, import |
| Après P1 | 65 | dévig (4 méthodes), méthode de prod, EV de clôture et verdict, profil PSI |
| Après P2 | 73 | options du modèle, `params` XGB / CatBoost, résumé des lignes de match, option désactivée = aucun appel API, journalisation |
| Après P3 | **79** | `shared/` sans `nhl/`, aucune exception silencieuse, code mort absent, rejeu du code hérité, CI versionnée, publication du dashboard sur un dépôt local |

---

## 8. Évolution des notes

| Axe | 03/10 | 04/10 (audit) | Après P0 | Après P1 | Après P2 | **Après P3** | Fait qui justifie la dernière note |
|---|---|---|---|---|---|---|---|
| Architecture logicielle | 12 | 13 | 13 | 13 | 13 | **15** | `shared/` indépendant (testé), code hérité isolé, plus de code mort en prod |
| Data & features | 6 | 13 | 14 | 14 | 14,5 | **14,5** | garde-fou d'historique, GP depuis les logs, contexte de match journalisé ; pas encore de feature de marché entraînable |
| Modélisation ML | 11 | 14 | 14 | 14 | 14 | **14** | modèle inchangé : les deux variantes testées ont été rejetées sur mesure |
| Validation & backtest | 7 | 10 | 11 | 13 | 13,5 | **13,5** | simulation = prod (non-régression stricte), variance et drawdown mesurés, contrôle figé, pipeline déterministe ; échantillon toujours petit |
| Stratégie de pari | 8 | 12 | 12,5 | 13,5 | 13,5 | **13,5** | no-vig de Shin, mélange réappris, drawdown ÷ 3 ; edge non démontré |
| MLOps / prod / monitoring | 7 | 10 | 12 | 13 | 13 | **14** | gate correct, void, cotes fiables, PSI pertinent, KPI EV de clôture, dashboard hors du dépôt |
| Tests & qualité | 4 | 11 | 13 | 13,5 | 14 | **15** | 79 tests, CI versionnée en Python 3.12 |
| **Note globale** | **8,5** | **12,5** | **13** | **13,5** | **13,5** | **14** | |

**Pourquoi pas plus.** Le moteur est maintenant fiable et honnête sur lui-même, mais il n'a pas démontré d'edge contre le marché. Au-delà de 15/20, il faudra : une EV de clôture positive sur au moins 300 paris réels, et des features que Pinnacle n'intègre pas déjà (le contexte de match commence à être collecté).

---

## 9. Ce qui reste à faire

**Actions manuelles sur le VPS** (je n'y ai pas accès) :
1. Vérifier que `nhl/data/gamelogs/mp_gamelogs.parquet` est présent. Sinon, le bot alertera sur Telegram et n'émettra **aucun** pick, ce qui est voulu.
2. Le premier export du dashboard crée `../bet2-dashboard` et la branche `dashboard-data` ; le VPS doit pouvoir pousser sur le remote. Si le dépôt est privé, le front en ligne retombera sur `data.json` (dernier snapshot du dépôt).
3. Pousser `test` puis fusionner dans `main` (= déploiement) quand tu le décides.

**Reporté, avec raison** :
- Cotes historiques 2025-26 : non téléchargées (environ 80 000 crédits), comme tu l'as décidé. Le paper trading sert de test.
- Features de marché (total implicite, gardien titulaire) : pas d'historique pour les entraîner. La collecte démarre avec P2 ; il faudra une saison de données.
- `xg_model_*.pkl` et `lr_model_ast.pkl` sont conservés : deux scripts de recherche (`estimate_ev.py`, `find_optimizations.py`) les chargent encore.
- Le dashboard Streamlit `nhl/dashboard.py` applique toujours l'**ancienne** stratégie (Kelly 1/8, seuils hérités). Il fonctionne, mais ses chiffres ne reflètent pas le bot actuel.

**Prochaines étapes** :
1. Paper trading au moins jusqu'au critère du TOML : 300 paris, borne basse de l'IC de l'EV de clôture > 0 (`/roi`).
2. Surveiller le marché passeur : son edge Pinnacle simulé est de −18,6 %. S'il reste négatif en EV de clôture après une centaine de paris, le retirer (`markets = ["but"]`).
3. Après une saison de collecte, entraîner et évaluer les features de contexte de match avec le même protocole.
