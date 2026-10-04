"""
scripts/search_config.py — Recherche de la meilleure configuration (moteur + stratégie de mise).

Protocole (fixé avant de lancer la recherche, cf. CONFIG_SEARCH_2026-10-04.md) :
- prédictions walk-forward existantes, prix de prod calibré, no-vig Pinnacle de Shin ;
- CHOIX sur la validation (saison 2023-24) uniquement ; contrôle (oct. 2024 → janv. 2025)
  affiché à part, jamais utilisé pour choisir ;
- scénarios retenus par des règles écrites à l'avance (SCENARIO_RULES) ;
- robustesse : voisins de grille, résultat de contrôle, p-value sous l'hypothèse « aucun edge »
  (résultats tirés avec la probabilité Pinnacle), corrigée du nombre de configurations testées.

Usage:
    python nhl/scripts/search_config.py            # moteurs + grille + scénarios
"""
import itertools
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "nhl")):
    if p not in sys.path:
        sys.path.insert(0, p)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nhl.core.betting import BetParams, select_bets  # noqa: E402
from nhl.scripts.simulate_roi import REPORT_DIR, VAL_END, bootstrap_ci, variance_metrics  # noqa: E402

GRID_CSV = os.path.join(REPORT_DIR, "config_search.csv")
SCENARIOS_JSON = os.path.join(REPORT_DIR, "config_scenarios.json")
ENGINES_CSV = os.path.join(REPORT_DIR, "config_engines.csv")
NIGHTS_PER_SEASON = 180
ENGINES = {
    "p1b_ens": "Ensemble LGBM + XGB + CatBoost (prod)",
    "p1b_lgbm": "LightGBM seul",
    "p1b_ens_monthly": "Ensemble, retrain mensuel",
    "x_feat_lgbm": "LightGBM, features V2",
    "x_tuned_lgbm": "LightGBM réglé (Optuna)",
    "q_p2_refit": "Ensemble, arbres ré-entraînés à 100 %",
    "avg_ens_v2": "Moyenne ensemble + LightGBM V2",
}
GRID = {
    "markets": [("but", "ast"), ("but",)],
    "ev": [0.04, 0.06, 0.08, 0.10],
    "w_shift": [-0.15, 0.0, 0.15],
    "cote_max_but": [8.0, 15.0],
    "max_per_game": [0, 1],
}
MIN_VAL_BETS = 150
MIN_PROFIT_CI_LO = -10.0


@dataclass
class Config:
    engine: str
    markets: tuple
    ev: float
    w_shift: float
    cote_max_but: float
    max_per_game: int

    def key(self) -> str:
        return (f"{self.engine}|{'+'.join(self.markets)}|ev{self.ev:.2f}|w{self.w_shift:+.2f}"
                f"|cmax{self.cote_max_but:g}|g{self.max_per_game}")

    def params(self) -> BetParams:
        base = BetParams.from_config()
        w = {m: float(np.clip(base.blend_w[m] + self.w_shift, 0.0, 1.0)) for m in ("but", "ast")}
        return BetParams.from_config(
            markets=self.markets, ev_low=self.ev, ev_mid=self.ev, ev_high=self.ev, blend_w=w,
            cote_max={"but": self.cote_max_but, "ast": base.cote_max["ast"]},
            max_bets_per_game=self.max_per_game)


def current_config() -> Config:
    """La config de prod (settings.toml) exprimée dans la grille."""
    b = BetParams.from_config()
    return Config("p1b_ens", tuple(b.markets), b.ev_mid, 0.0, b.cote_max["but"], b.max_bets_per_game)


# ─────────────────────────────────────────────────────────────────────────────
# Données
# ─────────────────────────────────────────────────────────────────────────────
def load_engine(name: str) -> pd.DataFrame:
    """Prédictions d'un moteur avec éligibilité, prix de prod et no-vig de prod."""
    from nhl.scripts.export_simulator_data import load_preds
    if name == "avg_ens_v2":
        a, b = load_engine("p1b_ens"), load_engine("x_feat_lgbm")
        b = b[["date", "playerId", "market", "p_model"]].rename(columns={"p_model": "p_b"})
        out = a.merge(b, on=["date", "playerId", "market"], how="inner")
        out["p_model"] = (out["p_model"] + out["p_b"]) / 2
        return out.drop(columns="p_b")
    return load_preds(name)


def day_candidates(df: pd.DataFrame) -> Dict[pd.Timestamp, List[dict]]:
    """Candidats de chaque soirée (lignes éligibles avec un prix de prod)."""
    d = df[df["eligible"] & df["prod_price"].notna()]
    out = {}
    for date, day in d.groupby("date", sort=True):
        out[date] = [{"market": x.market, "p_model": float(x.p_model),
                      "p_novig": (float(x.p_novig) if x.p_novig == x.p_novig else None),
                      "cote": float(x.prod_price), "game_id": x.gameId, "won": int(x.won), "date": date,
                      "soft": (float(x.soft_median) if x.soft_median == x.soft_median else None)}
                     for x in day.itertuples(index=False)]
    return out


def run_config(cands: Dict, cfg: Config) -> pd.DataFrame:
    """Paris d'une configuration sur toutes les soirées."""
    params, rows = cfg.params(), []
    for date, c in cands.items():
        rows += select_bets([x for x in c if x["market"] in cfg.markets], 100.0, params)
    b = pd.DataFrame(rows)
    if b.empty:
        return pd.DataFrame(columns=["date", "market", "mise", "cote", "won", "p_novig", "p_final", "game_id", "profit"])
    b["profit"] = np.where(b["won"] == 1, b["mise"] * (b["cote"] - 1), -b["mise"])
    return b


def period_metrics(b: pd.DataFrame, n_nights: int, n_games: int) -> Dict[str, float]:
    """Métriques d'une période (gain ramené à une saison de 180 soirées)."""
    if b.empty:
        return {"n": 0, "per_game": 0.0, "profit": 0.0, "profit_season": 0.0, "roi": np.nan,
                "profit_ci_lo": np.nan, "profit_ci_hi": np.nan, "max_dd": 0.0, "night_std": np.nan,
                "worst_night": np.nan, "sharpe_night": np.nan, "ev_pin": np.nan}
    lo, hi, plo, phi = bootstrap_ci(b)
    v = variance_metrics(b)
    pin = b[b["p_novig"].notna()]
    return {"n": int(len(b)), "per_game": len(b) / max(n_games, 1), "profit": float(b["profit"].sum()),
            "profit_season": float(b["profit"].sum()) * NIGHTS_PER_SEASON / max(n_nights, 1),
            "roi": float(b["profit"].sum() / b["mise"].sum()), "profit_ci_lo": plo, "profit_ci_hi": phi,
            "max_dd": v["max_dd"], "night_std": v["night_std"], "worst_night": v["worst_night"],
            "sharpe_night": v["sharpe_night"],
            "ev_pin": float((pin["p_novig"].astype(float) * pin["cote"] - 1).mean()) if len(pin) else np.nan}


def evaluate(cands: Dict, cfg: Config, counts: Dict) -> Dict:
    """Une configuration -> métriques validation et contrôle (une ligne du CSV)."""
    b = run_config(cands, cfg)
    row = {"key": cfg.key(), **{k: (("+".join(v)) if isinstance(v, tuple) else v) for k, v in asdict(cfg).items()}}
    for per, mask in (("val", b["date"] < VAL_END), ("ctl", b["date"] >= VAL_END)):
        m = period_metrics(b[mask] if len(b) else b, counts[per]["nights"], counts[per]["games"])
        row.update({f"{per}_{k}": v for k, v in m.items()})
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Moteurs
# ─────────────────────────────────────────────────────────────────────────────
def rank_engines(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Log-loss / AUC de chaque moteur sur le MÊME jeu de lignes (vs Pinnacle Shin)."""
    key = ["date", "playerId", "market"]
    common = None
    for f in frames.values():
        k = f[f["eligible"] & f["p_novig"].notna()][key]
        common = k if common is None else common.merge(k, on=key)
    rows = []
    for name, f in frames.items():
        d = f.merge(common, on=key)
        for mk in ("but", "ast"):
            for per, mask in (("val", d["date"] < VAL_END), ("ctl", d["date"] >= VAL_END)):
                s = d[mask & (d["market"] == mk)]
                rows.append({"engine": name, "market": mk, "period": per, "n": len(s),
                             "ll_model": log_loss(s["won"], s["p_model"].clip(1e-4, 1 - 1e-4)),
                             "ll_pinnacle": log_loss(s["won"], s["p_novig"].clip(1e-4, 1 - 1e-4)),
                             "auc_model": roc_auc_score(s["won"], s["p_model"])})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Sélection des scénarios (règles fixées avant la recherche)
# ─────────────────────────────────────────────────────────────────────────────
SCENARIO_RULES = {
    "prudent": ("Prudent", "meilleur ratio gain / écart-type par soirée, drawdown ≤ 15 U",
                lambda g: g[g.val_max_dd <= 15], "val_sharpe_night"),
    "equilibre": ("Équilibré", "meilleur gain par saison, drawdown ≤ 20 U et ROI ≥ 10 %",
                  lambda g: g[(g.val_max_dd <= 20) & (g.val_roi >= 0.10)], "val_profit_season"),
    "agressif": ("Agressif", "meilleur gain par saison, sans contrainte de drawdown",
                 lambda g: g, "val_profit_season"),
    "buteur": ("Buteur seul", "meilleur gain par saison parmi les configs buteur seul",
               lambda g: g[g.markets == "but"], "val_profit_season"),
}


# Variantes ajoutées à la main après lecture des résultats (affichées comme telles, pas
# issues d'une règle a priori) : voisin « 1 pari par match » de l'Équilibré, et buteur seul
# avec le moteur de prod (le scénario « Buteur seul » par règle utilise un moteur moyenné absent de la prod).
EXTRA_SCENARIOS = {
    "equilibre_1pm": ("Équilibré, 1 pari / match", "variante manuelle : Équilibré limité à 1 pari par match",
                      "p1b_ens|but+ast|ev0.08|w+0.15|cmax15|g1"),
    "buteur_prod": ("Buteur seul (moteur prod)", "variante manuelle : buteur seul avec le moteur de prod",
                    "p1b_ens|but|ev0.08|w+0.15|cmax8|g1"),
}


def admissible(grid: pd.DataFrame) -> pd.DataFrame:
    """Configs assez fournies et pas franchement perdantes en validation."""
    return grid[(grid.val_n >= MIN_VAL_BETS) & (grid.val_profit_ci_lo > MIN_PROFIT_CI_LO)]


def select_scenarios(grid: pd.DataFrame) -> Dict[str, str]:
    """{scénario: clé de config} selon SCENARIO_RULES (validation uniquement)."""
    ok = admissible(grid)
    out = {}
    for name, (_, _, filt, col) in SCENARIO_RULES.items():
        cand = filt(ok)
        if not cand.empty:
            out[name] = cand.sort_values(col, ascending=False).iloc[0]["key"]
    return out


def neighbors(grid: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    """Configs du même moteur qui ne diffèrent que d'un paramètre, d'un cran."""
    out = []
    for p, vals in GRID.items():
        col = "markets" if p == "markets" else p
        cur = row[col]
        vals_s = ["+".join(v) for v in vals] if p == "markets" else vals
        i = vals_s.index(cur)
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals_s):
                m = grid[(grid.engine == row.engine) & (grid[col] == vals_s[j])]
                for q in GRID:
                    if q != p:
                        m = m[m["markets" if q == "markets" else q] == row["markets" if q == "markets" else q]]
                out.append(m)
    return pd.concat(out) if out else grid.iloc[:0]


def null_pvalue(b: pd.DataFrame, n_sims: int = 5000, seed: int = 0) -> Optional[float]:
    """P(gain ≥ gain observé) si les résultats suivaient la proba Pinnacle (aucun edge).

    Paris sans Pinnacle : proba implicite de la cote (marge incluse), ce qui avantage
    l'hypothèse nulle (p-value prudente).
    """
    if b.empty:
        return None
    p0 = np.where(b["p_novig"].notna(), b["p_novig"].astype(float), 1.0 / b["cote"])
    rng = np.random.default_rng(seed)
    wins = rng.random((n_sims, len(b))) < p0
    gains = np.where(wins, (b["mise"] * (b["cote"] - 1)).to_numpy(), -b["mise"].to_numpy()).sum(1)
    return float((gains >= b["profit"].sum()).mean())


def main() -> None:
    print("Chargement des moteurs...")
    frames = {e: load_engine(e) for e in ENGINES}
    base = frames["p1b_ens"]
    priced = base[base["eligible"] & base["prod_price"].notna()]
    counts = {per: {"nights": int(priced[m]["date"].nunique()), "games": int(priced[m]["gameId"].nunique())}
              for per, m in (("val", priced["date"] < VAL_END), ("ctl", priced["date"] >= VAL_END))}
    print(f"Soirées / matchs cotés : {counts}")

    eng = rank_engines(frames)
    eng.to_csv(ENGINES_CSV, index=False)
    print(eng[eng.period == "val"].pivot(index="engine", columns="market", values="ll_model").round(5))

    cands = {e: day_candidates(f) for e, f in frames.items()}
    combos = [Config(e, *c) for e in ENGINES for c in itertools.product(*GRID.values())]
    cur = current_config()
    if cur.key() not in {c.key() for c in combos}:
        combos.append(cur)
    print(f"Évaluation de {len(combos)} configurations...")
    rows = []
    for i, c in enumerate(combos, 1):
        rows.append(evaluate(cands[c.engine], c, counts))
        if i % 100 == 0:
            print(f"  {i}/{len(combos)}")
    grid = pd.DataFrame(rows)
    grid.to_csv(GRID_CSV, index=False)

    chosen = {"actuelle": cur.key(), **select_scenarios(grid), **{k: v[2] for k, v in EXTRA_SCENARIOS.items()}}
    labels = {**{k: (v[0], v[1]) for k, v in SCENARIO_RULES.items()}, **{k: (v[0], v[1]) for k, v in EXTRA_SCENARIOS.items()},
              "actuelle": ("Actuelle (prod)", "config de settings.toml")}
    n_tested = len(grid)
    scen = {"protocol": {"selection": "validation 2023-24", "control": "oct. 2024 → janv. 2025",
                         "n_configs": n_tested, "counts": counts,
                         "rules": {k: v[1] for k, v in SCENARIO_RULES.items()}},
            "scenarios": {}}
    for name, key in chosen.items():
        row = grid[grid.key == key].iloc[0]
        nb = neighbors(grid, row)
        cfg = Config(row.engine, tuple(row.markets.split("+")), row.ev, row.w_shift, row.cote_max_but,
                     int(row.max_per_game))
        b = run_config(cands[cfg.engine], cfg)
        p_raw = null_pvalue(b[b["date"] < VAL_END])
        scen["scenarios"][name] = {
            "label": labels[name][0],
            "rule": labels[name][1],
            "manual": name in EXTRA_SCENARIOS,
            "config": {"engine": cfg.engine, "engine_label": ENGINES[cfg.engine], "markets": list(cfg.markets),
                       "ev_min": cfg.ev, "blend_w": cfg.params().blend_w, "cote_max_but": cfg.cote_max_but,
                       "max_bets_per_game": cfg.max_per_game},
            "val": {k[4:]: row[k] for k in row.index if k.startswith("val_")},
            "ctl": {k[4:]: row[k] for k in row.index if k.startswith("ctl_")},
            "robustness": {
                "neighbors": int(len(nb)),
                "neighbors_median_val_profit_season": float(nb["val_profit_season"].median()) if len(nb) else None,
                "rank_among_neighbors": int((nb["val_profit_season"] > row["val_profit_season"]).sum()) + 1,
                "p_value_no_edge": p_raw,
                "p_value_bonferroni": min(1.0, p_raw * n_tested) if p_raw is not None else None,
            },
        }
    with open(SCENARIOS_JSON, "w", encoding="utf-8") as f:
        json.dump(scen, f, indent=2, ensure_ascii=False, default=float)
    for name, s in scen["scenarios"].items():
        v, c, r = s["val"], s["ctl"], s["robustness"]
        print(f"{s['label']:14s} {s['config']['engine']:16s} {'+'.join(s['config']['markets']):7s} "
              f"EV≥{s['config']['ev_min']:.0%} w={s['config']['blend_w']} cmax={s['config']['cote_max_but']:g} "
              f"g{s['config']['max_bets_per_game']} | VAL {v['n']} paris, {v['profit_season']:+.1f} U/saison, "
              f"ROI {v['roi']:+.1%}, DD {v['max_dd']:.1f} | CTL {c['n']} paris, {c['profit_season']:+.1f} U/saison, "
              f"ROI {c['roi']:+.1%} | p={r['p_value_no_edge']}")
    print(f"-> {GRID_CSV}\n-> {SCENARIOS_JSON}")


if __name__ == "__main__":
    main()
