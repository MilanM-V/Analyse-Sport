"""
scripts/tune_hyperparams.py — Tuning Optuna de TemporalCalibratedGBM (LightGBM) par marché.

Critère : log-loss (probabilités calibrées) sur la saison de VALIDATION 2023-24, le
modèle étant entraîné sur toutes les saisons antérieures (≥ 2009). La saison de test
2024-25 n'est jamais utilisée ici : elle reste le juge du harnais simulate_roi.py.

Sortie : nhl/config/tuned_gbm_params.json  {"but": {"lgbm": {...}}, "ast": {...}}
(l'ancien optimal_hyperparams.json reste celui de l'ancien NHLEnsembleClassifier).

Usage:
    python nhl/scripts/tune_hyperparams.py [--trials 25]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import log_loss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.ensemble_model import TemporalCalibratedGBM  # noqa: E402
from nhl.core.features import FEATURES, build_features, load_all_gamelogs, load_season_priors  # noqa: E402

optuna.logging.set_verbosity(optuna.logging.WARNING)
OUT = os.path.join(ROOT, "nhl", "config", "tuned_gbm_params.json")
VAL_START, VAL_END = pd.Timestamp("2023-10-01"), pd.Timestamp("2024-07-01")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=25)
    a = ap.parse_args()
    df = build_features(load_all_gamelogs(), load_season_priors())
    df = df[(df["season"] >= 2009) & df["target_but"].notna()].sort_values(["date", "gameId", "playerId"])
    out = {}
    for market in ("but", "ast"):
        d = df[df["position"] != "D"] if market == "but" else df
        feats, target = FEATURES[market], f"target_{market}"
        tr, va = d[d["date"] < VAL_START], d[(d["date"] >= VAL_START) & (d["date"] < VAL_END)]
        Xtr, ytr = tr[feats].to_numpy(float), tr[target].to_numpy()
        Xva, yva = va[feats].to_numpy(float), va[target].to_numpy()

        def score(params: dict) -> float:
            m = TemporalCalibratedGBM(algos=("lgbm",), params={"lgbm": params}).fit(Xtr, ytr)
            return log_loss(yva, np.clip(m.predict_proba(Xva)[:, 1], 1e-6, 1 - 1e-6))

        base = score({})
        print(f"[{market}] défaut : log-loss validation = {base:.5f}")

        def objective(trial: optuna.Trial) -> float:
            return score({
                "n_estimators": trial.suggest_int("n_estimators", 150, 900, step=50),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.08, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 7, 127, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 50, 2000, log=True),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 50.0, log=True),
            })

        t0 = time.time()
        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
        study.enqueue_trial({"n_estimators": 400, "learning_rate": 0.03, "num_leaves": 31, "min_child_samples": 200,
                             "colsample_bytree": 0.8, "subsample": 0.8, "reg_lambda": 5.0})
        study.optimize(objective, n_trials=a.trials)
        best = study.best_value
        print(f"[{market}] meilleur : {best:.5f} (gain {base - best:+.5f}) en {time.time() - t0:.0f}s → {study.best_params}")
        out[market] = {"lgbm": study.best_params, "val_logloss": best, "val_logloss_default": base}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"écrit : {OUT}")


if __name__ == "__main__":
    main()
