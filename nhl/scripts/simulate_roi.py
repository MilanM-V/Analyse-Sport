"""
scripts/simulate_roi.py — Harnais unique de simulation du ROI (walk-forward).

Mesure, pour une "phase" du projet, le ROI qu'aurait obtenu le bot sur toutes
les dates où l'on dispose de cotes historiques réelles (oct. 2023 -> janv. 2025).

Principes :
- Walk-forward strict : le modèle est ré-entraîné à chaque date de RETRAIN_DATES
  sur les seules données antérieures, puis prédit les matchs jusqu'au retrain suivant.
- Les règles de sélection / mise sont celles du CODE DE PROD de la phase
  (evaluate_player_markets, is_cote_valid, apply_kelly_to_picks...), pas une copie.
- Cote d'exécution = médiane des soft books (hors Pinnacle) x 0.94 (proxy Winamax).
  Sensibilités : médiane brute, meilleure cote.
- Edge marché = moyenne(p_novig_Pinnacle * cote_exec - 1) sur les paris choisis :
  estimateur de l'EV réelle à faible variance (équivalent CLV).
- RÈGLE FIGÉE (audit 2026-10-04) : la période oct. 2024 → janv. 2025 (« test ») a déjà servi
  à adopter des pistes. Elle n'est plus qu'un CONTRÔLE : aucune décision ne se prend dessus.
  Les décisions se prennent sur la validation 2023-24 ; le vrai test est le paper trading.

Usage:
    python nhl/scripts/simulate_roi.py --phase baseline
    python nhl/scripts/simulate_roi.py --phase p0 --retrain monthly
"""
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NHL_DIR = os.path.join(ROOT, "nhl")
ODDS_WIDE = os.path.join(NHL_DIR, "data", "odds", "odds_wide.parquet")
GAMELOG_MP = os.path.join(NHL_DIR, "data", "gamelogs", "mp_gamelogs.parquet")
REPORT_DIR = os.path.join(NHL_DIR, "reports")
REPORT_CSV = os.path.join(REPORT_DIR, "roi_by_phase.csv")
REPORT_MD = os.path.join(REPORT_DIR, "roi_by_phase.md")

from nhl.sim.version import EXEC_HAIRCUT  # noqa: E402  marge Winamax / ARJEL vs médiane US
VAL_END = pd.Timestamp("2024-07-01")  # validation = saison 2023-24, test = 2024-25
RETRAIN = {
    "quarterly": ["2023-10-01", "2024-01-01", "2024-04-01", "2024-10-01", "2025-01-01"],
    "monthly": [f"{y}-{m:02d}-01" for y, m in
                [(2023, 10), (2023, 11), (2023, 12), (2024, 1), (2024, 2), (2024, 3), (2024, 4),
                 (2024, 10), (2024, 11), (2024, 12), (2025, 1)]],
}
PRICE_VARIANTS = {"exec": None, "soft_median": "soft_median", "soft_max": "soft_max", "prod": "prod_price"}
# La règle de prix est celle de la prod (shared.odds_api.apply_proxy) : médiane US × décote du
# marché si des books US cotent, sinon Pinnacle × pin_haircut. 5 min avant le match, ~60 % des
# passes ont une cote US (calibration Winamax du 2026-10-04) : on ne force plus Pinnacle.
AST_PINNACLE_ONLY = False


# ─────────────────────────────────────────────────────────────────────────────
# Spécification d'une phase
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PhaseSpec:
    """Tout ce qui varie d'une phase à l'autre.

    Attributes:
        name: identifiant de la phase.
        load: () -> DataFrame avec au minimum date, playerId, gameId, target_but,
              target_ast et les features.
        features: {'but': [...], 'ast': [...]}.
        model_factory: (market) -> estimateur sklearn-like (fit / predict_proba).
        train_mask: (df, market) -> masque booléen des lignes d'entraînement.
        eligible: (df, market) -> masque booléen des joueurs évalués par le bot.
        select_and_stake: (day_df) -> DataFrame des paris (colonnes market, mise, cote...).
        notes: texte libre affiché dans le rapport.
    """
    name: str
    load: Callable[[], pd.DataFrame]
    features: Dict[str, List[str]]
    model_factory: Callable[[str], object]
    train_mask: Callable[[pd.DataFrame, str], pd.Series]
    eligible: Callable[[pd.DataFrame, str], pd.Series]
    select_and_stake: Callable[[pd.DataFrame], pd.DataFrame]
    notes: str = ""
    extra: Dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires communs
# ─────────────────────────────────────────────────────────────────────────────
def season_to_date_stats(gl: pd.DataFrame) -> pd.DataFrame:
    """Stats "vues par le bot avant le match" (saison en cours + L10), strictement décalées.

    Reproduit ce que contiennent 'Player Season Totals.csv' et 'last 10.csv' au moment
    du scan : GP, G/GP, A/GP de la saison, TOI moyen L10, position.
    """
    gl = gl.sort_values(["playerId", "gameDate"]).copy()
    gl["a"] = gl["a1"] + gl["a2"]
    g = gl.groupby(["playerId", "season"])
    gl["std_gp"] = g.cumcount()
    gl["std_g"] = g["g"].cumsum() - gl["g"]
    gl["std_a"] = g["a"].cumsum() - gl["a"]
    gl["G_GP"] = np.where(gl["std_gp"] > 0, gl["std_g"] / gl["std_gp"].clip(lower=1), 0.0)
    gl["A_GP"] = np.where(gl["std_gp"] > 0, gl["std_a"] / gl["std_gp"].clip(lower=1), 0.0)
    gl["ATOI_L10"] = (gl.groupby("playerId")["toi"]
                        .transform(lambda s: s.shift(1).rolling(10, min_periods=1).mean())
                        .fillna(0.0))
    return gl[["playerId", "gameId", "std_gp", "G_GP", "A_GP", "ATOI_L10", "position"]]


def load_odds() -> pd.DataFrame:
    """Cotes rattachées (une ligne par date, playerId, marché)."""
    o = pd.read_parquet(ODDS_WIDE)
    o["date"] = pd.to_datetime(o["date"])
    o["exec_price"] = o["soft_median"] * EXEC_HAIRCUT
    return o


def add_prod_price(preds: pd.DataFrame) -> pd.DataFrame:
    """Prix d'exécution tel que la PROD le calcule aujourd'hui (shared.odds_api.apply_proxy).

    Médiane soft × exec_haircut, à défaut cote « Oui » Pinnacle × pin_haircut. Pour les
    passes, aucun book soft ne cote en live : seul le repli Pinnacle s'applique.
    Ajoute `pin_yes` depuis odds_wide.parquet si les prédictions ne l'ont pas.
    """
    from nhl.sim.version import EXEC_HAIRCUT_AST, PIN_HAIRCUT
    out = preds.copy()
    if "pin_yes" not in out:
        o = pd.read_parquet(ODDS_WIDE, columns=["date", "playerId", "market", "pin_yes"])
        o["date"] = pd.to_datetime(o["date"])
        out = out.merge(o, on=["date", "playerId", "market"], how="left")
    soft = out["soft_median"] * np.where(out["market"] == "ast", EXEC_HAIRCUT_AST, EXEC_HAIRCUT)
    pin = out["pin_yes"] * PIN_HAIRCUT
    price = soft.where(soft.notna(), pin)
    if AST_PINNACLE_ONLY:
        price = price.where(out["market"] != "ast", pin)
    out["prod_price"] = price
    return out


def apply_devig(preds: pd.DataFrame, method: str) -> pd.DataFrame:
    """Recalcule `p_novig` avec la méthode de dévig donnée (shared.devig), depuis pin_yes / pin_no."""
    from shared.devig import devig_yes
    out = preds.copy()
    if "pin_no" not in out:
        o = pd.read_parquet(ODDS_WIDE, columns=["date", "playerId", "market", "pin_no"])
        o["date"] = pd.to_datetime(o["date"])
        out = out.merge(o, on=["date", "playerId", "market"], how="left")
    out["p_novig"] = devig_yes(out["pin_yes"].to_numpy(), out["pin_no"].to_numpy(), method)
    return out


def bootstrap_roi(bets: pd.DataFrame, n: int = 2000, seed: int = 0) -> tuple:
    """IC 95 % du ROI par bootstrap sur les JOURNÉES (paris d'un même jour corrélés)."""
    return bootstrap_ci(bets, n, seed)[:2]


def bootstrap_ci(bets: pd.DataFrame, n: int = 2000, seed: int = 0) -> tuple:
    """IC 95 % du ROI puis du gain net, par bootstrap sur les soirées.

    Returns:
        (roi_lo, roi_hi, profit_lo, profit_hi) ; NaN si aucun pari.
    """
    if bets.empty:
        return (np.nan, np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    daily = bets.groupby("date").agg(p=("profit", "sum"), s=("mise", "sum"))
    p, s = daily["p"].to_numpy(), daily["s"].to_numpy()
    idx = rng.integers(0, len(daily), size=(n, len(daily)))
    profits = p[idx].sum(1)
    rois = profits / np.maximum(s[idx].sum(1), 1e-9)
    return (float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5)),
            float(np.percentile(profits, 2.5)), float(np.percentile(profits, 97.5)))


def variance_metrics(bets: pd.DataFrame) -> Dict[str, float]:
    """Variance du P&L : écart-type et pire soirée, max drawdown (U), ratio moyenne / écart-type.

    Calculé sur les soirées avec au moins un pari, dans l'ordre chronologique.
    """
    if bets.empty:
        return {"night_std": np.nan, "worst_night": np.nan, "max_dd": np.nan, "sharpe_night": np.nan, "n_nights": 0}
    daily = bets.groupby("date")["profit"].sum().sort_index()
    cum = daily.cumsum()
    dd = (cum.cummax().clip(lower=0) - cum).max()
    std = float(daily.std(ddof=1)) if len(daily) > 1 else np.nan
    return {"night_std": std, "worst_night": float(daily.min()), "max_dd": float(dd),
            "sharpe_night": float(daily.mean() / std) if std and std == std else np.nan,
            "n_nights": int(len(daily))}


# ─────────────────────────────────────────────────────────────────────────────
# Moteur walk-forward
# ─────────────────────────────────────────────────────────────────────────────
def walk_forward_predictions(spec: PhaseSpec, df: pd.DataFrame, odds: pd.DataFrame,
                             retrain_dates: List[str]) -> pd.DataFrame:
    """Prédit, sans regarder le futur, toutes les lignes (joueur, match) qui ont une cote.

    Returns:
        DataFrame (une ligne par date, playerId, marché) avec la proba du modèle,
        la cote, le résultat et l'éligibilité.
    """
    out = []
    dates = [pd.Timestamp(d) for d in retrain_dates] + [pd.Timestamp("2100-01-01")]
    for market in ("but", "ast"):
        feats = spec.features[market]
        target = f"target_{market}"
        mo = odds[odds.market == market]
        test = df.merge(mo, on=["date", "playerId"], how="inner", suffixes=("", "_odds"))
        test = test[test["date"] >= dates[0]]
        test["eligible"] = spec.eligible(test, market).to_numpy()
        for i, start in enumerate(dates[:-1]):
            end = dates[i + 1]
            chunk = test[(test.date >= start) & (test.date < end)]
            if chunk.empty:
                continue
            tr = df[(df.date < start) & spec.train_mask(df, market)]
            t0 = time.time()
            model = spec.model_factory(market)
            model.fit(tr[feats].to_numpy(dtype=float), tr[target].to_numpy())
            p = model.predict_proba(chunk[feats].to_numpy(dtype=float))[:, 1]
            c = chunk.copy()
            c["p_model"] = p
            c["market"] = market
            out.append(c)
            print(f"  [{market}] retrain {start.date()} : train={len(tr):,} lignes, "
                  f"test={len(c):,} ({time.time() - t0:.0f}s)")
    res = pd.concat(out, ignore_index=True)
    res["won"] = np.where(res["market"] == "but", res["target_but"], res["target_ast"]).astype(int)
    return res


def run_betting(spec: PhaseSpec, preds: pd.DataFrame, price_col: Optional[str]) -> pd.DataFrame:
    """Rejoue la sélection + mise jour par jour avec un prix d'exécution donné."""
    p = preds[preds["eligible"]].copy()
    if price_col:
        p["exec_price"] = p[price_col]
    p = p[p["exec_price"].notna() & (p["exec_price"] > 1.01)]
    bets = []
    for _, day in p.groupby("date", sort=True):
        b = spec.select_and_stake(day)
        if b is not None and not b.empty:
            bets.append(b)
    if not bets:
        return pd.DataFrame(columns=["date", "market", "mise", "cote", "won", "profit"])
    bets = pd.concat(bets, ignore_index=True)
    bets = bets[bets["mise"] > 0].copy()
    bets["profit"] = np.where(bets["won"] == 1, bets["mise"] * (bets["cote"] - 1.0), -bets["mise"])
    return bets


def summarize(bets: pd.DataFrame, preds: pd.DataFrame) -> Dict[str, Dict]:
    """Métriques par marché et par période (validation / test / total)."""
    out = {}
    periods = {"val": lambda d: d < VAL_END, "test": lambda d: d >= VAL_END, "all": lambda d: d == d}
    for market in ("but", "ast", "total"):
        for per, f in periods.items():
            b = bets[f(bets["date"])]
            pr = preds[f(preds["date"])]
            if market != "total":
                b = b[b["market"] == market]
                pr = pr[pr["market"] == market]
            stake = b["mise"].sum()
            r = {
                "n_bets": int(len(b)), "stake": float(stake), "profit": float(b["profit"].sum()),
                "roi": float(b["profit"].sum() / stake) if stake else np.nan,
                "hit_rate": float(b["won"].mean()) if len(b) else np.nan,
                "avg_odds": float(b["cote"].mean()) if len(b) else np.nan,
            }
            r["roi_ci_lo"], r["roi_ci_hi"], r["profit_ci_lo"], r["profit_ci_hi"] = bootstrap_ci(b)
            r.update(variance_metrics(b))
            pinn = b.dropna(subset=["p_novig"])
            r["mkt_edge"] = float((pinn["p_novig"] * pinn["cote"] - 1).mean()) if len(pinn) else np.nan
            r["mkt_edge_cov"] = float(len(pinn) / len(b)) if len(b) else np.nan
            # Qualité du modèle vs Pinnacle, sur toutes les lignes cotées éligibles
            q = pr[pr["eligible"]].dropna(subset=["p_novig"])
            if market != "total" and len(q) > 200 and q["won"].nunique() > 1:
                r["ll_model"] = float(log_loss(q["won"], q["p_model"].clip(1e-4, 1 - 1e-4)))
                r["ll_pinnacle"] = float(log_loss(q["won"], q["p_novig"].clip(1e-4, 1 - 1e-4)))
                r["auc_model"] = float(roc_auc_score(q["won"], q["p_model"]))
                r["auc_pinnacle"] = float(roc_auc_score(q["won"], q["p_novig"]))
                band = q[(q["p_model"] >= 0.08) & (q["p_model"] <= 0.35)]
                if len(band) > 100:
                    bins = pd.cut(band["p_model"], 10)
                    g = band.groupby(bins, observed=True).agg(p=("p_model", "mean"), y=("won", "mean"), n=("won", "size"))
                    r["ece_band"] = float((g["n"] * (g["p"] - g["y"]).abs()).sum() / g["n"].sum())
            out[f"{market}_{per}"] = r
    return out


def odds_buckets(bets: pd.DataFrame) -> pd.DataFrame:
    """ROI par tranche de cote."""
    if bets.empty:
        return pd.DataFrame()
    b = bets.copy()
    b["bucket"] = pd.cut(b["cote"], [1, 2, 2.5, 3.5, 4.5, 6, 10, 100])
    return (b.groupby(["market", "bucket"], observed=True)
              .agg(n=("profit", "size"), mise=("mise", "sum"), profit=("profit", "sum"))
              .assign(roi=lambda x: x.profit / x.mise).round(3).reset_index())


def write_report(spec: PhaseSpec, results: Dict[str, Dict], buckets: pd.DataFrame,
                 retrain: str, elapsed: float) -> None:
    """Ajoute la phase au CSV cumulatif et au rapport Markdown."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for variant, res in results.items():
        for key, r in res.items():
            market, per = key.rsplit("_", 1)
            rows.append(dict(timestamp=stamp, phase=spec.name, retrain=retrain, price=variant,
                             market=market, period=per, **r))
    df = pd.DataFrame(rows)
    if os.path.exists(REPORT_CSV):
        old = pd.read_csv(REPORT_CSV)
        old = old[~((old.phase == spec.name) & (old.retrain == retrain))]
        df = pd.concat([old, df], ignore_index=True)
    df.to_csv(REPORT_CSV, index=False)

    ex = results["exec"]

    def fmt(r: Dict, k: str, pct: bool = True) -> str:
        v = r.get(k, np.nan)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        return f"{v * 100:+.1f}%" if pct else f"{v:.4f}"

    lines = [f"\n## Phase `{spec.name}` — {stamp} (retrain {retrain}, {elapsed / 60:.0f} min)\n"]
    if spec.notes:
        lines.append(f"{spec.notes}\n")
    lines.append("Cote d'exécution : médiane soft books × 0,94. IC 95 % bootstrap par journée.\n")
    lines.append("| Marché | Période | Paris | Mise (U) | Profit (U) | **ROI** | IC 95 % | Edge marché (Pinnacle) | Couv. Pinnacle | LL modèle | LL Pinnacle | AUC modèle | AUC Pinnacle | ECE bande |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for market in ("but", "ast", "total"):
        for per in ("val", "test", "all"):
            r = ex[f"{market}_{per}"]
            ci = (f"[{r['roi_ci_lo'] * 100:+.0f} ; {r['roi_ci_hi'] * 100:+.0f}]"
                  if not np.isnan(r.get("roi_ci_lo", np.nan)) else "—")
            lines.append(
                f"| {market} | {per} | {r['n_bets']} | {r['stake']:.1f} | {r['profit']:+.1f} | **{fmt(r, 'roi')}** | {ci} | "
                f"{fmt(r, 'mkt_edge')} | {fmt(r, 'mkt_edge_cov')} | {fmt(r, 'll_model', False)} | {fmt(r, 'll_pinnacle', False)} | "
                f"{fmt(r, 'auc_model', False)} | {fmt(r, 'auc_pinnacle', False)} | {fmt(r, 'ece_band', False)} |")
    lines.append("\nSensibilité au prix d'exécution (ROI total, toute la période) : " + ", ".join(
        f"{v} = {fmt(results[v]['total_all'], 'roi')} ({results[v]['total_all']['n_bets']} paris)" for v in results))
    if not buckets.empty:
        lines.append("\nROI par tranche de cote (exec) :\n")
        lines.append("| Marché | Cote | Paris | Mise | Profit | ROI |\n|---|---|---|---|---|---|")
        for r in buckets.itertuples(index=False):
            lines.append(f"| {r.market} | {r.bucket} | {r.n} | {r.mise:.1f} | {r.profit:+.1f} | {r.roi * 100:+.1f}% |")
    header = "# ROI simulé par phase\n\nGénéré par `nhl/scripts/simulate_roi.py`. Une section par exécution.\n"
    prev = open(REPORT_MD, encoding="utf-8").read() if os.path.exists(REPORT_MD) else header
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(prev.rstrip() + "\n" + "\n".join(lines) + "\n")


def run(spec: PhaseSpec, retrain: str = "quarterly") -> Dict:
    """Exécute la simulation complète d'une phase et écrit le rapport."""
    t0 = time.time()
    print(f"=== SIMULATION ROI — phase {spec.name} (retrain {retrain}) ===")
    df = spec.load()
    df["date"] = pd.to_datetime(df["date"])
    odds = load_odds()
    src = spec.extra.get("reuse_preds")
    if src:
        # Même modèle que la phase `src` : on réutilise ses prédictions et on ne
        # recalcule que l'éligibilité (règles de la phase courante).
        preds = pd.read_parquet(os.path.join(REPORT_DIR, f"preds_{src}.parquet"))
        print(f"  prédictions réutilisées depuis la phase {src} ({len(preds):,} lignes)")
        parts = []
        for market in ("but", "ast"):
            sub = preds[preds["market"] == market].reset_index(drop=True)
            key = sub[["date", "playerId"]].merge(df, on=["date", "playerId"], how="left")
            sub["eligible"] = spec.eligible(key, market).to_numpy()
            parts.append(sub)
        preds = pd.concat(parts, ignore_index=True)
    else:
        preds = walk_forward_predictions(spec, df, odds, RETRAIN[retrain])
    tag = spec.name if retrain == "quarterly" else f"{spec.name}_{retrain}"
    preds_path = os.path.join(REPORT_DIR, f"preds_{tag}.parquet")
    os.makedirs(REPORT_DIR, exist_ok=True)
    preds.drop(columns=[c for c in preds.columns if c not in (
        "date", "playerId", "gameId", "market", "p_model", "won", "eligible", "exec_price",
        "soft_median", "soft_max", "p_novig", "pin_yes", "position", "team", "is_home", "ATOI_L10", "G_GP", "A_GP", "std_gp",
        "pos_bot")], errors="ignore").to_parquet(preds_path, index=False)
    preds = add_prod_price(preds)
    if spec.extra.get("devig"):
        preds = apply_devig(preds, spec.extra["devig"])
    if spec.extra.get("exec_is_prod"):
        preds["exec_price"] = preds["prod_price"]  # la phase simule le prix réel de la prod
    results, buckets = {}, pd.DataFrame()
    for variant, col in PRICE_VARIANTS.items():
        bets = run_betting(spec, preds, col)
        results[variant] = summarize(bets, preds)
        if variant == "exec":
            buckets = odds_buckets(bets)
            bets.to_parquet(os.path.join(REPORT_DIR, f"bets_{tag}.parquet"), index=False)
    elapsed = time.time() - t0
    write_report(spec, results, buckets, retrain, elapsed)
    tot = results["exec"]
    for k in ("but_all", "ast_all", "total_all", "total_val", "total_test"):
        r = tot[k]
        print(f"  {k:10s} paris={r['n_bets']:5d}  ROI={r['roi'] * 100 if r['n_bets'] else float('nan'):+6.1f}%  "
              f"edge_mkt={r['mkt_edge'] * 100 if not np.isnan(r['mkt_edge']) else float('nan'):+6.1f}%")
    print(f"  terminé en {elapsed / 60:.1f} min -> {REPORT_MD}")
    return results


def main() -> None:
    from nhl.sim.phases import PHASES  # import tardif : les phases importent le code de prod
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    ap.add_argument("--retrain", default="quarterly", choices=sorted(RETRAIN))
    args = ap.parse_args()
    run(PHASES[args.phase](), args.retrain)


if __name__ == "__main__":
    main()
