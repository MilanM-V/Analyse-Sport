"""
scripts/simulate_early.py — Backtest du mode découverte ([early_season]) : picks avant 10 matchs.

Rejoue la config de prod (prédictions walk-forward p1b_ens, prix de prod, no-vig Shin,
nhl/core/betting.select_bets) en ajoutant les joueurs à moins de 10 matchs cette saison, évalués
par market_filter.evaluate_early_season (G/GP et A/GP mélangés avec la saison passée).

Règle de décision fixée avant de lancer : seuil d'EV choisi sur la VALIDATION (début de saison
2023-24) ; si le gain des picks découverte y est négatif pour tous les seuils, le mode reste
désactivé. Le contrôle (début de saison 2024-25) est affiché à part.

Usage:
    python nhl/scripts/simulate_early.py      # -> nhl/reports/EARLY_SEASON_2026-10-04.md
"""
import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.config.settings import cfg  # noqa: E402
from nhl.core.betting import BetParams, select_bets  # noqa: E402
from nhl.scripts.simulate_roi import GAMELOG_MP, REPORT_DIR, VAL_END  # noqa: E402

REPORT_MD = os.path.join(REPORT_DIR, "EARLY_SEASON_2026-10-04.md")
EV_GRID = [0.08, 0.12, 0.15]


def prev_season_stats() -> pd.DataFrame:
    """GP, G/GP et A/GP de chaque joueur par saison, rattachés à la saison SUIVANTE."""
    gl = pd.read_parquet(GAMELOG_MP, columns=["playerId", "season", "g", "a1", "a2"])
    gl["a"] = gl["a1"] + gl["a2"]
    s = gl.groupby(["playerId", "season"]).agg(GP=("g", "size"), G=("g", "sum"), A=("a", "sum")).reset_index()
    s["G_GP"], s["A_GP"] = s["G"] / s["GP"], s["A"] / s["GP"]
    s["season"] += 1
    return s[["playerId", "season", "GP", "G_GP", "A_GP"]]


def early_eligible(df: pd.DataFrame) -> pd.Series:
    """Éligibilité découverte (prod : bot_logic filtre ATOI puis evaluate_early_season)."""
    from nhl.core.market_filter import evaluate_early_season
    atoi_min = cfg.thresholds.general.atoi_min
    out = []
    for r in df.itertuples(index=False):
        if r.ATOI_L10 < atoi_min or r.prev_GP != r.prev_GP:
            out.append(False)
            continue
        p_form = {"ATOI": r.ATOI_L10}
        v5 = {"G_GP": r.G_GP, "A_GP": r.A_GP, "GP": int(r.std_gp), "Position": r.pos_bot}
        prev = {"GP": r.prev_GP, "G_GP": r.prev_G_GP, "A_GP": r.prev_A_GP}
        cb, ca, phase = evaluate_early_season("", p_form, v5, {}, bool(r.is_home), prev)
        out.append(phase == "early" and bool(cb if r.market == "but" else ca))
    return pd.Series(out, index=df.index)


def load() -> pd.DataFrame:
    from nhl.scripts.search_config import load_engine
    d = load_engine("p1b_ens")
    seasons = pd.read_parquet(GAMELOG_MP, columns=["gameId", "season"]).drop_duplicates("gameId")
    d = d.merge(seasons, on="gameId", how="left")
    prev = prev_season_stats().rename(columns={"GP": "prev_GP", "G_GP": "prev_G_GP", "A_GP": "prev_A_GP"})
    d = d.merge(prev, on=["playerId", "season"], how="left")
    cfg.early_season.enabled = True
    try:
        d["early"] = False
        m = (d["std_gp"] < 10) & d["prod_price"].notna()
        d.loc[m, "early"] = early_eligible(d[m]).to_numpy()
    finally:
        cfg.early_season.enabled = False
    return d


def run(d: pd.DataFrame, params: BetParams, with_early: bool) -> pd.DataFrame:
    """Paris de toutes les soirées (config de prod, mode découverte en option)."""
    keep = d["prod_price"].notna() & (d["eligible"] | (d["early"] if with_early else False))
    rows: List[dict] = []
    for date, day in d[keep].groupby("date", sort=True):
        cands = [{"market": x.market, "p_model": float(x.p_model),
                  "p_novig": (float(x.p_novig) if x.p_novig == x.p_novig else None),
                  "cote": float(x.prod_price), "game_id": x.gameId, "won": int(x.won), "date": date,
                  "early": bool(x.early and not x.eligible)}
                 for x in day.itertuples(index=False)]
        rows += select_bets(cands, 100.0, params)
    b = pd.DataFrame(rows)
    b["profit"] = np.where(b["won"] == 1, b["mise"] * (b["cote"] - 1), -b["mise"])
    b["ev_pin"] = b["p_novig"] * b["cote"] - 1
    return b


def stats(b: pd.DataFrame) -> Dict[str, float]:
    if b.empty:
        return {"n": 0, "mise": 0.0, "gain": 0.0, "roi": np.nan, "ev_pin": np.nan, "esp_sans_edge": 0.0}
    pin = b.dropna(subset=["p_novig"])
    return {"n": len(b), "mise": b["mise"].sum(), "gain": b["profit"].sum(),
            "roi": b["profit"].sum() / b["mise"].sum(),
            "ev_pin": pin["ev_pin"].mean() if len(pin) else np.nan,
            # gain attendu si les résultats suivaient la proba Pinnacle (aucun avantage du modèle)
            "esp_sans_edge": float((pin["mise"] * pin["ev_pin"]).sum())}


def main() -> None:
    d = load()
    periods = {"Validation 2023-24": lambda x: x["date"] < VAL_END,
               "Contrôle 2024-25": lambda x: x["date"] >= VAL_END}
    base = run(d, BetParams.from_config(), with_early=False)
    lines = ["# Mode découverte : picks avant 10 matchs — backtest", "",
             "Config de prod (Équilibré, 1 pari / match) + joueurs à moins de 10 matchs cette saison, "
             "G/GP et A/GP mélangés avec la saison passée (k = 10, au moins 20 matchs la saison passée), "
             "mise Kelly × 0,5. Seuil d'EV choisi sur la validation ; contrôle affiché à part.", ""]
    res = {}
    for ev in EV_GRID:
        b = run(d, BetParams.from_config(early_ev_min=ev, early_stake_mult=0.5), with_early=True)
        res[ev] = b
    for name, f in periods.items():
        lines += [f"## {name}", "",
                  "| EV min découverte | Picks découverte | Mise | Gain | ROI | EV vs Pinnacle | Gain attendu sans avantage | Gain total saison (vs sans le mode) |",
                  "|---|---|---|---|---|---|---|---|"]
        tb = stats(base[f(base)])
        for ev, b in res.items():
            bp = b[f(b)]
            e, t = stats(bp[bp["early"]]), stats(bp)
            lines.append(f"| {ev:.0%} | {e['n']} | {e['mise']:.1f} U | {e['gain']:+.1f} U | {e['roi']:+.1%} | "
                         f"{e['ev_pin']:+.1%} | {e['esp_sans_edge']:+.1f} U | {t['gain']:+.1f} U ({t['gain'] - tb['gain']:+.1f}) |")
        lines += ["", f"Sans le mode : {tb['n']} paris, {tb['gain']:+.1f} U.", ""]
    val = {ev: stats(b[(b["date"] < VAL_END) & b["early"]])["gain"] for ev, b in res.items()}
    best = max(val, key=val.get)
    verdict = (f"Meilleur seuil en validation : EV ≥ {best:.0%} ({val[best]:+.1f} U)."
               if val[best] > 0 else "Gain négatif en validation pour tous les seuils : mode laissé désactivé.")
    lines += ["## Décision", "", verdict, ""]
    with open(REPORT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
