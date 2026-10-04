"""
sim/legacy.py — Code de l'ANCIEN pipeline (avant l'audit du 2026-10-03), conservé uniquement
pour rejouer les phases historiques (`baseline`, `p0`, `p1a` de nhl/sim/phases.py), les
scripts de recherche et le dashboard Streamlit hérité (`nhl/dashboard.py`).

Le bot de production n'utilise RIEN de ce module : sa stratégie est `nhl/core/betting.py`
et son modèle `nhl.core.ensemble_model.TemporalCalibratedGBM`.

Contenu (déplacé ici à l'audit P3 du 2026-10-04) :
- NHLEnsembleClassifier (ex-nhl/core/ensemble_model.py) : XGB/LGBM/CatBoost repondérés
  + calibration sigmoïde ;
- calculate_quarter_kelly / is_cote_valid / apply_kelly_to_picks (ex-shared/kelly.py) :
  Kelly 1/8 avec plancher de 0,5 U ;
- get_adaptive_ev_threshold (ex-nhl/core/market_filter.py).
Les constantes sont figées à leurs valeurs historiques ([kelly] du TOML a été supprimé).
"""
import copy
import logging
import os
from typing import Any, Dict, Optional

import numpy as np
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from scipy.optimize import minimize
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

from nhl.config.settings import cfg

logger = logging.getLogger("NHL.Legacy")
NHL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ex-section [kelly] de settings.toml (valeurs historiques figées)
CATEGORY_CAPS: Dict[str, float] = {"BUTEUR": 1.5, "PASSEUR": 2.0, "POINTEUR": 2.0}


class NHLEnsembleClassifier(BaseEstimator, ClassifierMixin):
    """Classifieur d'Ensemble pour les marchés NHL (Buteurs & Passeurs).

    Combine XGBoost, LightGBM et CatBoost via Blending pondéré convexe
    optimisé sur le Brier Score avec validation temporelle stricte.
    """

    def __init__(self, market: str = "but", mode: str = "ensemble", n_splits: int = 3, random_state: int = 42):
        """
        Args:
            market: 'but' ou 'ast'.
            mode: 'ensemble' (blending pondéré des 3) ou 'champion' (sélectionne le meilleur).
            n_splits: Nombre de folds temporels pour TimeSeriesSplit.
            random_state: Seed aléatoire pour reproductibilité.
        """
        self.market = market
        self.mode = mode
        self.n_splits = n_splits
        self.random_state = random_state
        self.models_ = {}
        self.weights_ = None
        self.best_model_name_ = None
        self.calibrated_models_ = {}
        self.classes_ = np.array([0, 1])

    def _load_optimal_params(self) -> Dict[str, Any]:
        """Tente de charger les hyperparamètres Optuna optimaux."""
        import os
        import json
        cfg_path = os.path.join(NHL_DIR, "config", "optimal_hyperparams.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Fallback chain: try exact key first, then {market}_0_5
                    # (JSON uses "but_0_5"/"ast_0_5", but self.market is "but"/"ast")
                    return data.get(self.market) or data.get(f"{self.market}_0_5", {})
            except (OSError, ValueError) as e:
                logger.warning(f"optimal_hyperparams.json illisible ({e}) : hyperparamètres par défaut.")
        return {}

    def _init_base_models(self, scale_pos: float) -> Dict[str, Any]:
        opt_params = self._load_optimal_params()
        
        # 1. CatBoost
        cat_p = {
            'iterations': 100, 'depth': 3, 'learning_rate': 0.05,
            'scale_pos_weight': scale_pos, 'random_seed': self.random_state,
            'verbose': False, 'thread_count': -1, 'allow_writing_files': False
        }
        if 'CatBoost' in opt_params:
            cat_p.update(opt_params['CatBoost'])
            cat_p['scale_pos_weight'] = scale_pos
            cat_p['verbose'] = False
            cat_p['thread_count'] = -1
            cat_p['allow_writing_files'] = False
        cat = CatBoostClassifier(**cat_p)

        # 2. LightGBM
        lgb_p = {
            'n_estimators': 100, 'max_depth': 3, 'num_leaves': 7, 'learning_rate': 0.05,
            'scale_pos_weight': scale_pos, 'random_state': self.random_state,
            'subsample': 0.8, 'colsample_bytree': 0.8, 'verbose': -1, 'n_jobs': -1
        }
        if 'LightGBM' in opt_params:
            lgb_p.update(opt_params['LightGBM'])
            lgb_p['scale_pos_weight'] = scale_pos
            lgb_p['verbose'] = -1
            lgb_p['n_jobs'] = -1
        lgb = LGBMClassifier(**lgb_p)

        # 3. XGBoost
        xgb_p = {
            'n_estimators': 100, 'max_depth': 3, 'learning_rate': 0.05,
            'scale_pos_weight': scale_pos, 'eval_metric': 'logloss',
            'random_state': self.random_state, 'subsample': 0.8, 'colsample_bytree': 0.8,
            'verbosity': 0, 'n_jobs': -1
        }
        if 'XGBoost' in opt_params:
            xgb_p.update(opt_params['XGBoost'])
            xgb_p['scale_pos_weight'] = scale_pos
            xgb_p['eval_metric'] = 'logloss'
            xgb_p['verbosity'] = 0
            xgb_p['n_jobs'] = -1
        xgb = XGBClassifier(**xgb_p)

        return {'CatBoost': cat, 'LightGBM': lgb, 'XGBoost': xgb}

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Entraîne et calibre les modèles de base puis optimise les poids."""
        n_samples = len(y)
        n_pos = int(sum(y))
        n_neg = int(n_samples - n_pos)
        scale_pos = n_neg / max(1, n_pos)

        n_splits_actual = min(self.n_splits, max(2, n_samples // 400))
        tscv = TimeSeriesSplit(n_splits=n_splits_actual)

        base_models = self._init_base_models(scale_pos)
        self.models_ = base_models
        # 2. Entraînement et calibration sigmoid de chaque modèle complet
        for name, model in base_models.items():
            calibrated = CalibratedClassifierCV(model, method='sigmoid', cv=tscv, n_jobs=None)
            calibrated.fit(X, y)
            self.calibrated_models_[name] = calibrated

        # 3. Optimisation des poids de l'Ensemble par Blending OOF (Out-Of-Fold)
        oof_preds = {name: np.zeros(n_samples) for name in base_models.keys()}
        valid_indices = []
        for train_idx, val_idx in tscv.split(X):
            valid_indices.extend(val_idx)
            X_train, y_train = X[train_idx], y[train_idx]
            X_val = X[val_idx]
            for name, model in base_models.items():
                m_clone = copy.deepcopy(model)
                cal = CalibratedClassifierCV(m_clone, method='sigmoid', cv=2, n_jobs=None)
                cal.fit(X_train, y_train)
                oof_preds[name][val_idx] = cal.predict_proba(X_val)[:, 1]

        valid_indices = np.array(valid_indices)
        n_models = len(base_models)
        
        if len(valid_indices) > 0:
            y_valid = y[valid_indices]
            
            def objective(weights):
                combined = np.zeros(len(valid_indices))
                for i, name in enumerate(base_models.keys()):
                    combined += weights[i] * oof_preds[name][valid_indices]
                return brier_score_loss(y_valid, combined)
                
            init_w = np.ones(n_models) / n_models
            bounds = tuple((0.0, 1.0) for _ in range(n_models))
            cons = ({'type': 'eq', 'fun': lambda w: 1.0 - np.sum(w)})
            
            res = minimize(objective, init_w, method='SLSQP', bounds=bounds, constraints=cons)
            self.weights_ = res.x
            
            # Champion fallback
            best_brier = float('inf')
            for name in base_models.keys():
                score = brier_score_loss(y_valid, oof_preds[name][valid_indices])
                if score < best_brier:
                    best_brier = score
                    self.best_model_name_ = name
        else:
            self.weights_ = np.ones(n_models) / n_models
            self.best_model_name_ = list(base_models.keys())[0]

        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Prédit les probabilités [P(0), P(1)] selon le mode choisi."""
        if self.mode == "champion" and self.best_model_name_:
            # Utilise le meilleur modèle calibré
            p1 = self.calibrated_models_[self.best_model_name_].predict_proba(X)[:, 1]
        else:
            # Mode 'ensemble' : combinaison pondérée des prédictions calibrées
            p1 = np.zeros(len(X))
            for i, (name, model) in enumerate(self.calibrated_models_.items()):
                p1 += self.weights_[i] * model.predict_proba(X)[:, 1]

        # Garantir le clipping [0.01, 0.99] pour éviter division par zéro dans Kelly
        p1 = np.clip(p1, 0.005, 0.995)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Prédit la classe binaire selon le seuil."""
        probas = self.predict_proba(X)[:, 1]
        return (probas >= threshold).astype(int)


def calculate_quarter_kelly(proba: float, cote: Optional[float], categorie: str = "", current_exposure: float = 0.0, max_exposure: float = 15.0, brier_penalty: float = 0.0) -> str:
    """Calcule la recommandation de mise fractionnée Quarter Kelly avec Money Management Global.

    Args:
        proba: Probabilité estimée de l'événement.
        cote: Cote décimale du bookmaker.
        categorie: Catégorie du pick (BUTEUR, PASSEUR, POINTEUR).
        current_exposure: Exposition totale actuelle du Portfolio.
        max_exposure: Plafond maximum autorisé (ex: 15.0 U).
        brier_penalty: Pénalité appliquée au diviseur Kelly (ex: 4.0 pour réduire la mise en période d'incertitude).

    Returns:
        String de mise formatée (ex: "1.5 U").
    """
    if not cote or cote <= 1.05:
        return "1 U"

    b = cote - 1.0
    p = proba

    # NOTE (V2): La pénalité défenseur (p * 0.6) a été supprimée.
    # Le modèle calibré (CalibratedClassifierCV isotonique) produit
    # des probabilités déjà ajustées par position via les features
    # (ixg, sog, hdcf sont naturellement plus bas pour les D-men).
    # Garder le patch en plus = double pénalité injustifiée.

    q = 1.0 - p
    f = (p * b - q) / b

    # Plafond dynamique selon la catégorie
    cap = CATEGORY_CAPS.get(categorie, 2.0)

    if f > 0:
        ev = (p * cote) - 1.0
        
        # Mode Safe (Phase 4) supprimé : on ne booste plus le cap 
        # artificiellement pour éviter la sur-exposition liée à la surconfiance.
            
        # Fraction Kelly dynamique : 1/6ème sur les Passeurs à fort Edge (EV >= 0.12)
        # et 1/8ème pour les autres marchés à plus forte variance
        if categorie == "PASSEUR" and ev >= 0.12:
            fraction = 6.0 + brier_penalty
        else:
            fraction = 8.0 + brier_penalty

        kelly_stake = f / fraction
        units = round(kelly_stake * 100 * 2) / 2  # arrondi à 0.5 près
        units = max(0.5, min(units, cap))
        
        # Money Management Global : on réduit la mise si on dépasse le plafond
        if current_exposure + units > max_exposure:
            remaining_capacity = max(0.0, max_exposure - current_exposure)
            # Arrondi à 0.5 près
            remaining_capacity = round(remaining_capacity * 2) / 2
            units = min(units, remaining_capacity)
            
            if units <= 0:
                logger.warning(f"Pari ignoré (Kelly {f/8.0:.2f}U) : Plafond d'exposition globale atteint ({current_exposure}/{max_exposure}U).")
                return "0 U"
            else:
                logger.warning(f"Mise réduite ({units}U au lieu de cap) : Plafond global presque atteint.")
                
        return f"{units} U"

    return "0 U"


def is_cote_valid(pick: dict, cote_min: float) -> bool:
    if not pick.get("Cote") or pick["Cote"] <= 1.05:
        logger.info(f"Pari Rejeté (Absence de Cote) : {pick['Joueur']}")
        return False
    if cote_min > 0 and pick["Cote"] < cote_min:
        logger.info(f"Pari Rejeté (Cote {pick['Cote']:.2f} < min {cote_min:.2f}) : {pick['Joueur']}")
        return False
        
    ev = (pick["Proba"] * pick["Cote"]) - 1.0
    # FILTRE EV ADAPTATIF (P9) : seuils lus dans [thresholds.ev_adaptive] (source unique)
    cote = pick["Cote"]
    thr = cfg.thresholds.ev_adaptive
    if cote < thr.low_odds_cutoff:
        min_ev = thr.low_odds_min_ev
    elif cote <= thr.mid_odds_cutoff:
        min_ev = thr.mid_odds_min_ev
    else:
        min_ev = thr.high_odds_min_ev

    if ev < min_ev:
        logger.info(f"Pari Rejeté (EV {ev*100:.1f}% < requis {min_ev*100:.0f}%) : {pick['Joueur']} @ {cote:.2f} (Proba: {pick['Proba']:.3f})")
        return False
    return True


def apply_kelly_to_picks(picks_list: list, current_exposure: float = 0.0, max_exposure: float = 15.0, brier_penalty: float = 0.0) -> float:
    """Calcule et injecte la mise Kelly sur chaque pick (mutation in-place).
    Met à jour l'exposition globale en cours.

    Args:
        picks_list: Liste de dicts de picks à enrichir avec 'Mise' et 'MiseNum'.
        current_exposure: Exposition actuelle avant traitement de ces picks.
        max_exposure: Plafond maximum autorisé.
        brier_penalty: Pénalité optionnelle augmentant le diviseur.
        
    Returns:
        La nouvelle exposition totale après ces picks.
    """
    for p in picks_list:
        mise_str = calculate_quarter_kelly(
            p.get('Proba', 0),
            p.get('Cote'), 
            p.get('Categorie', ''),
            current_exposure=current_exposure,
            max_exposure=max_exposure,
            brier_penalty=brier_penalty
        )
        p["Mise"] = mise_str
        try:
            val = float(mise_str.replace(" U", ""))
            p["MiseNum"] = val
            current_exposure += val
        except (ValueError, AttributeError):
            p["MiseNum"] = 0.0
            
    return current_exposure


def get_adaptive_ev_threshold(cote: float, default_ev: float = 0.05) -> float:
    """Seuil EV adaptatif selon la cote décimale ([thresholds.ev_adaptive])."""
    if not cote or cote <= 1.05:
        return default_ev
    ev = cfg.thresholds.ev_adaptive
    if cote < ev.low_odds_cutoff:
        return ev.low_odds_min_ev
    if cote <= ev.mid_odds_cutoff:
        return ev.mid_odds_min_ev
    return ev.high_odds_min_ev
