"""
core/monitoring.py — Surveillance de dérive (PSI) des features servies en production.

Le modèle embarque un profil de référence (déciles des features d'entraînement).
Chaque jour, on compare les vecteurs de features réellement servis (loggés en JSON
dans la table `players`) à ce profil. PSI > 0,2 sur une feature = alerte.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("NHL.Monitoring")

PSI_ALERT = 0.2


def reference_profile(df: pd.DataFrame, cols: List[str], bins: int = 10) -> Dict[str, Dict[str, list]]:
    """Profil de référence : bornes de déciles + part de NaN, par feature."""
    prof = {}
    for c in cols:
        x = df[c].to_numpy(dtype=float)
        nan_rate = float(np.isnan(x).mean())
        x = x[~np.isnan(x)]
        edges = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1))) if len(x) else np.array([0.0])
        prof[c] = {"edges": edges.tolist(), "nan_rate": nan_rate}
    return prof


def psi(ref: Dict[str, list], values: np.ndarray, eps: float = 1e-4) -> float:
    """Population Stability Index d'un échantillon vs le profil de référence."""
    edges = np.asarray(ref["edges"], dtype=float)
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(edges) < 2 or len(values) < 30:
        return float("nan")
    inner = edges[1:-1]
    expected = np.full(len(inner) + 1, 1.0 / (len(inner) + 1))
    actual = np.bincount(np.searchsorted(inner, values, side="right"), minlength=len(inner) + 1) / len(values)
    expected, actual = np.clip(expected, eps, None), np.clip(actual, eps, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def drift_report(days: int = 7) -> Optional[str]:
    """Calcule le PSI des features servies sur `days` jours ; renvoie un message d'alerte ou None."""
    from nhl.core.database import get_connection
    from nhl.core.inference import load_models
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        rows = pd.read_sql("SELECT features_json FROM players WHERE date >= ? AND features_json IS NOT NULL",
                           conn, params=(since,))
    finally:
        conn.close()
    if rows.empty:
        logger.info("[Drift] Aucun vecteur de features loggé sur la période.")
        return None
    alerts = []
    for market, bundle in load_models().items():
        prof = bundle.get("feature_profile")
        if not prof:
            continue
        vecs = [json.loads(j).get(market) for j in rows["features_json"]]
        X = pd.DataFrame([v for v in vecs if v])
        for col, ref in prof.items():
            if col in X:
                v = psi(ref, X[col].to_numpy(dtype=float))
                if v == v and v > PSI_ALERT:
                    alerts.append(f"{market}.{col} PSI={v:.2f}")
    logger.info(f"[Drift] {len(rows)} vecteurs analysés, {len(alerts)} alerte(s).")
    if alerts:
        return "📉 <b>Dérive des features (PSI &gt; 0,2)</b>\n" + "\n".join(alerts[:20])
    return None
