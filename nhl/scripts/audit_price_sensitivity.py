"""
scripts/audit_price_sensitivity.py — Reproduit les chiffres de nhl/AUDIT_DATA_PARIS_2026-10-04.md.

Lecture seule : aucun fichier n'est écrit, tout est imprimé.

1. Calibration Winamax (15 matchs) : ratio Winamax / médiane US selon que Pinnacle cote ou non
   les deux côtés, et dérive historique médiane US / Pinnacle « Oui ».
2. Backtest de la config de prod (phase q_final) rejoué avec plusieurs règles de prix
   d'exécution : celle du backtest (décote uniforme), décotes uniformes, prix segmenté selon la
   calibration, prix ancré sur Pinnacle, et « prod réaliste » (proposé au prix proxy, pris
   seulement si le prix Winamax estimé dépasse la cote seuil).
3. Tests statistiques : gain observé contre gain attendu si Pinnacle a raison (z analytique),
   log-loss modèle vs Pinnacle (IC bootstrap par soirée), poids de mélange optimal par période,
   rapport de vraisemblance p_final / Pinnacle sur les picks.

Prérequis (fichiers non versionnés) : nhl/reports/preds_q_final.parquet
(python nhl/scripts/simulate_roi.py --phase q_final), nhl/data/odds/odds_wide.parquet,
nhl/data/odds/winamax_calibration_rows.parquet.

Usage:
    python nhl/scripts/audit_price_sensitivity.py
"""
import math
import os
import sys
from typing import Dict, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.betting import BetParams, select_bets  # noqa: E402
from nhl.scripts.simulate_roi import ODDS_WIDE, REPORT_DIR, VAL_END, add_prod_price, apply_devig  # noqa: E402
# Prix S1 / S2 : partagés avec le simulateur (S2 = prix réaliste de simulateur.html)
from nhl.sim.real_price import CALIB_ROWS, calibration_ratios, price_pinnacle, price_segmented  # noqa: E402

pd.set_option("display.width", 250)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Calibration Winamax
# ─────────────────────────────────────────────────────────────────────────────
def print_calibration(calib: pd.DataFrame) -> None:
    c = calib.dropna(subset=["soft_median"]).copy()
    c["couverture"] = np.where(c["pin_no"].notna() & c["pin_yes"].notna(), "Pinnacle 2 côtés", "sans Pinnacle")
    c["r"] = c["winamax"] / c["soft_median"]
    print("\n== 1a. Winamax / médiane US (15 matchs, oct. 2026)")
    print(c.groupby(["market", "couverture"])["r"].agg(["median", "count"]).round(3).to_string())
    w = pd.read_parquet(ODDS_WIDE)
    w["date"] = pd.to_datetime(w["date"])
    h = w[(w.market == "but")].dropna(subset=["soft_median", "pin_yes"]).copy()
    h["saison"] = np.where(h.date < VAL_END, "2023-24", "2024-25")
    h["r"] = h["soft_median"] / h["pin_yes"]
    cal = c[(c.market == "but") & c.pin_yes.notna()]
    print("\n== 1b. Buteur : médiane US / Pinnacle « Oui » (dérive du marché US)")
    print(h.groupby("saison")["r"].agg(["median", "count"]).round(3).to_string())
    print(f"2026-27 (calibration) : {float((cal.soft_median / cal.pin_yes).median()):.3f} ({len(cal)} lignes)")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Backtest de la config de prod avec plusieurs règles de prix
# ─────────────────────────────────────────────────────────────────────────────
def load_preds() -> pd.DataFrame:
    """Prédictions walk-forward de q_final + prix de prod + no-vig de Shin (comme simulate_roi.run)."""
    p = pd.read_parquet(os.path.join(REPORT_DIR, "preds_q_final.parquet"))
    p = apply_devig(add_prod_price(p), "shin")
    if "pin_no" not in p:
        o = pd.read_parquet(ODDS_WIDE, columns=["date", "playerId", "market", "pin_no"])
        o["date"] = pd.to_datetime(o["date"])
        p = p.merge(o, on=["date", "playerId", "market"], how="left")
    return p.reset_index(drop=True)


def run(p: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    """Rejoue select_bets (config de settings.toml) soirée par soirée au prix donné."""
    params = BetParams.from_config()
    d = p[p["eligible"]].assign(px=price)
    d = d[d["px"].notna() & (d["px"] > 1.01)]
    rows = []
    for _, day in d.groupby("date", sort=True):
        rows += select_bets([{"market": r.market, "p_model": float(r.p_model), "p_novig": r.p_novig,
                              "cote": float(r.px), "game_id": r.gameId, "won": int(r.won),
                              "playerId": r.playerId, "date": r.date} for r in day.itertuples(index=False)],
                            100.0, params)
    b = pd.DataFrame(rows)
    b["profit"] = np.where(b["won"] == 1, b["mise"] * (b["cote"] - 1), -b["mise"])
    b["period"] = np.where(b["date"] < VAL_END, "val", "ctrl")
    return b


def take_at_real_price(base: pd.DataFrame, p: pd.DataFrame, real: pd.Series) -> pd.DataFrame:
    """Prod réaliste : picks proposés au prix proxy, pris au prix réel s'il dépasse la cote seuil."""
    idx = pd.MultiIndex.from_frame(p[["date", "playerId", "market"]])
    b = base.copy()
    b["real"] = pd.Series(real.to_numpy(), index=idx).reindex(
        pd.MultiIndex.from_frame(b[["date", "playerId", "market"]])).to_numpy()
    t = b[b["real"].notna() & (b["real"] >= b["cote_seuil"])].copy()
    t["cote"] = t["real"]
    t["profit"] = np.where(t["won"] == 1, t["mise"] * (t["cote"] - 1), -t["mise"])
    return t


def z_vs_pinnacle(b: pd.DataFrame) -> Tuple[float, float, float]:
    """Gain observé vs gain attendu si les résultats suivaient Pinnacle (1/cote sans Pinnacle).

    Returns:
        (gain attendu, z, p-value unilatérale) — approximation normale, sans résolution Monte Carlo.
    """
    p0 = np.where(b["p_novig"].notna(), b["p_novig"].astype(float), 1.0 / b["cote"])
    win, lose = b["mise"] * (b["cote"] - 1), -b["mise"]
    mu = float((p0 * win + (1 - p0) * lose).sum())
    sd = float(np.sqrt((p0 * (1 - p0) * (win - lose) ** 2).sum()))
    z = (b["profit"].sum() - mu) / sd
    return mu, z, 0.5 * math.erfc(z / math.sqrt(2))  # P(Z > z), loi normale


def summary(b: pd.DataFrame, label: str) -> Dict:
    out = {"scénario": label}
    for per in ("val", "ctrl"):
        x = b[b["period"] == per]
        pin = x.dropna(subset=["p_novig"])
        _, z, _ = z_vs_pinnacle(x)
        out.update({f"{per}_paris": len(x), f"{per}_gain": round(x["profit"].sum(), 1),
                    f"{per}_roi%": round(100 * x["profit"].sum() / x["mise"].sum(), 1),
                    f"{per}_evpin%": round(100 * (pin["p_novig"] * pin["cote"] - 1).mean(), 1),
                    f"{per}_z": round(z, 2)})
    d = b.groupby("date")["profit"].sum().sort_index().cumsum()
    out["max_dd"] = round(float((d.cummax().clip(lower=0) - d).max()), 1)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 3. Le modèle bat-il Pinnacle ?
# ─────────────────────────────────────────────────────────────────────────────
def _ll(y: pd.Series, x: pd.Series) -> np.ndarray:
    x = np.clip(x.to_numpy(float), 1e-4, 1 - 1e-4)
    return -(y.to_numpy() * np.log(x) + (1 - y.to_numpy()) * np.log(1 - x))


def model_vs_pinnacle(p: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> None:
    q = p[p["eligible"] & p["p_novig"].notna()].copy()
    q["period"] = np.where(q["date"] < VAL_END, "val", "ctrl")
    rng = np.random.default_rng(seed)
    print("\n== 3a. Log-loss modèle − Pinnacle (mnats/ligne, négatif = modèle meilleur), IC 95 % par soirée")
    for (mk, per), g in q.groupby(["market", "period"]):
        d = pd.Series(_ll(g["won"], g["p_model"]) - _ll(g["won"], g["p_novig"]), index=g.index)
        daily = d.groupby(g["date"]).agg(["sum", "count"])
        i = rng.integers(0, len(daily), (n_boot, len(daily)))
        boot = daily["sum"].to_numpy()[i].sum(1) / daily["count"].to_numpy()[i].sum(1)
        ws = np.linspace(0, 1, 21)
        w_opt = ws[int(np.argmin([_ll(g["won"], w * g["p_model"] + (1 - w) * g["p_novig"]).mean() for w in ws]))]
        print(f"  {mk:3s} {per:4s} n={len(g):6d}  dLL={1000 * d.mean():+.2f} [{1000 * np.percentile(boot, 2.5):+.2f} ; "
              f"{1000 * np.percentile(boot, 97.5):+.2f}]  poids optimal du modèle={w_opt:.2f}")


def llr_on_picks(b: pd.DataFrame) -> None:
    """Sur les picks : le résultat donne-t-il raison à p_final ou au no-vig Pinnacle ?"""
    x = b.dropna(subset=["p_novig"]).copy()
    pf, pn = x["p_final"].clip(1e-4, 1 - 1e-4), x["p_novig"].clip(1e-4, 1 - 1e-4)
    x["llr"] = np.where(x["won"] == 1, np.log(pf / pn), np.log((1 - pf) / (1 - pn)))
    print("\n== 3b. Rapport de vraisemblance p_final / Pinnacle sur les picks (z > 2 : le modèle a raison)")
    for (mk, per), g in x.groupby(["market", "period"]):
        z = g["llr"].mean() / (g["llr"].std(ddof=1) / np.sqrt(len(g)))
        print(f"  {mk:3s} {per:4s} n={len(g):4d}  z={z:+.2f}  écart moyen p_final − p_novig = "
              f"{100 * (g['p_final'] - g['p_novig']).mean():+.1f} pts")


def main() -> None:
    calib = pd.read_parquet(CALIB_ROWS)
    print_calibration(calib)
    soft_r, vs_pin = calibration_ratios(calib)

    p = load_preds()
    is_but = p["market"] == "but"
    base = run(p, p["prod_price"])
    rows = [summary(base, "S0 prix du backtest (buteur ×1,078, passes ×1,00)")]
    for h in (1.00, 1.04, 1.10):
        px = p["prod_price"].copy()
        px[is_but & p["soft_median"].notna()] = p["soft_median"] * h
        rows.append(summary(run(p, px), f"décote buteur uniforme ×{h:.2f}"))
    s1 = price_segmented(p, soft_r)
    s2 = price_pinnacle(p, s1, vs_pin)
    b1, b2 = run(p, s1), run(p, s2)
    rows.append(summary(b1, "S1 prix segmenté (couverture Pinnacle × tranche)"))
    rows.append(summary(b2, "S2 Winamax = Pinnacle « Oui » (sinon S1)"))
    rows.append(summary(take_at_real_price(base, p, s1), "Prod réaliste S1 (proxy puis prix réel ≥ seuil)"))
    rows.append(summary(take_at_real_price(base, p, s2), "Prod réaliste S2 (proxy puis prix réel ≥ seuil)"))
    print(f"\n== 2. Config de prod rejouée ({len(base)} paris au prix du backtest)")
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n== 2a. Par marché aux prix réalistes")
    for lab, b in (("S1", b1), ("S2", b2)):
        for (mk, per), g in b.groupby(["market", "period"]):
            _, z, _ = z_vs_pinnacle(g)
            print(f"  {lab} {mk:3s} {per:4s} n={len(g):4d} gain={g.profit.sum():+6.1f} U "
                  f"ROI={100 * g.profit.sum() / g.mise.sum():+6.1f} % z={z:+.2f}")

    print("\n== 2b. Décomposition du backtest (S0) par marché et période")
    for (mk, per), g in base.groupby(["market", "period"]):
        mu, z, pv = z_vs_pinnacle(g)
        pin = g.dropna(subset=["p_novig"])
        print(f"  {mk:3s} {per:4s} n={len(g):4d} gain={g.profit.sum():+6.1f} U ROI={100 * g.profit.sum() / g.mise.sum():+6.1f} % "
              f"réussite={g.won.mean():.3f} p_final={g.p_final.mean():.3f} p_novig={pin.p_novig.mean():.3f} "
              f"attendu(Pinnacle)={mu:+.1f} z={z:+.2f} p={pv:.2g}")
    top = base.sort_values("profit", ascending=False)
    print(f"  5 meilleurs paris : {top.profit.head(5).sum():+.1f} U sur {base.profit.sum():+.1f} U ; "
          f"sans les 10 meilleurs : {top.profit.iloc[10:].sum():+.1f} U")

    model_vs_pinnacle(p)
    llr_on_picks(base)


if __name__ == "__main__":
    main()
