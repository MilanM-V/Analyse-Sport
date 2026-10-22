"""
scripts/engine_report.py — Résultats d'un moteur, saison par saison, contre le moteur actuel et Pinnacle.

Lit les prédictions walk-forward de deux phases de simulate_roi.py (par défaut `v2`, le
nouveau moteur, et `m0`, le moteur actuel tel que servi), prédites sur TOUTES les lignes
éligibles (option `all_eligible`), cotées ou non. Pour chaque saison (2023-24, 2024-25,
2025-26) et chaque marché :
  - qualité : Δ log-loss nouveau − actuel sur toutes les lignes éligibles, en millinats
    (1 mnat = 0,001 nat par ligne ; négatif = mieux), IC 95 % bootstrap par soirée ;
  - contre Pinnacle (lignes où Pinnacle cote les deux côtés, no-vig de Shin) : modèle seul et
    mélange de prod (w de [betting]) ;
  - calibration par tranche de probabilité, nombre de valeurs distinctes ;
  - argent : paris de la stratégie de prod au prix réaliste (nhl/sim/real_price.py), config
    de prod et « buteur seul », bankroll 100 U ; z = écart du gain à ce qu'attendait Pinnacle.

Usage:
    python nhl/scripts/engine_report.py                 # v2 contre m0
    python nhl/scripts/engine_report.py --new v2 --ref m0
"""
import argparse
import json
import os
import sys
from typing import Dict, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.betting import BetParams  # noqa: E402
from nhl.scripts.simulate_roi import REPORT_DIR, variance_metrics  # noqa: E402

SEASONS = {"2023-24": ("2023-07-01", "2024-07-01"), "2024-25": ("2024-07-01", "2025-07-01"),
           "2025-26": ("2025-07-01", "2026-07-01")}
BUCKETS = [(0.15, 0.20), (0.20, 0.25), (0.25, 0.30), (0.30, 0.35), (0.35, 0.50)]
OUT_JSON = os.path.join(REPORT_DIR, "engine_v2_results.json")


def _ll(y: np.ndarray, q: np.ndarray) -> np.ndarray:
    q = np.clip(np.asarray(q, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def delta_ll(y, q_new, q_ref, nights, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """Δ log-loss moyen par ligne (mnat, négatif = q_new meilleur), IC 95 % bootstrap par soirée."""
    d = _ll(y, q_new) - _ll(y, q_ref)
    s = pd.DataFrame({"d": d, "n": np.asarray(nights)}).groupby("n")["d"].agg(["sum", "count"])
    su, co = s["sum"].to_numpy(), s["count"].to_numpy()
    idx = np.random.default_rng(seed).integers(0, len(s), size=(n_boot, len(s)))
    boot = su[idx].sum(1) / co[idx].sum(1)
    return {"n": int(len(d)), "nights": int(len(s)), "d_mnat": float(d.mean() * 1000),
            "lo": float(np.percentile(boot, 2.5) * 1000), "hi": float(np.percentile(boot, 97.5) * 1000)}


def calibration(y: np.ndarray, p: np.ndarray) -> list:
    """Réussite observée par tranche de probabilité annoncée."""
    out = []
    for lo, hi in BUCKETS:
        m = (p >= lo) & (p < hi)
        if m.sum() >= 50:
            out.append({"tranche": f"{lo:.0%}-{hi:.0%}", "n": int(m.sum()), "annonce": float(p[m].mean()),
                        "observe": float(y[m].mean())})
    return out


def money(bets: pd.DataFrame) -> Dict[str, float]:
    """Paris, gain, ROI, z (contre l'hypothèse « aucun edge » de Pinnacle) et drawdown d'un ensemble de paris."""
    if bets.empty:
        return {"n": 0}
    p0 = np.where(bets["p_novig"].notna(), bets["p_novig"].astype(float), 1.0 / bets["cote"])
    win, lose = bets["mise"] * (bets["cote"] - 1), bets["mise"]
    exp = (p0 * win - (1 - p0) * lose).sum()
    var = (p0 * (1 - p0) * (win + lose) ** 2).sum()
    v = variance_metrics(bets)
    return {"n": int(len(bets)), "mise": float(bets["mise"].sum()), "gain": float(bets["profit"].sum()),
            "roi": float(bets["profit"].sum() / bets["mise"].sum()),
            "z": float((bets["profit"].sum() - exp) / np.sqrt(var)) if var > 0 else None,
            "max_dd": float(v["max_dd"]), "soirees": int(v["n_nights"])}


def season_of(dates: pd.Series) -> pd.Series:
    out = pd.Series(None, index=dates.index, dtype=object)
    for s, (a, b) in SEASONS.items():
        out[(dates >= a) & (dates < b)] = s
    return out


def report(new: str, ref: str) -> Dict:
    from nhl.scripts.export_simulator_data import load_preds
    from nhl.scripts.search_config import Config, W_BASE, day_candidates, run_config
    frames = {k: load_preds(k, end=None) for k in (new, ref)}
    key = ["date", "playerId", "market"]
    a = frames[new][frames[new]["eligible"]]
    b = frames[ref][frames[ref]["eligible"]][key + ["p_model"]].rename(columns={"p_model": "p_ref"})
    d = a.merge(b, on=key, how="inner")
    d["season"] = season_of(d["date"])
    d = d[d["season"].notna()]
    w = BetParams.from_config().blend_w
    res: Dict = {"new": new, "ref": ref, "blend_w": w, "quality": {}, "money": {}}
    for (season, mk), u in d.groupby(["season", "market"]):
        y = u["won"].to_numpy()
        r = {"vs_ref": delta_ll(y, u["p_model"], u["p_ref"], u["date"]),
             "calibration_new": calibration(y, u["p_model"].to_numpy()),
             "calibration_ref": calibration(y, u["p_ref"].to_numpy()),
             "distinct_15_50": {"new": int(u.loc[u.p_model.between(0.15, 0.5), "p_model"].round(6).nunique()),
                                "ref": int(u.loc[u.p_ref.between(0.15, 0.5), "p_ref"].round(6).nunique())}}
        pin = u[u["p_novig"].notna()]
        if len(pin) > 500:
            yp = pin["won"].to_numpy()
            for tag, col in (("new", "p_model"), ("ref", "p_ref")):
                blend = w[mk] * pin[col] + (1 - w[mk]) * pin["p_novig"]
                r[f"{tag}_vs_pinnacle"] = delta_ll(yp, pin[col], pin["p_novig"], pin["date"])
                r[f"{tag}_blend_vs_pinnacle"] = delta_ll(yp, blend, pin["p_novig"], pin["date"])
        res["quality"][f"{season}|{mk}"] = r
    cur = BetParams.from_config()
    for eng in (new, ref):
        cands = day_candidates(frames[eng])
        for label, markets in (("prod", tuple(cur.markets)), ("buteur", ("but",))):
            cfg = Config(eng, markets, cur.ev_mid, round(cur.blend_w["but"] - W_BASE["but"], 2),
                         cur.cote_max["but"], cur.max_bets_per_game)
            bets = run_config(cands, cfg)
            if bets.empty:
                continue
            bets["season"] = season_of(pd.to_datetime(bets["date"]))
            for season, t in bets.groupby("season"):
                res["money"][f"{eng}|{label}|{season}"] = money(t)
    return res


def _fmt(x: Optional[Dict]) -> str:
    return "—" if not x else f"{x['d_mnat']:+.2f} [{x['lo']:+.2f} ; {x['hi']:+.2f}]"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--new", default="v2")
    ap.add_argument("--ref", default="m0")
    a = ap.parse_args()
    res = report(a.new, a.ref)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=float)
    print(f"| Saison | Marché | Lignes | {a.new} − {a.ref} | {a.ref} mélangé − Pinnacle | {a.new} mélangé − Pinnacle |")
    print("|---|---|---|---|---|---|")
    for k, r in res["quality"].items():
        season, mk = k.split("|")
        print(f"| {season} | {mk} | {r['vs_ref']['n']:,} | {_fmt(r['vs_ref'])} | {_fmt(r.get('ref_blend_vs_pinnacle'))} "
              f"| {_fmt(r.get('new_blend_vs_pinnacle'))} |")
    print("\n| Moteur | Config | Saison | Paris | Gain (U) | ROI | z | Drawdown |")
    print("|---|---|---|---|---|---|---|---|")
    for k, m in res["money"].items():
        eng, label, season = k.split("|")
        if m.get("n"):
            print(f"| {eng} | {label} | {season} | {m['n']} | {m['gain']:+.1f} | {m['roi']:+.1%} | {m['z']:+.2f} | {m['max_dd']:.1f} |")
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    main()
