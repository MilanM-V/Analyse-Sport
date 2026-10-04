"""
core/ensemble_model.py — Modèle de production NHL : TemporalCalibratedGBM.

Boosting(s) LightGBM / XGBoost / CatBoost entraînés sur le passé, blending pondéré par la
log-loss et calibration isotonique sur le bloc temporel le plus récent (hors apprentissage).
L'ancien NHLEnsembleClassifier (repondération + calibration sigmoïde) est dans
nhl/sim/legacy.py, pour rejouer les phases historiques uniquement.
"""
from typing import Any, Dict, Optional

import numpy as np
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator, ClassifierMixin
from xgboost import XGBClassifier


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
                 params: Optional[Dict[str, Dict[str, Any]]] = None, refit_full: bool = False,
                 split_calib: bool = False):
        self.algos = algos
        self.calib_frac = calib_frac
        self.random_state = random_state
        self.params = params  # surcharges d'hyperparamètres par algo, ex. {"lgbm": {"num_leaves": 63}}
        # refit_full : après calibration, ré-entraîne les arbres sur 100 % des lignes (les plus
        # récentes, réservées à la calibration, ne servaient jamais à l'apprentissage).
        self.refit_full = refit_full
        # split_calib : poids de blending appris sur la 1re moitié du bloc de calibration,
        # isotonique sur la 2e (sinon les deux sur le même bloc : log-loss de calibration optimiste).
        self.split_calib = split_calib
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
            kw = dict(n_estimators=400, learning_rate=0.03, max_depth=5, min_child_weight=50,
                      subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, eval_metric="logloss",
                      random_state=self.random_state, verbosity=0, n_jobs=-1)
            kw.update(over)
            return XGBClassifier(**kw)
        if algo == "cat":
            kw = dict(iterations=400, learning_rate=0.05, depth=6, l2_leaf_reg=5.0,
                      random_seed=self.random_state, verbose=False, thread_count=-1,
                      allow_writing_files=False)
            kw.update(over)
            kw["allow_writing_files"] = False  # sinon catboost_info/ est écrit dans le dépôt
            return CatBoostClassifier(**kw)
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
        half = len(y_ca) // 2 if getattr(self, "split_calib", False) else 0
        w_idx = slice(0, half) if half else slice(None)
        i_idx = slice(half, None) if half else slice(None)
        ll = np.array([log_loss(y_ca[w_idx], np.clip(raw[a][w_idx], 1e-6, 1 - 1e-6)) for a in self.algos])
        w = np.exp(-(ll - ll.min()) * 200)  # écarts de log-loss minimes -> poids proches
        self.weights_ = w / w.sum()
        blend = sum(self.weights_[i] * raw[a] for i, a in enumerate(self.algos))
        self.iso_ = IsotonicRegression(out_of_bounds="clip", y_min=0.005, y_max=0.995)
        self.iso_.fit(blend[i_idx], y_ca[i_idx])
        self.calib_logloss_ = float(log_loss(y_ca[i_idx], np.clip(self.iso_.predict(blend[i_idx]), 1e-6, 1 - 1e-6)))
        if getattr(self, "refit_full", False):
            # Mêmes hyperparamètres, toutes les lignes : l'isotonique apprise ci-dessus est conservée
            for a in self.algos:
                m = self._make(a)
                m.fit(X, y)
                self.models_[a] = m
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        blend = sum(self.weights_[i] * self.models_[a].predict_proba(X)[:, 1] for i, a in enumerate(self.algos))
        p1 = np.clip(self.iso_.predict(blend), 0.005, 0.995)
        return np.column_stack([1 - p1, p1])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= threshold).astype(int)
