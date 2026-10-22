"""
core/ensemble_model.py — Modèle de production NHL : TemporalCalibratedGBM.

Boosting(s) LightGBM / XGBoost / CatBoost entraînés sur le passé, blending pondéré par la
log-loss et calibration sur le bloc temporel le plus récent (hors apprentissage) :
isotonique (moteur p1) ou Platt (moteur v2, 2026-10). Le moteur v2 ajoute un membre réseau
de neurones (TabularMLP), calibré à part sur le même bloc, moyenné avec les arbres en logit.
L'ancien NHLEnsembleClassifier (repondération + calibration sigmoïde) est dans
nhl/sim/legacy.py, pour rejouer les phases historiques uniquement.
"""
import warnings
from typing import Any, Dict, Optional, Tuple

import numpy as np
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator, ClassifierMixin
from xgboost import XGBClassifier


def _logit(p: Any) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _sigmoid(z: Any) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


class PlattCalibrator:
    """Calibration de Platt : régression logistique sur le logit de la probabilité brute.

    Courbe lisse en S, au lieu des paliers de l'isotonique (piste C2 de l'étude du 2026-10-08).
    """

    def fit(self, raw: np.ndarray, y: np.ndarray) -> "PlattCalibrator":
        from sklearn.linear_model import LogisticRegression
        self.lr_ = LogisticRegression(C=1e6, max_iter=2000).fit(_logit(raw).reshape(-1, 1), np.asarray(y).astype(int))
        return self

    def predict(self, raw: np.ndarray) -> np.ndarray:
        return self.lr_.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]


def make_calibrator(kind: str):
    """Calibrateur 'isotonic' (bornes 0,005 / 0,995, comme avant) ou 'platt'."""
    if kind == "isotonic":
        from sklearn.isotonic import IsotonicRegression
        return IsotonicRegression(out_of_bounds="clip", y_min=0.005, y_max=0.995)
    if kind == "platt":
        return PlattCalibrator()
    raise ValueError(f"calibration inconnue : {kind}")


class TabularMLP:
    """Réseaux de neurones tabulaires moyennés en logit, membre de l'ensemble (piste C4).

    Préparation apprise sur le train : NaN remplacés par la médiane + indicateurs de manque,
    rangs gaussiens (QuantileTransformer). Puis `n_nets` MLP 256-256 (ReLU, Adam, L2 1e-4,
    lots de 8 192, `epochs` passes), graines différentes, logits moyennés.

    Args:
        n_nets: nombre de réseaux moyennés.
        epochs: passes sur les données (3 dans l'étude : arrêt précoce volontaire).
        random_state: graine du premier réseau.
    """

    def __init__(self, n_nets: int = 3, epochs: int = 3, random_state: int = 0):
        self.n_nets = n_nets
        self.epochs = epochs
        self.random_state = random_state

    def _prep(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        miss = np.isnan(X)
        Z = self.qt_.transform(np.where(miss, self.median_, X))
        return np.hstack([Z, miss[:, self.miss_cols_]]).astype(np.float32)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TabularMLP":
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import QuantileTransformer
        X = np.asarray(X, dtype=np.float64)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # colonne entièrement vide : médiane NaN
            med = np.nanmedian(X, axis=0)
        self.median_ = np.where(np.isnan(med), 0.0, med)
        self.miss_cols_ = np.isnan(X).any(axis=0)
        self.qt_ = QuantileTransformer(n_quantiles=1000, output_distribution="normal", subsample=200_000,
                                       random_state=0).fit(np.where(np.isnan(X), self.median_, X))
        Z = self._prep(X)
        self.nets_ = []
        for i in range(self.n_nets):
            net = MLPClassifier(hidden_layer_sizes=(256, 256), activation="relu", solver="adam", alpha=1e-4,
                                batch_size=min(8192, len(Z)), learning_rate_init=1e-3, max_iter=self.epochs, shuffle=True,
                                random_state=self.random_state + i, tol=0.0, n_iter_no_change=10 ** 6)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)  # arrêt après `epochs` passes : voulu
                net.fit(Z, np.asarray(y).astype(int))
            self.nets_.append(net)
        return self

    def predict_raw(self, X: np.ndarray) -> np.ndarray:
        """Probabilité brute (non calibrée) : sigmoïde de la moyenne des logits des réseaux."""
        Z = self._prep(X)
        return _sigmoid(np.mean([_logit(n.predict_proba(Z)[:, 1]) for n in self.nets_], axis=0))


# ─────────────────────────────────────────────────────────────────────────────
# P1b — Modèle calibré "propre" : pas de repondération, calibration sur un bloc
# temporel tenu à l'écart, NaN gérés nativement.
# ─────────────────────────────────────────────────────────────────────────────
class TemporalCalibratedGBM(BaseEstimator, ClassifierMixin):
    """Boosting(s) entraîné(s) sur le passé + calibration sur le bloc le plus récent.

    Les lignes doivent être triées chronologiquement. Les `calib_frac` dernières
    lignes ne servent qu'à la calibration (et au poids de blending), jamais à
    l'apprentissage des arbres : la calibration est donc hors échantillon.

    Args:
        algos: modèles de base parmi 'lgbm', 'xgb', 'cat'. Plusieurs = blending
            pondéré par la log-loss sur le bloc de calibration.
        calib_frac: fraction finale réservée à la calibration.
        random_state: graine.
        params: surcharges d'hyperparamètres par algo.
        refit_full: après calibration, ré-entraîne arbres (et réseaux) sur 100 % des lignes.
        split_calib: poids de blending sur la 1re moitié du bloc, calibration sur la 2e.
        calibration: 'isotonic' (moteur p1) ou 'platt' (moteur v2).
        mlp_nets: nombre de réseaux du membre TabularMLP (0 = arbres seuls).
        mlp_weight: poids des arbres dans la moyenne des logits (1 − poids pour le réseau).
        mlp_epochs: passes d'entraînement des réseaux.
    """

    def __init__(self, algos: tuple = ("lgbm",), calib_frac: float = 0.15, random_state: int = 42,
                 params: Optional[Dict[str, Dict[str, Any]]] = None, refit_full: bool = False,
                 split_calib: bool = False, calibration: str = "isotonic", mlp_nets: int = 0,
                 mlp_weight: float = 0.5, mlp_epochs: int = 3):
        self.algos = algos
        self.calib_frac = calib_frac
        self.random_state = random_state
        self.params = params  # surcharges d'hyperparamètres par algo, ex. {"lgbm": {"num_leaves": 63}}
        # refit_full : après calibration, ré-entraîne les arbres sur 100 % des lignes (les plus
        # récentes, réservées à la calibration, ne servaient jamais à l'apprentissage).
        self.refit_full = refit_full
        # split_calib : poids de blending appris sur la 1re moitié du bloc de calibration,
        # calibration sur la 2e (sinon les deux sur le même bloc : log-loss de calibration optimiste).
        self.split_calib = split_calib
        self.calibration = calibration
        self.mlp_nets = mlp_nets
        self.mlp_weight = mlp_weight
        self.mlp_epochs = mlp_epochs
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

    def _make_mlp(self) -> TabularMLP:
        return TabularMLP(n_nets=self.mlp_nets, epochs=getattr(self, "mlp_epochs", 3), random_state=self.random_state)

    def _combine(self, p_trees: np.ndarray, p_mlp: Optional[np.ndarray]) -> np.ndarray:
        if p_mlp is None:
            return p_trees
        w = getattr(self, "mlp_weight", 0.5)
        return _sigmoid(w * _logit(p_trees) + (1 - w) * _logit(p_mlp))

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Entraîne les modèles de base (et les réseaux) puis calibre sur le bloc final."""
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
        self.cal_ = make_calibrator(self.calibration).fit(blend[i_idx], y_ca[i_idx])
        if self.calibration == "isotonic":
            self.iso_ = self.cal_  # nom historique (anciens pickles, tests)
        p_mlp = None
        self.mlp_ = None
        if self.mlp_nets:
            self.mlp_ = self._make_mlp().fit(X_tr, y_tr)
            raw_mlp = self.mlp_.predict_raw(X_ca)
            self.mlp_cal_ = make_calibrator(self.calibration).fit(raw_mlp[i_idx], y_ca[i_idx])
            p_mlp = self.mlp_cal_.predict(raw_mlp[i_idx])
        p_cal = np.clip(self._combine(self.cal_.predict(blend[i_idx]), p_mlp), 0.005, 0.995)
        self.calib_logloss_ = float(log_loss(y_ca[i_idx], p_cal))
        if getattr(self, "refit_full", False):
            # Mêmes hyperparamètres, toutes les lignes : les calibrateurs appris ci-dessus sont conservés
            for a in self.algos:
                m = self._make(a)
                m.fit(X, y)
                self.models_[a] = m
            if self.mlp_ is not None:
                self.mlp_ = self._make_mlp().fit(X, y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        blend = sum(self.weights_[i] * self.models_[a].predict_proba(X)[:, 1] for i, a in enumerate(self.algos))
        cal = getattr(self, "cal_", None)
        if cal is None:  # pickles d'avant 2026-10 : iso_ seul
            cal = self.iso_
        mlp = getattr(self, "mlp_", None)
        p_mlp = self.mlp_cal_.predict(mlp.predict_raw(X)) if mlp is not None else None
        p1 = np.clip(self._combine(cal.predict(blend), p_mlp), 0.005, 0.995)
        return np.column_stack([1 - p1, p1])

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= threshold).astype(int)

    def describe(self) -> str:
        """Nom court du moteur, enregistré dans le bundle (« algo »)."""
        name = "temporal_calibrated_gbm[" + "+".join(self.algos) + "]"
        if getattr(self, "mlp_nets", 0):
            name += f"+mlp{self.mlp_nets}"
        if getattr(self, "calibration", "isotonic") != "isotonic":
            name += f"/{self.calibration}"
        return name


def prod_model(algos: Optional[Tuple[str, ...]] = None) -> TemporalCalibratedGBM:
    """Moteur de prod décrit par la section [model] de settings.toml (`algos` la surcharge)."""
    from nhl.config.settings import cfg
    m = cfg.model
    return TemporalCalibratedGBM(algos=tuple(algos or m.algos), calibration=getattr(m, "calibration", "isotonic"),
                                 mlp_nets=int(getattr(m, "mlp_nets", 0)), mlp_weight=float(getattr(m, "mlp_weight", 0.5)))
