"""
shared/devig.py — Probabilité « juste » (sans marge) d'un marché à deux issues (Oui / Non).

Méthodes :
- multiplicative : p = (1/cote) / somme. Répartit la marge proportionnellement : sur les
  longshots, où les books mettent plus de marge (biais favori-longshot), elle surestime p.
- additive : retire la même quantité de marge à chaque issue.
- power : p_i = (1/cote_i)^k avec k tel que la somme vaille 1 (marge plus forte sur le longshot).
- shin : modèle de Shin (proportion z de parieurs informés), résolu numériquement.

Toutes les fonctions acceptent des scalaires ou des tableaux numpy (NaN propagés).
La méthode de production est choisie par log-loss sur l'historique (audit 2026-10-04, P1).
"""
from typing import Tuple

import numpy as np

METHODS = ("multiplicative", "additive", "power", "shin")


def _inv(yes, no) -> Tuple[np.ndarray, np.ndarray]:
    return 1.0 / np.asarray(yes, dtype=float), 1.0 / np.asarray(no, dtype=float)


def _bisect(f, lo: float, hi: float, shape, n_iter: int = 80) -> np.ndarray:
    """Racine de f (croissante) sur [lo, hi], élément par élément."""
    a, b = np.full(shape, lo, dtype=float), np.full(shape, hi, dtype=float)
    for _ in range(n_iter):
        m = (a + b) / 2
        pos = f(m) > 0
        b = np.where(pos, m, b)
        a = np.where(pos, a, m)
    return (a + b) / 2


def devig_yes(yes, no, method: str = "multiplicative"):
    """Probabilité sans marge de l'issue « Oui ».

    Args:
        yes: cote décimale « Oui » (scalaire ou tableau).
        no: cote décimale « Non ».
        method: une de METHODS.

    Returns:
        p(Oui) dans [0, 1] ; NaN si une cote manque. Scalaire si les entrées le sont.
    """
    if method not in METHODS:
        raise ValueError(f"méthode de dévig inconnue : {method}")
    scalar = np.ndim(yes) == 0 and np.ndim(no) == 0
    qy, qn = _inv(yes, no)
    qy, qn = np.atleast_1d(qy), np.atleast_1d(qn)
    s = qy + qn
    if method == "multiplicative":
        p = qy / s
    elif method == "additive":
        p = qy - (s - 1.0) / 2.0
    elif method == "power":
        # somme(q_i^k) décroît avec k (q_i < 1) : on cherche k ≥ 1 où elle vaut 1
        def f(k):
            return 1.0 - (qy ** k + qn ** k)
        k = _bisect(f, 0.2, 10.0, qy.shape)
        p = qy ** k
    else:  # shin
        def p_shin(z, q):
            return (np.sqrt(z ** 2 + 4 * (1 - z) * q ** 2 / s) - z) / (2 * (1 - z))

        def f(z):
            return 1.0 - (p_shin(z, qy) + p_shin(z, qn))
        z = _bisect(f, 0.0, 0.5, qy.shape)
        p = p_shin(z, qy)
    p = np.where(np.isfinite(s), np.clip(p, 0.0, 1.0), np.nan)
    return float(p[0]) if scalar else p
