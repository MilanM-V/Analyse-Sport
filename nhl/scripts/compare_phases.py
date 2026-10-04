"""
scripts/compare_phases.py — Tableau comparatif des phases simulées (ROI, gain net, variance).

Lit nhl/reports/roi_by_phase.csv (écrit par simulate_roi.py) et imprime, en Markdown,
une ligne par phase et par période : paris, mise, gain net (IC 95 %), ROI (IC 95 %),
écart-type du P&L par soirée, pire soirée, max drawdown, edge Pinnacle, log-loss.

Usage:
    python nhl/scripts/compare_phases.py                       # phases q_* dans l'ordre du plan
    python nhl/scripts/compare_phases.py --phases q_ref,q_p0 --price prod --market ast
"""
import argparse
import os
import sys
from typing import List

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT_CSV = os.path.join(ROOT, "nhl", "reports", "roi_by_phase.csv")
DEFAULT_PHASES = ["q_ref", "q_prod", "q_p0", "q_p1_price", "q_p1_devig", "q_p1", "q_p2_refit", "q_p2", "q_p3"]
PERIOD_LABEL = {"val": "validation", "test": "contrôle", "all": "total"}


def _pct(v: float) -> str:
    return "—" if v is None or v != v else f"{v * 100:+.1f} %"


def _u(v: float) -> str:
    return "—" if v is None or v != v else f"{v:+.1f}"


def _f(v: float, d: int = 1) -> str:
    return "—" if v is None or v != v else f"{v:.{d}f}"


def table(phases: List[str], price: str = "exec", market: str = "total",
          periods: tuple = ("val", "test", "all")) -> str:
    """Tableau Markdown des phases demandées (celles absentes du CSV sont ignorées)."""
    r = pd.read_csv(REPORT_CSV)
    r = r[(r["retrain"] == "quarterly") & (r["price"] == price) & (r["market"] == market)]
    r = r.drop_duplicates(["phase", "period"], keep="last").set_index(["phase", "period"])
    lines = [f"Prix : `{price}` · marché : `{market}`\n",
             "| Phase | Période | Paris | Mise (U) | **Gain net (U)** | IC 95 % gain | **ROI** | IC 95 % ROI | "
             "σ / soirée (U) | Pire soirée | **Max drawdown (U)** | Edge Pinnacle |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for ph in phases:
        for per in periods:
            if (ph, per) not in r.index:
                continue
            x = r.loc[(ph, per)]
            g = lambda k: x[k] if k in x.index else np.nan  # noqa: E731
            lines.append(
                f"| {ph} | {PERIOD_LABEL[per]} | {int(x['n_bets'])} | {_f(x['stake'])} | **{_u(x['profit'])}** | "
                f"[{_u(g('profit_ci_lo'))} ; {_u(g('profit_ci_hi'))}] | **{_pct(x['roi'])}** | "
                f"[{_pct(x['roi_ci_lo'])} ; {_pct(x['roi_ci_hi'])}] | {_f(g('night_std'), 2)} | "
                f"{_u(g('worst_night'))} | **{_f(g('max_dd'))}** | {_pct(x['mkt_edge'])} |")
    return "\n".join(lines)


def model_quality(phases: List[str]) -> str:
    """Log-loss et AUC modèle vs Pinnacle par marché (période validation et contrôle)."""
    r = pd.read_csv(REPORT_CSV)
    r = r[(r["retrain"] == "quarterly") & (r["price"] == "exec") & r["market"].isin(["but", "ast"])]
    r = r.drop_duplicates(["phase", "market", "period"], keep="last")
    lines = ["| Phase | Marché | Période | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle |",
             "|---|---|---|---|---|---|---|"]
    for ph in phases:
        for _, x in r[r.phase == ph].sort_values(["market", "period"]).iterrows():
            if x["period"] == "all":
                continue
            lines.append(f"| {ph} | {x['market']} | {PERIOD_LABEL[x['period']]} | {_f(x['ll_model'], 4)} | "
                         f"{_f(x['ll_pinnacle'], 4)} | {_f(x['auc_model'], 3)} | {_f(x['auc_pinnacle'], 3)} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phases", default=",".join(DEFAULT_PHASES))
    ap.add_argument("--price", default="exec")
    ap.add_argument("--market", default="total")
    ap.add_argument("--quality", action="store_true", help="ajoute la qualité du modèle vs Pinnacle")
    a = ap.parse_args()
    phases = [p.strip() for p in a.phases.split(",") if p.strip()]
    print(table(phases, a.price, a.market))
    if a.quality:
        print()
        print(model_quality(phases))


if __name__ == "__main__":
    main()
