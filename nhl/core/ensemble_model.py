"""
core/ensemble_model.py — Architecture d'Ensemble Multi-Boosting NHL.

Combine XGBoost, LightGBM et CatBoost sous validation croisée temporelle
stricte (TimeSeriesSplit) avec calibration isotonique et pondération convexe.
Permet d'utiliser soit l'Ensemble complet (Blending), soit le modèle Champion
pour chaque marché spécifique.
"""
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.model_selection import TimeSeriesSplit
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, roc_auc_score
from scipy.optimize import minimize

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier


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
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "optimal_hyperparams.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Fallback chain: try exact key first, then {market}_0_5
                    # (JSON uses "but_0_5"/"ast_0_5", but self.market is "but"/"ast")
                    return data.get(self.market) or data.get(f"{self.market}_0_5", {})
            except Exception:
                pass
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
                import copy
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


# ─────────────────────────────────────────────────────────────────────────────
# P1b — Modèle calibré "propre" : pas de repondération, isotonique sur un bloc
# temporel tenu à l'écart, NaN gérés nativement.
# ─────────────────────────────────────────────────────────────────────────────
class TemporalCalibratedGBM(BaseEstimator, ClassifierMixin):
    """Boosting(s) entraîné(s) sur le passé + calibration isotonique sur le bloc le plus récent.

    Les lignes doivent être triées chronologiquement. Les `calib_frac` dernières
    lignes ne servent qu'à la calibration (et au poids de blending), jamais à
    l'apprentissage des arbres : la calibration est donc hors échantillon.

    Args:
        algos: modèles de base parmi 'lgbm', 'xgb', 'cat'. Plusieurs = blending
            pondéré par la log-loss sur le bloc de calibration.
        calib_frac: fraction finale réservée à la calibration.
        random_state: graine.
    """

    def __init__(self, algos: tuple = ("lgbm",), calib_frac: float = 0.15, random_state: int = 42,
                 params: Optional[Dict[str, Dict[str, Any]]] = None):
        self.algos = algos
        self.calib_frac = calib_frac
        self.random_state = random_state
        self.params = params  # surcharges d'hyperparamètres par algo, ex. {"lgbm": {"num_leaves": 63}}
        self.classes_ = np.array([0, 1])

    def _make(self, algo: str):
        over = (self.params or {}).get(algo, {})
        if algo == "lgbm":
            kw = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=200,
                      subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0,
                      random_state=self.random_state, verbose=-1, n_jobs=-1)
            kw.update(over)
            return LGBMClassifier(**kw)
        if algo == "xgb":
            return XGBClassifier(n_estimators=400, learning_rate=0.03, max_depth=5, min_child_weight=50,
                                 subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, eval_metric="logloss",
                                 random_state=self.random_state, verbosity=0, n_jobs=-1)
        if algo == "cat":
            return CatBoostClassifier(iterations=400, learning_rate=0.05, depth=6, l2_leaf_reg=5.0,
                                      random_seed=self.random_state, verbose=False, thread_count=-1,
                                      allow_writing_files=False)
        raise ValueError(f"algo inconnu : {algo}")

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Entraîne les modèles de base puis calibre sur le bloc final."""
        from sklearn.isotonic import IsotonicRegression
        from sklearn.metrics import log_loss
        n = len(y)
        cut = int(n * (1 - self.calib_frac))
        X_tr, y_tr, X_ca, y_ca = X[:cut], y[:cut], X[cut:], y[cut:]
        self.models_ = {}
        raw = {}
        for a in self.algos:
            m = self._make(a)
            m.fit(X_tr, y_tr)
            self.models_[a] = m
            raw[a] = m.predict_proba(X_ca)[:, 1]
        # Poids inverses à la log-loss (simple, stable) ; un seul algo => poids 1
        ll = np.array([log_loss(y_ca, np.clip(raw[a], 1e-6, 1 - 1e-6)) for a in self.algos])
        w = np.exp(-(ll - ll.min()) * 200)  # écarts de log-loss minimes -> poids proches
        self.weights_ = w / w.sum()
        blend = sum(self.weights_[i] * raw[a] for i, a in enumerate(self.algos))
        self.iso_ = IsotonicRegression(out_of_bounds="clip", y_min=0.005, y_max=0.995)
        self.iso_.fit(blend, y_ca)
        self.calib_logloss_ = float(log_loss(y_ca, np.clip(self.iso_.predict(blend), 1e-6, 1 - 1e-6)))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        blend = sum(self.weights_[i] * self.models_[a].predict_proba(X)[:, 1] for i, a in enumerate(self.algos))
        p1 = np.clip(self.iso_.predict(blend), 0.005, 0.995)
        return np.column_stack([1 - p1, p1])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= threshold).astype(int)
