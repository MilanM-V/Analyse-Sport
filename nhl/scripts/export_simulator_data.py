"""
scripts/export_simulator_data.py — Injecte les données réelles du moteur dans simulateur.html.

Source : prédictions walk-forward (nhl/reports/preds_<src>.parquet) rejouées avec la
stratégie de prod (nhl/core/betting.select_bets + settings.toml [betting]) pour trois
prix d'exécution : médiane soft books × 0,94 (proxy Winamax), médiane brute, meilleure cote.

Les paris sont regroupés par SOIRÉE (toutes les soirées cotées, y compris celles sans
pari) : le simulateur rééchantillonne des soirées entières, ce qui conserve la
corrélation des paris d'un même soir et le vrai rythme de picks.

Le JSON est écrit entre les marqueurs /*DATA_START*/ et /*DATA_END*/ de simulateur.html.

Usage:
    python nhl/scripts/export_simulator_data.py [--src p1b_ens]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.betting import BetParams, select_bets  # noqa: E402
from nhl.scripts.simulate_roi import REPORT_DIR, VAL_END  # noqa: E402
from nhl.sim.phases import p2_eligible  # noqa: E402
from nhl.sim.version import current_version  # noqa: E402

HTML = os.path.join(ROOT, "simulateur.html")
SCENARIOS = {
    # Prix calculé exactement comme la prod (shared.odds_api.apply_proxy) : médiane soft × 0,94,
    # et pour les passes (cotées par Pinnacle seul en live) Pinnacle × pin_haircut.
    "exec": ("Prix de la prod (proxy ; passes = Pinnacle × 0,90)", "prod_price", 1.0),
    "median": ("Prix médian des books (multi-books FR)", "soft_median", 1.0),
    "best": ("Meilleure cote disponible", "soft_max", 1.0),
}


def load_preds(src: str) -> pd.DataFrame:
    """Prédictions walk-forward avec l'éligibilité de prod."""
    from nhl.config.settings import cfg
    from nhl.scripts.simulate_roi import add_prod_price, apply_devig
    p = pd.read_parquet(os.path.join(REPORT_DIR, f"preds_{src}.parquet"))
    p["date"] = pd.to_datetime(p["date"])
    # Même prix et même no-vig Pinnacle que la prod
    p = apply_devig(add_prod_price(p), getattr(cfg.betting, "devig_method", "multiplicative"))
    parts = []
    for m in ("but", "ast"):
        sub = p[p["market"] == m].reset_index(drop=True)
        sub["eligible"] = p2_eligible(sub, m).to_numpy()
        parts.append(sub)
    return pd.concat(parts, ignore_index=True)


def scenario_nights(preds: pd.DataFrame, col: str, k: float, params: BetParams) -> list:
    """Paris de chaque soirée cotée : [cote, mise, gagné, p_conservatrice, marché(0=but,1=ast)]."""
    nights = []
    for date, day in preds.groupby("date", sort=True):
        d = day[day["eligible"] & day[col].notna()]
        cands = [{"market": r.market, "p_model": float(r.p_model), "p_novig": r.p_novig,
                  "cote": float(getattr(r, col) * k), "game_id": r.gameId, "won": int(r.won),
                  "soft": float(r.soft_median)} for r in d.itertuples(index=False)]
        bets = []
        for b in select_bets(cands, 100.0, params):
            # Hypothèse « aucun edge » : Pinnacle no-vig si dispo, sinon proba implicite de la médiane
            pn = b["p_novig"]
            p_cons = float(pn) if pn == pn and pn is not None else 1.0 / b["soft"]
            bets.append([round(b["cote"], 3), b["mise"], b["won"], round(p_cons, 4), 0 if b["market"] == "but" else 1])
        nights.append({"d": date.strftime("%Y-%m-%d"), "v": int(date < VAL_END), "b": bets})
    return nights


def summary(nights: list) -> dict:
    """Statistiques réelles d'un scénario (toute la période + par marché)."""
    rows = [(n["v"], *b) for n in nights for b in n["b"]]
    if not rows:
        return {"n": 0}
    df = pd.DataFrame(rows, columns=["val", "cote", "mise", "won", "pc", "mk"])
    df["profit"] = np.where(df["won"] == 1, df["mise"] * (df["cote"] - 1), -df["mise"])

    def stats(d: pd.DataFrame) -> dict:
        if d.empty:
            return {"n": 0}
        return {"n": int(len(d)), "avg_odds": round(float(d["cote"].mean()), 2),
                "win_rate": round(float(d["won"].mean()), 4), "avg_stake": round(float(d["mise"].mean()), 2),
                "stake": round(float(d["mise"].sum()), 1), "profit": round(float(d["profit"].sum()), 1),
                "roi": round(float(d["profit"].sum() / d["mise"].sum()), 4),
                "roi_pinnacle": round(float((d["pc"] * d["cote"] - 1).mean()), 4)}

    return {"all": stats(df), "but": stats(df[df.mk == 0]), "ast": stats(df[df.mk == 1]),
            "val": stats(df[df.val == 1]), "test": stats(df[df.val == 0]),
            "nights": len(nights), "active_nights": int(sum(1 for n in nights if n["b"]))}


def export(src: str = "p1b_ens") -> str:
    """Rejoue la stratégie actuelle, injecte les données dans simulateur.html ; renvoie la version."""
    preds = load_preds(src)
    params = BetParams.from_config()
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "version": current_version(),
        "source": f"walk-forward {src} + settings.toml [betting]",
        "period": [preds["date"].min().strftime("%Y-%m-%d"), preds["date"].max().strftime("%Y-%m-%d")],
        "params": {"kelly_fraction": params.kelly_fraction, "min_stake": params.min_stake,
                   "max_game": params.max_game_exposure, "max_day": params.max_daily_exposure},
        "scenarios": {},
    }
    for key, (label, col, k) in SCENARIOS.items():
        nights = scenario_nights(preds, col, k, params)
        s = summary(nights)
        data["scenarios"][key] = {"label": label, "nights": nights, "summary": s}
        al = s.get("all", {})
        print(f"[{key}] {label} : {al.get('n', 0)} paris sur {s.get('nights')} soirées | "
              f"cote {al.get('avg_odds')} | réussite {al.get('win_rate')} | ROI {al.get('roi')} | "
              f"EV Pinnacle {al.get('roi_pinnacle')}")

    blob = json.dumps(data, separators=(",", ":"))
    html = open(HTML, encoding="utf-8").read()
    if "/*DATA_START*/" not in html:
        raise RuntimeError("Marqueurs /*DATA_START*/ … /*DATA_END*/ absents de simulateur.html")
    html = re.sub(r"/\*DATA_START\*/.*?/\*DATA_END\*/", lambda _: f"/*DATA_START*/{blob}/*DATA_END*/",
                  html, flags=re.S)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Données injectées dans {HTML} ({len(blob) / 1024:.0f} Ko) — version {data['version']}")
    return data["version"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="p1b_ens")
    export(ap.parse_args().src)


if __name__ == "__main__":
    main()
