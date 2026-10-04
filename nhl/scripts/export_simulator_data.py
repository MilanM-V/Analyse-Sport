"""
scripts/export_simulator_data.py — Injecte les données réelles du moteur dans simulateur.html.

Source : les CONFIGURATIONS de nhl/reports/config_scenarios.json (search_config.py) : chacune
est un moteur (prédictions walk-forward) + une stratégie (select_bets), toutes rejouées au prix
de prod calibré (médiane US × exec_haircut ; passes = Pinnacle × pin_haircut) avec le no-vig
de prod. La config « actuelle » correspond à settings.toml.

Les paris sont regroupés par SOIRÉE (toutes les soirées cotées, y compris celles sans
pari) : le simulateur rééchantillonne des soirées entières, ce qui conserve la
corrélation des paris d'un même soir et le vrai rythme de picks.

Le JSON est écrit entre les marqueurs /*DATA_START*/ et /*DATA_END*/ de simulateur.html.

Usage:
    python nhl/scripts/search_config.py          # (re)calcule les configurations
    python nhl/scripts/export_simulator_data.py
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

from nhl.core.betting import BetParams  # noqa: E402
from nhl.scripts.simulate_roi import REPORT_DIR, VAL_END  # noqa: E402
from nhl.sim.phases import p2_eligible  # noqa: E402
from nhl.sim.version import EXEC_HAIRCUT, PIN_HAIRCUT, current_version  # noqa: E402

HTML = os.path.join(ROOT, "simulateur.html")
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


def config_nights(scenario: dict, all_dates: list) -> list:
    """Paris de chaque soirée cotée pour une configuration : [cote, mise, gagné, p_cons, marché]."""
    from nhl.scripts.search_config import W_BASE, Config, day_candidates, load_engine, run_config
    c = scenario["config"]
    cfg = Config(c["engine"], tuple(c["markets"]), c["ev_min"], round(c["blend_w"]["but"] - W_BASE["but"], 2),
                 c["cote_max_but"], c["max_bets_per_game"])
    bets = run_config(day_candidates(load_engine(cfg.engine)), cfg)
    by_day = {d: g for d, g in bets.groupby("date")} if len(bets) else {}
    nights = []
    for date in all_dates:
        rows = []
        for b in (by_day[date].itertuples(index=False) if date in by_day else []):
            # Hypothèse « aucun edge » : Pinnacle no-vig si dispo, sinon proba implicite de la médiane US
            pn = b.p_novig
            p_cons = float(pn) if pn is not None and pn == pn else (1.0 / b.soft if b.soft else 1.0 / b.cote)
            rows.append([round(b.cote, 3), b.mise, int(b.won), round(p_cons, 4), 0 if b.market == "but" else 1])
        nights.append({"d": date.strftime("%Y-%m-%d"), "v": int(date < VAL_END), "b": rows})
    return nights


def export() -> str:
    """Rejoue chaque configuration, injecte les données dans simulateur.html ; renvoie la version."""
    from nhl.scripts.search_config import SCENARIOS_JSON, load_engine
    with open(SCENARIOS_JSON, encoding="utf-8") as f:
        scen = json.load(f)
    base = load_engine("p1b_ens")
    priced = base[base["eligible"] & base["prod_price"].notna()]
    all_dates = sorted(priced["date"].unique())
    params = BetParams.from_config()
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "version": current_version(),
        "source": "configurations de nhl/reports/config_scenarios.json, prix de prod calibré",
        "price": f"médiane US × {EXEC_HAIRCUT:.3f} ; passes = Pinnacle × {PIN_HAIRCUT:.2f}".replace(".", ","),
        "period": [pd.Timestamp(all_dates[0]).strftime("%Y-%m-%d"), pd.Timestamp(all_dates[-1]).strftime("%Y-%m-%d")],
        "params": {"kelly_fraction": params.kelly_fraction, "min_stake": params.min_stake,
                   "max_game": params.max_game_exposure, "max_day": params.max_daily_exposure},
        "protocol": scen["protocol"],
        "scenarios": {},
    }
    for key, sc in scen["scenarios"].items():
        nights = config_nights(sc, [pd.Timestamp(d) for d in all_dates])
        s = summary(nights)
        data["scenarios"][key] = {"label": sc["label"], "rule": sc["rule"], "manual": sc.get("manual", False),
                                  "config": sc["config"], "val": sc["val"], "ctl": sc["ctl"],
                                  "robustness": sc["robustness"], "nights": nights, "summary": s}
        al = s.get("all", {})
        print(f"[{key}] {sc['label']} : {al.get('n', 0)} paris sur {s.get('nights')} soirées | "
              f"ROI {al.get('roi')} | EV Pinnacle {al.get('roi_pinnacle')}")

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
    argparse.ArgumentParser(description=__doc__).parse_args()
    export()


if __name__ == "__main__":
    main()
