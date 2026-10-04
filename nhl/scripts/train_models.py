"""
scripts/train_models.py — Entraînement des modèles NHL de production (V3, parité train/serve).

- Données : tous les logs de match (MoneyPuck 2008-2024 + API NHL 2025+) passés par
  `nhl.core.features.build_features` — la MÊME fonction que le bot en production.
- Modèle : `TemporalCalibratedGBM` (pas de repondération, isotonique sur le bloc récent).
- Buteur : attaquants uniquement. Passeur : tous les patineurs (`is_D` en feature).
- Gate : le nouveau modèle n'écrase le modèle en place que s'il fait au moins aussi
  bien en log-loss sur le même holdout temporel (derniers HOLDOUT_DAYS jours).
  Un modèle en place d'une autre version de features est toujours remplacé.

Usage:
    python nhl/scripts/train_models.py                 # entraîne + gate + sauvegarde
    python nhl/scripts/train_models.py --algos lgbm,xgb,cat
    python nhl/scripts/train_models.py --force         # ignore le gate
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.ensemble_model import TemporalCalibratedGBM  # noqa: E402
from nhl.core.monitoring import reference_profile  # noqa: E402
from nhl.core.features import (FEATURES, FEATURES_VERSION, build_features,  # noqa: E402
                               load_all_gamelogs, load_season_priors)

MODELS_DIR = os.path.join(ROOT, "nhl", "models")
LIVE_DIR = os.path.join(MODELS_DIR, "live")  # retrains du VPS : hors git (pas de conflit au pull)
HOLDOUT_DAYS = 45
MIN_SEASON = 2009
DEFAULT_ALGOS = ("lgbm",)


def load_training_frame() -> pd.DataFrame:
    """Features de tous les matchs joués (cibles connues), triées chronologiquement."""
    df = build_features(load_all_gamelogs(), load_season_priors())
    df = df[(df["season"] >= MIN_SEASON) & df["target_but"].notna()]
    return df.sort_values(["date", "gameId", "playerId"]).reset_index(drop=True)


def market_rows(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Population d'entraînement d'un marché (buteur = attaquants seulement)."""
    return df[df["position"] != "D"] if market == "but" else df


def _metrics(y: np.ndarray, p: np.ndarray) -> Dict[str, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"logloss": float(log_loss(y, p)), "brier": float(brier_score_loss(y, p)),
            "auc": float(roc_auc_score(y, p)), "mean_p": float(p.mean()), "rate": float(y.mean())}


GATE_MIN_ROWS = 2000  # lignes postérieures au cutoff du modèle en place nécessaires pour comparer


def _current_bundle(market: str) -> Optional[dict]:
    """Modèle en place (live/ prioritaire), ou None s'il est absent ou d'une autre version de features."""
    from nhl.core.inference import model_path
    path = model_path(market)
    if not path:
        return None
    bundle = joblib.load(path)
    if bundle.get("features_version") != FEATURES_VERSION:
        print(f"  [gate] {market} : modèle en place d'une autre version de features "
              f"({bundle.get('features_version')}) → remplacé.")
        return None
    return bundle


def gate_rows(hold: pd.DataFrame, current_cutoff: Optional[str]) -> pd.DataFrame:
    """Lignes du holdout que le modèle en place n'a PAS vues à l'entraînement (date > son cutoff).

    Comparer sur tout le holdout avantage le modèle en place, entraîné jusqu'à son cutoff
    (holdout inclus) : il serait évalué en échantillon et ne serait jamais remplacé.
    """
    if not current_cutoff:
        return hold.iloc[:0]
    return hold[hold["date"] > pd.Timestamp(current_cutoff)]


def gate_decision(new_ll: float, cur_ll: Optional[float], n_rows: int, force: bool) -> Tuple[bool, str]:
    """Décision du gate.

    Returns:
        (remplacer, raison). Sans assez de lignes hors échantillon, le modèle en place est conservé.
    """
    if force:
        return True, "forcé (--force)"
    if cur_ll is None:
        return False, f"non concluant : {n_rows} ligne(s) postérieure(s) au modèle en place (< {GATE_MIN_ROWS})"
    if new_ll <= cur_ll:
        return True, f"nouveau meilleur ({new_ll:.4f} ≤ {cur_ll:.4f}, {n_rows} lignes)"
    return False, f"nouveau moins bon ({new_ll:.4f} > {cur_ll:.4f}, {n_rows} lignes)"


def train_market(df: pd.DataFrame, market: str, algos: Tuple[str, ...], force: bool, out_dir: str = MODELS_DIR) -> bool:
    """Entraîne, applique le gate, puis ré-entraîne sur tout et sauvegarde.

    Returns:
        True si le modèle a été sauvegardé.
    """
    feats = FEATURES[market]
    target = f"target_{market}"
    d = market_rows(df, market)
    cutoff = d["date"].max() - pd.Timedelta(days=HOLDOUT_DAYS)
    tr, hold = d[d["date"] <= cutoff], d[d["date"] > cutoff]
    print(f"\n=== {market.upper()} — train {len(tr):,} lignes (≤ {cutoff.date()}), holdout {len(hold):,} ===")

    m = TemporalCalibratedGBM(algos=algos).fit(tr[feats].to_numpy(float), tr[target].to_numpy())
    met = _metrics(hold[target].to_numpy(), m.predict_proba(hold[feats].to_numpy(float))[:, 1])
    print(f"  holdout : logloss={met['logloss']:.4f} brier={met['brier']:.4f} auc={met['auc']:.4f} "
          f"p_moy={met['mean_p']:.3f} taux={met['rate']:.3f}")

    bundle = _current_bundle(market)
    if bundle is not None:
        rows = gate_rows(hold, bundle.get("train_cutoff"))
        y = rows[target].to_numpy()
        cur_ll = new_ll = None
        if len(rows) >= GATE_MIN_ROWS and len(np.unique(y)) > 1:
            X = rows[feats].to_numpy(float)
            new_ll = _metrics(y, m.predict_proba(X)[:, 1])["logloss"]
            cur_ll = _metrics(y, bundle["model"].predict_proba(rows[bundle["features"]].to_numpy(float))[:, 1])["logloss"]
        ok, why = gate_decision(new_ll if new_ll is not None else met["logloss"], cur_ll, len(rows), force)
        print(f"  [gate] {market} : {'✅ remplacé' if ok else '⛔ conservé'} — {why}")
        if not ok:
            return False

    final = TemporalCalibratedGBM(algos=algos).fit(d[feats].to_numpy(float), d[target].to_numpy())
    data_hash = hashlib.sha1(pd.util.hash_pandas_object(d[["playerId", "gameId"]], index=False).values).hexdigest()[:12]
    bundle = {
        "model": final, "features": feats, "features_version": FEATURES_VERSION,
        "algo": "temporal_calibrated_gbm[" + "+".join(algos) + "]",
        "train_cutoff": str(d["date"].max().date()), "train_samples": int(len(d)),
        "holdout_days": HOLDOUT_DAYS, "holdout_logloss": met["logloss"], "holdout_brier": met["brier"],
        "holdout_auc": met["auc"], "holdout_rate": met["rate"], "data_hash": data_hash,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "feature_profile": reference_profile(d[d["date"] > d["date"].max() - pd.Timedelta(days=365)], feats),
    }
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"ml_model_{market}.pkl")
    joblib.dump(bundle, path)
    print(f"  ✅ sauvegardé : {path}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algos", default=",".join(DEFAULT_ALGOS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--live", action="store_true", help="écrit dans nhl/models/live/ (retrain automatique du VPS)")
    a = ap.parse_args()
    algos = tuple(x.strip() for x in a.algos.split(",") if x.strip())
    df = load_training_frame()
    print(f"{len(df):,} matchs-joueurs ({df['date'].min().date()} → {df['date'].max().date()}), "
          f"features {FEATURES_VERSION}, algos {algos}")
    saved = [train_market(df, market, algos, a.force, LIVE_DIR if a.live else MODELS_DIR) for market in ("but", "ast")]
    if any(saved) and not a.live:
        refresh_simulator()


def refresh_simulator() -> None:
    """Nouveaux modèles de prod = nouvelle version : régénère simulateur.html."""
    try:
        from nhl.scripts.export_simulator_data import export
        export()
    except FileNotFoundError as e:
        print(f"  ⚠️ simulateur NON régénéré (prédictions walk-forward absentes : {e}). "
              "Lancer simulate_roi.py --phase p1b_ens puis export_simulator_data.py.")


if __name__ == "__main__":
    main()
