"""
scripts/tune_betting.py — Calibrage de la stratégie de mise P2 sur la saison de VALIDATION.

Entrée : les prédictions walk-forward d'une phase (nhl/reports/preds_<phase>.parquet).
Seule la saison 2023-24 (validation) est utilisée pour choisir les paramètres ; la
saison 2024-25 (test) n'est JAMAIS regardée ici.

1. Poids du mélange modèle / Pinnacle (w) : minimise la log-loss en validation.
2. Fenêtres de cotes et seuils d'EV, par marché : maximise le ROI RÉALISÉ en validation
   (≥ MIN_BETS paris). Le profit attendu sous Pinnacle est affiché en contrôle : il est
   négatif pour tous les réglages au prix médian ×0,94 (cf. rapport), il ne peut donc
   pas servir de critère. Le juge final reste la saison de test, jamais vue ici.
3. Paris sans référence Pinnacle : majoration d'EV choisie sur le ROI réalisé en
   validation (≥ 40 paris exigés, sinon ces paris sont désactivés).

Usage:
    python nhl/scripts/tune_betting.py --phase p1b_lgbm
"""
import argparse
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.betting import BetParams, select_bets  # noqa: E402
from nhl.scripts.simulate_roi import REPORT_DIR, VAL_END  # noqa: E402

BANKROLL = 100.0
EV_GRID = {"0": (0.0, 0.0, 0.0), "low": (0.03, 0.02, 0.05), "std": (0.08, 0.05, 0.10), "high": (0.12, 0.08, 0.15)}
GRID = {
    "but": {"cote_min": [1.5, 2.0, 3.0, 4.5], "cote_max": [6.0, 10.0, 25.0]},
    "ast": {"cote_min": [1.5, 1.8, 2.2, 2.5], "cote_max": [3.5, 5.0, 8.0]},
}
NO_PIN_GRID = [0.05, 0.10, 0.20]
DISABLED = 9.0
MIN_BETS = 60  # majoration impossible à atteindre = paris sans Pinnacle désactivés


def fit_blend_weight(val: pd.DataFrame) -> float:
    """w minimisant la log-loss de w*p_model + (1-w)*p_novig en validation."""
    q = val.dropna(subset=["p_novig"])
    best = min(np.linspace(0, 1, 21),
               key=lambda w: log_loss(q["won"], np.clip(w * q["p_model"] + (1 - w) * q["p_novig"], 1e-6, 1 - 1e-6)))
    return float(best)


def simulate(val: pd.DataFrame, params: BetParams) -> pd.DataFrame:
    """Rejoue select_bets jour par jour (bankroll fixe en unités)."""
    out = []
    for _, day in val.groupby("date", sort=True):
        cands = [{"market": r.market, "p_model": r.p_model, "p_novig": r.p_novig, "cote": r.exec_price,
                  "game_id": r.gameId, "won": r.won} for r in day.itertuples(index=False)]
        for b in select_bets(cands, BANKROLL, params):
            out.append(b)
    b = pd.DataFrame(out)
    if b.empty:
        return b
    b["profit"] = np.where(b["won"] == 1, b["mise"] * (b["cote"] - 1), -b["mise"])
    b["exp_profit_pin"] = b["mise"] * (b["p_novig"] * b["cote"] - 1)
    return b


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    a = ap.parse_args()
    preds = pd.read_parquet(os.path.join(REPORT_DIR, f"preds_{a.phase}.parquet"))
    preds["date"] = pd.to_datetime(preds["date"])
    # Même éligibilité que la phase P2 (passeurs à domicile ET à l'extérieur)
    from nhl.sim.phases import p2_eligible
    parts = []
    for m in ("but", "ast"):
        sub = preds[preds["market"] == m].reset_index(drop=True)
        sub["eligible"] = p2_eligible(sub, m).to_numpy()
        parts.append(sub)
    preds = pd.concat(parts, ignore_index=True)
    val = preds[(preds["date"] < VAL_END) & preds["eligible"] & preds["exec_price"].notna()].copy()
    print(f"Validation : {len(val):,} lignes éligibles cotées ({val.date.min().date()} → {val.date.max().date()})")

    chosen = {}
    for m in ("but", "ast"):
        w = fit_blend_weight(val[val.market == m])
        chosen[f"blend_w_{m}"] = w
        print(f"[{m}] poids modèle w = {w:.2f}")

    # Grille par marché (les marchés sont simulés séparément, exposition non partagée)
    for m in ("but", "ast"):
        vm = val[val.market == m]
        rows = []
        for cmin, cmax, (ev_name, ev) in itertools.product(GRID[m]["cote_min"], GRID[m]["cote_max"], EV_GRID.items()):
            if cmin >= cmax:
                continue
            params = BetParams.from_config(
                markets=(m,), blend_w={"but": chosen["blend_w_but"], "ast": chosen["blend_w_ast"]},
                cote_min={m: cmin}, cote_max={m: cmax}, ev_low=ev[0], ev_mid=ev[1], ev_high=ev[2],
                no_pinnacle_extra_ev=DISABLED, max_daily_exposure=1e9)
            params.no_pinnacle_extra_ev = 0.05  # paris sans Pinnacle inclus (réglés plus bas)
            b = simulate(vm, params)
            exp = float(b["exp_profit_pin"].fillna(0).sum()) if not b.empty else 0.0
            rows.append({"cote_min": cmin, "cote_max": cmax, "ev": ev_name, "n": len(b),
                         "stake": float(b["mise"].sum()) if not b.empty else 0.0, "exp_profit_pin": exp,
                         "roi_realise": float(b["profit"].sum() / b["mise"].sum()) if not b.empty else np.nan})
        g = pd.DataFrame(rows)
        print(f"\n[{m}] grille complète : {len(g)} réglages, nb de paris max = {g['n'].max()}")
        g = g[g["n"] >= MIN_BETS].sort_values("roi_realise", ascending=False)
        print(f"[{m}] top 8 (validation, ≥ {MIN_BETS} paris, ROI réalisé ; profit attendu sous Pinnacle en contrôle) :")
        print(g.head(8).to_string(index=False))
        if g.empty or g.iloc[0]["roi_realise"] <= 0:
            print(f"  ⚠️ [{m}] aucun réglage rentable en validation → marché désactivé.")
            chosen[f"enable_{m}"] = False
            best = pd.Series({"cote_min": GRID[m]["cote_min"][0], "cote_max": GRID[m]["cote_max"][-1], "ev": "high"})
        else:
            chosen[f"enable_{m}"] = True
            best = g.iloc[0]
        chosen[f"cote_min_{m}"], chosen[f"cote_max_{m}"] = float(best["cote_min"]), float(best["cote_max"])
        chosen[f"ev_{m}"] = best["ev"]

    # Paris sans Pinnacle : majoration d'EV choisie sur le ROI réalisé en validation
    ev_names = {chosen[f"ev_{m}"] for m in ("but", "ast") if chosen[f"enable_{m}"]} or {"high"}
    ev_pick = EV_GRID[max(ev_names, key=lambda k: EV_GRID[k][1])]  # le plus prudent des deux
    best_np, best_roi = DISABLED, 0.0
    markets = tuple(m for m in ("but", "ast") if chosen[f"enable_{m}"])
    for extra in NO_PIN_GRID:
        params = BetParams.from_config(
            markets=markets, blend_w={"but": chosen["blend_w_but"], "ast": chosen["blend_w_ast"]},
            cote_min={m: chosen[f"cote_min_{m}"] for m in ("but", "ast")},
            cote_max={m: chosen[f"cote_max_{m}"] for m in ("but", "ast")},
            ev_low=ev_pick[0], ev_mid=ev_pick[1], ev_high=ev_pick[2], no_pinnacle_extra_ev=extra)
        b = simulate(val[val.p_novig.isna()], params) if markets else pd.DataFrame()
        n = len(b)
        roi = float(b["profit"].sum() / b["mise"].sum()) if n else np.nan
        print(f"[sans Pinnacle] extra EV {extra:.2f} : {n} paris, ROI réalisé {roi * 100 if n else float('nan'):+.1f}%")
        if n >= 40 and roi > best_roi:
            best_np, best_roi = extra, roi
    chosen["no_pinnacle_extra_ev"] = best_np
    chosen["ev_thresholds"] = ev_pick
    print("\nRéglages retenus (validation uniquement) :")
    print(json.dumps(chosen, indent=2, default=str))
    with open(os.path.join(REPORT_DIR, f"betting_params_{a.phase}.json"), "w", encoding="utf-8") as f:
        json.dump(chosen, f, indent=2, default=str)


if __name__ == "__main__":
    main()
