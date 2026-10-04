"""
scripts/eval_new_markets.py — Piste G : qualité prédictive de nouveaux marchés.

Marchés : points ≥ 1 (target_pts), tirs cadrés ≥ 2 (target_sog2) et ≥ 3 (target_sog3).
Pas assez de cotes historiques pour simuler un ROI : on mesure la qualité du modèle
(log-loss, AUC, calibration) hors échantillon sur trois saisons, contre une référence
naïve (fréquence du joueur sur ses 20 derniers matchs, shrinkée vers la moyenne).

Usage:
    python nhl/scripts/eval_new_markets.py
"""
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.ensemble_model import TemporalCalibratedGBM  # noqa: E402
from nhl.core.features import FEATURES_G, build_features, load_all_gamelogs, load_season_priors  # noqa: E402

SPLITS = [("2023-24", "2023-10-01", "2024-07-01"), ("2024-25", "2024-10-01", "2025-07-01"),
          ("2025-26", "2025-10-01", "2026-07-01")]
OUT = os.path.join(ROOT, "nhl", "reports", "new_markets_eval.csv")


def naive_prob(df: pd.DataFrame, target: str) -> np.ndarray:
    """Fréquence décalée du joueur sur 20 matchs, shrinkée (k=5) vers la moyenne globale."""
    base = df[target].mean()
    hit = df.groupby("playerId")[target].transform(lambda s: s.shift(1).rolling(20, min_periods=1).sum())
    n = df.groupby("playerId").cumcount().clip(upper=20)
    return ((hit.fillna(0) + 5 * base) / (n + 5)).to_numpy()


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    q = pd.qcut(p, bins, duplicates="drop")
    g = pd.DataFrame({"y": y, "p": p, "b": q}).groupby("b", observed=True).agg(y=("y", "mean"), p=("p", "mean"), n=("y", "size"))
    return float((g["n"] * (g["p"] - g["y"]).abs()).sum() / g["n"].sum())


def main() -> None:
    df = build_features(load_all_gamelogs(), load_season_priors())
    df = df[(df["season"] >= 2009) & df["target_but"].notna()].sort_values(["playerId", "date", "gameId"])
    rows = []
    for market, feats in FEATURES_G.items():
        target = f"target_{market}"
        d = df if market == "pts" else df[df["position"] != "D"]
        d = d.assign(naive=naive_prob(d, target)).sort_values(["date", "gameId", "playerId"])
        for name, start, end in SPLITS:
            tr = d[d["date"] < start]
            te = d[(d["date"] >= start) & (d["date"] < end) & (d["std_gp"] >= 10) & (d["toi_l10"] >= 13)]
            m = TemporalCalibratedGBM(algos=("lgbm",)).fit(tr[feats].to_numpy(float), tr[target].to_numpy())
            p = m.predict_proba(te[feats].to_numpy(float))[:, 1]
            y = te[target].to_numpy()
            r = {"marche": market, "saison": name, "n": len(te), "taux": y.mean(),
                 "ll_modele": log_loss(y, p), "ll_naif": log_loss(y, np.clip(te["naive"], 1e-4, 1 - 1e-4)),
                 "ll_constant": log_loss(y, np.full(len(y), tr[target].mean())),
                 "auc_modele": roc_auc_score(y, p), "auc_naif": roc_auc_score(y, te["naive"]), "ece_modele": ece(y, p)}
            r["gain_ll_vs_naif_%"] = 100 * (r["ll_naif"] - r["ll_modele"]) / r["ll_naif"]
            rows.append(r)
            print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"écrit : {OUT}")


if __name__ == "__main__":
    main()
