# 🔍 Analyse du Backtest Historique : Le mythe des "800 U"

Tu m'as demandé d'être 100% honnête : **Oui, le chiffre de 800 U par saison en backtest était "de la merde" (une illusion statistique).** 

Ce n'est pas que le code du backtest était faux, mais il ne simulait pas les **conditions réelles de production en France**. Voici exactement pourquoi l'ancien backtest affichait des profits délirants et pourquoi la réalité (Winamax) est beaucoup plus difficile.

---

## 🛑 Pourquoi le backtest à 800 U était biaisé

### 1. L'Illusion des Cotes (Le piège ARJEL vs International)
Dans `walk_forward_backtest.py`, le script charge les cotes historiques via `historical_odds_parsed.csv` en utilisant la **médiane des bookmakers internationaux** (Pinnacle, DraftKings, Bet365, etc.). 
- **En Backtest :** Le bot "pariait" sur des cotes internationales sans taxe. (ex: Cote à 2.50)
- **En Production :** Le bot parie sur **Winamax**, qui est soumis à la taxe ARJEL française. Les cotes props joueurs sur Winamax sont **10% à 15% plus basses** que le marché international. (ex: La même cote est à 2.15 sur Winamax).
> *Impact :* Un pari qui avait une EV de +10% en backtest devient un pari à EV Négative en production. C'est la raison **numéro 1** de la différence de P&L.

### 2. Le "Closing Line Bias" (Biais de la ligne de clôture)
L'API historique stocke souvent la cote juste avant le début du match (la ligne la plus affûtée). 
- **En Backtest :** Le modèle regarde la cote parfaite de clôture.
- **En Production :** Le bot prend les cotes le matin ou l'après-midi, quand le marché n'est pas encore formé.

### 3. La boucle "Implied Prob" (Triche involontaire)
Dans nos précédentes conversations, la feature `implied_prob` (1 / cote) avait été ajoutée au modèle.
- Si on donne la cote du bookmaker au modèle pendant son entraînement, il va juste apprendre à "copier" le bookmaker. 
- En backtest, cela donne des scores incroyables. En production, ça ne bat pas la marge (le "juice") du bookmaker, surtout sur Winamax.

### 4. Slippage et Limites de Mise (Kelly irréaliste)
Le backtest simulait des mises Kelly parfaites (parfois 3U, 5U) sur des marchés annexes (Assists, Points). En réalité, les bookmakers limitent rapidement les mises sur ces marchés de niche, et prendre la cote la fait immédiatement baisser (slippage).

---

## 🛠️ Liste des Problèmes Actuels et Comment les Régler

Voici le plan d'action pour transformer le bot d'une "machine à backtest biaisée" en un **vrai bot de production rentable** :

| Problème | Explication | Solution (Fix) |
|---|---|---|
| **1. Fuite d'argent sur les Assists** | Le marché "Passeurs" a un ROI de -6% en live (et un ROI Kelly de -100%). Les cotes Winamax sur les assists sont trop "juicées" (trop de marge bookmaker). | **Désactiver le marché Assists** temporairement dans `bot_logic.py`, ou monter la `cote_min` à 2.50. |
| **2. Le Portfolio n'est jamais mis à jour** | Il y a 34 paris "en attente" dans la DB. Le dashboard affiche toujours 100 U. L'updater résout les paris mais n'appelle pas `portfolio.resolve_bet()`. | Modifier `nhl/core/updater.py` pour qu'il appelle la fonction de résolution du portfolio et mette à jour la bankroll réelle. |
| **3. Les mises Kelly ne sont pas sauvegardées** | Le bot calcule bien la mise (ex: 0.5U), l'envoie sur Telegram, mais enregistre `NULL` dans la DB. | Corriger `nhl/core/logger_csv.py` pour insérer la variable `mise` dans la table `picks`. |
| **4. Feature `opp_goalie_gsax_60` écrasée** | Le dataset historique met cette statistique cruciale du gardien adverse à `0.0` par erreur, la rendant inutile pour le ML. | Corriger la ligne 313 de `build_historical_dataset.py` pour garder la vraie valeur. |
| **5. Blending ML désactivé** | L'Ensemble (XGB + LGBM + CatBoost) a ses poids hardcodés à `[0.33, 0.33, 0.33]` au lieu d'utiliser le solveur d'optimisation. | Réactiver l'optimisation des poids dans `ensemble_model.py`. |
| **6. Crash hebdomadaire silencieux** | Le script Telegram appelle `scripts/recalc_probas.py` chaque lundi, mais ce fichier n'existe pas. | Supprimer ce job de `nhl/core/services.py` ou recréer le script manquant. |

### Conclusion
Le chiffre de 800 U était un mirage mathématique causé par l'utilisation de cotes internationales sans marge ARJEL. En condition réelle sur Winamax, l'Edge (l'avantage) est extrêmement fin. Pour être rentable, il faut arrêter les marchés secondaires peu rentables (Assists) et se concentrer uniquement sur les Buteurs avec une stricte gestion de bankroll.
