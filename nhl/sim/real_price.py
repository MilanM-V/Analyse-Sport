"""
sim/real_price.py — Prix réaliste des simulations : la cote Winamax reconstituée.

Il n'existe aucun historique de cotes des books français. Pour rejouer les saisons passées,
le simulateur reconstitue la cote Winamax à partir de la calibration sur de vraies cotes
Winamax (15 matchs, 1er au 3 oct. 2026, nhl/scripts/winamax_calibration.py) :
- ligne cotée par Pinnacle : cote Pinnacle « Oui » × ratio Winamax / Pinnacle (≈ 1,00) ;
- sinon : médiane US × ratio Winamax / médiane US des lignes sans Pinnacle, par marché et
  tranche de cote.

C'est le scénario S2 de nhl/AUDIT_DATA_PARIS_2026-10-04.md (§2.3). Ancré sur Pinnacle, il ne
dépend pas de la dérive des books US d'une saison à l'autre (médiane US / Pinnacle « Oui » :
0,948 en 2023-24, 0,997 en 2024-25). S1 (médiane US × ratio sur toutes les lignes) ne sert
qu'à la comparaison de l'audit (nhl/scripts/audit_price_sensitivity.py).

Les ratios sont figés dans nhl/reports/sim_price.json (versionné, haché dans la version du
simulateur). À recalculer quand la table book_odds aura accumulé assez de vraies cotes FR
(nhl/scripts/fr_odds_report.py).

Usage:
    python -m nhl.sim.real_price      # réécrit sim_price.json depuis winamax_calibration_rows.parquet
"""
import json
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

NHL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIB_ROWS = os.path.join(NHL_DIR, "data", "odds", "winamax_calibration_rows.parquet")
RATIOS_JSON = os.path.join(NHL_DIR, "reports", "sim_price.json")
BANDS = [1, 2, 3, 4.5, 7, 100]
MIN_ROWS = 10  # sous ce nombre de lignes, une tranche prend le ratio médian de son segment

SoftRatios = Dict[Tuple[str, bool, Tuple[float, float]], float]


def calibration_ratios(calib: pd.DataFrame) -> Tuple[SoftRatios, Dict[str, float]]:
    """Ratios Winamax / médiane US par (marché, Pinnacle deux côtés ?, tranche de cote US).

    Returns:
        ({(marché, pin2, (bas, haut)): ratio}, {marché: médiane Winamax / Pinnacle « Oui »}).
    """
    c = calib.dropna(subset=["soft_median"]).copy()
    c["pin2"] = c["pin_no"].notna() & c["pin_yes"].notna()
    c["r"] = c["winamax"] / c["soft_median"]
    soft = {}
    for (mk, pin2), seg in c.groupby(["market", "pin2"]):
        for lo, hi in zip(BANDS[:-1], BANDS[1:]):
            band = seg[(seg.soft_median > lo) & (seg.soft_median <= hi)]
            # Lignes couvertes par Pinnacle : ratio plat d'une tranche à l'autre -> ratio du segment
            use_seg = pin2 or len(band) < MIN_ROWS
            soft[(mk, bool(pin2), (lo, hi))] = float((seg if use_seg else band)["r"].median())
    pin = c[c["pin2"]]
    vs_pin = {mk: float((g["winamax"] / g["pin_yes"]).median()) for mk, g in pin.groupby("market")}
    return soft, vs_pin


def save_ratios(calib: pd.DataFrame, out_path: str = RATIOS_JSON) -> Dict[str, Any]:
    """Écrit les ratios de calibration dans un JSON versionné.

    Args:
        calib: lignes de calibration (winamax_calibration_rows.parquet).
        out_path: fichier de sortie.

    Returns:
        Le contenu écrit.
    """
    soft, vs_pin = calibration_ratios(calib)
    data = {
        "source": "vraies cotes Winamax relevées par nhl/scripts/winamax_calibration.py",
        "dates": [str(calib["date"].min())[:10], str(calib["date"].max())[:10]],
        "games": int(calib["gameId"].nunique()),
        "lines": int(calib["soft_median"].notna().sum()),
        "rule": ("Pinnacle « Oui » × vs_pin si Pinnacle cote ; sinon médiane US × soft "
                 "(marché, sans Pinnacle, tranche de la médiane US)"),
        "vs_pin": vs_pin,
        "soft": [{"market": mk, "pinnacle": pin2, "lo": lo, "hi": hi, "ratio": r}
                 for (mk, pin2, (lo, hi)), r in sorted(soft.items())],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return data


def load_ratios(path: str = RATIOS_JSON) -> Tuple[SoftRatios, Dict[str, float]]:
    """Relit les ratios écrits par save_ratios (même format que calibration_ratios)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    soft = {(r["market"], bool(r["pinnacle"]), (r["lo"], r["hi"])): float(r["ratio"]) for r in data["soft"]}
    return soft, {mk: float(v) for mk, v in data["vs_pin"].items()}


def price_segmented(p: pd.DataFrame, soft_r: SoftRatios) -> pd.Series:
    """S1 : Winamax = médiane US × ratio mesuré (marché, couverture Pinnacle, tranche) ; sinon Pinnacle."""
    px = pd.Series(np.nan, index=p.index)
    pin2 = p["p_novig"].notna()
    for (mk, cov, (lo, hi)), r in soft_r.items():
        m = (p.market == mk) & (pin2 == cov) & (p.soft_median > lo) & (p.soft_median <= hi)
        px[m] = p.loc[m, "soft_median"] * r
    return px.where(px.notna(), p["pin_yes"])


def price_pinnacle(p: pd.DataFrame, s1: pd.Series, vs_pin: Dict[str, float]) -> pd.Series:
    """S2 : Winamax = Pinnacle « Oui » × ratio mesuré quand Pinnacle cote, sinon S1."""
    r = p["market"].map(vs_pin).fillna(1.0)
    return (p["pin_yes"] * r).where(p["pin_yes"].notna(), s1)


def add_real_price(preds: pd.DataFrame,
                   ratios: Optional[Tuple[SoftRatios, Dict[str, float]]] = None) -> pd.DataFrame:
    """Ajoute la colonne `real_price` (prix S2) aux prédictions.

    Args:
        preds: lignes avec market, soft_median, pin_yes et p_novig (simulate_roi.apply_devig).
        ratios: ratios de calibration ; par défaut ceux de sim_price.json.

    Returns:
        Copie de preds avec `real_price` (NaN si ni Pinnacle ni médiane US).
    """
    soft, vs_pin = ratios or load_ratios()
    out = preds.copy()
    out["real_price"] = price_pinnacle(out, price_segmented(out, soft), vs_pin)
    return out


def describe(path: str = RATIOS_JSON) -> str:
    """Règle de prix en une ligne, pour le simulateur."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    fr = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
    names = {"but": "buteur", "ast": "passes"}
    markets = [mk for mk in names if mk in data["vs_pin"]]
    vs = sorted({fr(data["vs_pin"][mk]) for mk in markets})
    vs_txt = vs[0] if len(vs) == 1 else " / ".join(f"{fr(data['vs_pin'][mk])} ({names[mk]})" for mk in markets)
    rng = []
    for mk in markets:
        rs = [r["ratio"] for r in data["soft"] if r["market"] == mk and not r["pinnacle"]]
        rng.append(f"{fr(min(rs))} à {fr(max(rs))} ({names[mk]})")
    return (f"cote Winamax reconstituée : Pinnacle « Oui » × {vs_txt} quand Pinnacle cote, sinon médiane US × "
            f"{' ; '.join(rng)}, d'après {data['lines']} vraies cotes Winamax ({data['games']} matchs, "
            f"{data['dates'][0]} → {data['dates'][1]})")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = save_ratios(pd.read_parquet(CALIB_ROWS))
    print(f"{RATIOS_JSON} : {len(d['soft'])} ratios médiane US, vs Pinnacle {d['vs_pin']}")
    print(describe())
