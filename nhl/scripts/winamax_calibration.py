"""
scripts/winamax_calibration.py — Calibre le prix Winamax réel contre The Odds API (books US, Pinnacle).

Entrées :
- nhl/data/odds/winamax_snapshots.parquet (parse_winamax_pages.py) : dernières cotes Winamax
  avant le coup d'envoi ;
- The Odds API historique, instantané 5 min avant chaque match (buteur + passes, us + eu),
  mis en cache dans nhl/data/odds/winamax_calib_odds.db (aucun re-téléchargement).

Analyses : décote réelle Winamax (vs médiane US et vs Pinnacle), EV des cotes Winamax contre
la cote juste Pinnacle (Shin), modèle aux prix Winamax réels, volume simulé 2023-25 avec la
décote mesurée. Sortie : tableaux imprimés + nhl/reports/winamax_calibration.json.

Usage:
    python nhl/scripts/winamax_calibration.py --fetch --max-credits 800
    python nhl/scripts/winamax_calibration.py            # analyses seules (cache)
"""
import argparse
import json
import os
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(os.path.join(ROOT, ".env"))

from nhl.core.odds import nhl_team_key  # noqa: E402
from shared.devig import devig_yes  # noqa: E402
from shared.odds_api import SOFT_BOOKS, match_player  # noqa: E402

ODDS_DIR = os.path.join(ROOT, "nhl", "data", "odds")
SNAPSHOTS = os.path.join(ODDS_DIR, "winamax_snapshots.parquet")
CACHE_DB = os.path.join(ODDS_DIR, "winamax_calib_odds.db")
REPORT_JSON = os.path.join(ROOT, "nhl", "reports", "winamax_calibration.json")
API = "https://api.the-odds-api.com/v4/historical/sports/icehockey_nhl"
MARKETS = {"player_goal_scorer_anytime": "but", "player_assists": "ast"}
LEAD_MIN = 5  # instantané 5 min avant le coup d'envoi


# ─────────────────────────────────────────────────────────────────────────────
# Récupération (avec cache et plafond de crédits)
# ─────────────────────────────────────────────────────────────────────────────
class Budget:
    """Suit la consommation de crédits via les en-têtes The Odds API et impose un plafond."""

    def __init__(self, max_credits: int) -> None:
        self.max, self.used, self.remaining = max_credits, 0, None

    def charge(self, resp: requests.Response) -> None:
        last = resp.headers.get("x-requests-last")
        self.used += int(last) if last and last.isdigit() else 0
        self.remaining = resp.headers.get("x-requests-remaining", self.remaining)

    def can_spend(self, cost: int) -> bool:
        return self.used + cost <= self.max


def _cache_get(key: str) -> Optional[dict]:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, body TEXT)")
    row = conn.execute("SELECT body FROM cache WHERE key = ?", (key,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def _cache_put(key: str, body: dict) -> None:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, body TEXT)")
    conn.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)", (key, json.dumps(body)))
    conn.commit()
    conn.close()


def _get(url: str, params: dict, budget: Budget, cost: int) -> Optional[dict]:
    """GET historique avec contrôle du budget. Lève RuntimeError si le plafond serait dépassé."""
    if not budget.can_spend(cost):
        raise RuntimeError(f"Plafond de crédits atteint ({budget.used}/{budget.max}) : arrêt.")
    r = requests.get(url, params={"apiKey": os.getenv("api_odds"), **params}, timeout=30)
    budget.charge(r)
    if r.status_code in (404, 422):
        return {}
    r.raise_for_status()
    return r.json()


def fetch_reference_odds(snap: pd.DataFrame, max_credits: int) -> Dict[int, dict]:
    """Cotes US + Pinnacle 5 min avant chaque match des pages Winamax.

    Returns:
        {gameId: réponse /events/{id}/odds (champ data)} ; les réponses sont mises en cache.
    """
    budget = Budget(max_credits)
    key_fn = nhl_team_key()
    games = snap.drop_duplicates("gameId")[["gameId", "date", "home", "away", "start_utc"]]
    out: Dict[int, dict] = {}
    for date, day in games.groupby("date"):
        first = pd.Timestamp(day["start_utc"].min()) - pd.Timedelta(minutes=30)
        ev_key = f"EVENTS|{first.isoformat()}"
        events = _cache_get(ev_key)
        if events is None:
            events = _get(f"{API}/events", {"date": first.strftime("%Y-%m-%dT%H:%M:%SZ")}, budget, 1) or {}
            _cache_put(ev_key, events)
        evs = events.get("data", [])
        for g in day.itertuples(index=False):
            ev = next((e for e in evs if key_fn(e["home_team"]) == g.home and key_fn(e["away_team"]) == g.away), None)
            if ev is None:
                print(f"  ⚠️ event introuvable pour {g.home}-{g.away} ({date})")
                continue
            t = pd.Timestamp(g.start_utc) - pd.Timedelta(minutes=LEAD_MIN)
            k = f"ODDS|{ev['id']}|{t.isoformat()}"
            body = _cache_get(k)
            if body is None:
                body = _get(f"{API}/events/{ev['id']}/odds",
                            {"date": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "regions": "us,eu",
                             "markets": ",".join(MARKETS), "oddsFormat": "decimal"}, budget, 40) or {}
                _cache_put(k, body)
            out[int(g.gameId)] = body.get("data", {})
    print(f"Crédits consommés : {budget.used} (restants : {budget.remaining})")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Rapprochement
# ─────────────────────────────────────────────────────────────────────────────
def reference_table(raw: Dict[int, dict]) -> pd.DataFrame:
    """Une ligne par (match, marché, joueur API) : soft_median, n_soft, pin_yes, pin_no."""
    recs = []
    for gid, data in raw.items():
        for bm in data.get("bookmakers", []):
            for m in bm.get("markets", []):
                mk = MARKETS.get(m["key"])
                if not mk:
                    continue
                for o in m.get("outcomes", []):
                    if mk == "ast" and o.get("point") not in (None, 0.5):
                        continue
                    side = "yes" if str(o.get("name")).lower() in ("yes", "over") else "no"
                    recs.append({"gameId": gid, "market": mk, "api_player": o.get("description", ""),
                                 "book": bm["key"], "side": side, "price": float(o["price"])})
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    soft = (df[df.book.isin(SOFT_BOOKS) & (df.side == "yes")]
            .groupby(["gameId", "market", "api_player"])["price"].agg(soft_median="median", n_soft="count"))
    pin = (df[df.book == "pinnacle"].pivot_table(index=["gameId", "market", "api_player"], columns="side",
                                                 values="price", aggfunc="last")
           .rename(columns={"yes": "pin_yes", "no": "pin_no"}))
    return soft.join(pin, how="outer").reset_index()


def match_tables(snap: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Rattache chaque cote Winamax au joueur The Odds API du même match et marché."""
    rows = []
    for (gid, mk), w in snap[snap.market.isin(["but", "ast"])].groupby(["gameId", "market"]):
        r = ref[(ref.gameId == gid) & (ref.market == mk)]
        cands = list(r["api_player"])
        for x in w.itertuples(index=False):
            hit = match_player(x.player, cands) if cands else None
            rec = x._asdict()
            if hit is not None:
                rec.update(r[r.api_player == hit].iloc[0][["soft_median", "n_soft", "pin_yes", "pin_no"]].to_dict())
            rows.append(rec)
    out = pd.DataFrame(rows)
    out["p_shin"] = devig_yes(out["pin_yes"].to_numpy(float), out["pin_no"].to_numpy(float), "shin")
    return out


def attach_outcomes(df: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    """playerId + résultat (but / passe) depuis les logs de match API NHL ; absent = non aligné."""
    rows = []
    for gid, sub in df.groupby("gameId"):
        lg = logs[logs.gameId == gid]
        names = list(lg["name"])
        for x in sub.itertuples(index=False):
            hit = match_player(x.player, names)
            rec = x._asdict()
            if hit is not None:
                r = lg[lg.name == hit].iloc[0]
                rec.update(playerId=int(r.playerId), position=r.position,
                           won=int((r.g if x.market == "but" else r.a1 + r.a2) > 0))
            rows.append(rec)
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Analyses
# ─────────────────────────────────────────────────────────────────────────────
def cluster_ci(df: pd.DataFrame, col: str, n: int = 4000, seed: int = 0) -> Tuple[float, float, float]:
    """Médiane d'une colonne et IC 95 % par bootstrap sur les MATCHS (cotes d'un match corrélées)."""
    d = df.dropna(subset=[col])
    if d.empty:
        return (np.nan, np.nan, np.nan)
    groups = [g[col].to_numpy() for _, g in d.groupby("gameId")]
    rng = np.random.default_rng(seed)
    meds = [np.median(np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))]))
            for _ in range(n)]
    return float(np.median(d[col])), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5))


def model_predictions(df: pd.DataFrame, eng) -> pd.DataFrame:
    """p_model de chaque joueur, avec uniquement les données antérieures au jour du match."""
    preds = []
    for date, day in df.dropna(subset=["playerId"]).groupby("date"):
        games = [{"gameId": int(g), "home": h, "away": a}
                 for g, h, a in day[["gameId", "home", "away"]].drop_duplicates().itertuples(index=False)]
        logs = eng.logs[eng.logs.gameId.isin([g["gameId"] for g in games])]
        lineup = dict(zip(logs["name"], logs["team"]))
        res = eng.predict(games, lineup, date)
        for name, r in res.items():
            preds.append({"playerId": r["playerId"], "date": date, "p_but": r.get("but"), "p_ast": r.get("ast"),
                          "std_gp": r["features"].get("but", {}).get("std_gp")})
    p = pd.DataFrame(preds).drop_duplicates(["playerId", "date"])
    out = df.merge(p, on=["playerId", "date"], how="left")
    out["p_model"] = np.where(out.market == "but", out.p_but, out.p_ast)
    return out


def analyze(df: pd.DataFrame) -> Dict:
    """Décote, EV contre la cote juste, modèle aux prix Winamax réels (sur les lignes rapprochées)."""
    from sklearn.metrics import log_loss
    from nhl.core.betting import BetParams, select_bets
    res: Dict = {"n_games": int(df.gameId.nunique())}
    buckets = [1, 2, 3, 4.5, 7, 100]
    for mk, sub in df.groupby("market"):
        r = {"n": int(len(sub))}
        for col, lab in (("r_soft", "vs_soft"), ("r_pin", "vs_pin")):
            med, lo, hi = cluster_ci(sub, col)
            r[lab] = {"n": int(sub[col].notna().sum()), "median": med, "ci": [lo, hi],
                      "by_odds": {str(b): round(float(g[col].median()), 4) for b, g in
                                  sub.dropna(subset=[col]).groupby(pd.cut(sub["winamax"], buckets), observed=True)}}
        f = sub.dropna(subset=["ev_fair"])
        r["ev_fair"] = {"n": int(len(f)), "mean": float(f["ev_fair"].mean()), "share_pos": float((f["ev_fair"] > 0).mean()),
                        "share_4pct": float((f["ev_fair"] > 0.04).mean())}
        q = sub.dropna(subset=["won", "p_model", "p_shin"])
        if len(q) > 30 and q["won"].nunique() > 1:
            r["logloss"] = {"n": int(len(q)),
                            "model": float(log_loss(q["won"], q["p_model"].clip(1e-4, 1 - 1e-4))),
                            "pinnacle_shin": float(log_loss(q["won"], q["p_shin"].clip(1e-4, 1 - 1e-4))),
                            "winamax_implied": float(log_loss(q["won"], (1 / q["winamax"]).clip(1e-4, 1 - 1e-4))),
                            "rate": float(q["won"].mean())}
        res[mk] = r
    # Paris que la stratégie de prod aurait pris AU PRIX WINAMAX RÉEL. Filtres de prod appliqués
    # (buteur : attaquants seulement, le modèle n'est pas entraîné sur les défenseurs), sauf
    # « 10 matchs joués » (impossible en début de saison) : signalé dans le rapport.
    params = BetParams.from_config()
    bets = []
    elig = df.dropna(subset=["p_model", "won"])
    elig = elig[~((elig["market"] == "but") & (elig["position"] == "D"))]
    res["eligible_rows"] = elig.groupby("market").size().to_dict()
    for gid, day in elig.groupby("date"):
        cands = [{"market": x.market, "p_model": float(x.p_model),
                  "p_novig": (float(x.p_shin) if x.p_shin == x.p_shin else None), "cote": float(x.winamax),
                  "game_id": x.gameId, "won": int(x.won), "player": x.player, "date": x.date}
                 for x in day.itertuples(index=False)]
        bets += select_bets(cands, 100.0, params)
    b = pd.DataFrame(bets)
    if not b.empty:
        b["profit"] = np.where(b["won"] == 1, b["mise"] * (b["cote"] - 1), -b["mise"])
        pin = b.dropna(subset=["p_novig"])
        res["bets"] = {"n": int(len(b)), "by_market": b.groupby("market").size().to_dict(),
                       "stake": float(b["mise"].sum()), "profit": float(b["profit"].sum()),
                       "roi": float(b["profit"].sum() / b["mise"].sum()), "hit": float(b["won"].mean()),
                       "expected_profit_model": float((b["mise"] * (b["p_final"] * b["cote"] - 1)).sum()),
                       "ev_pinnacle": float((pin["p_novig"] * pin["cote"] - 1).mean()) if len(pin) else None,
                       "list": b[["date", "player", "market", "cote", "p_final", "ev", "mise", "won"]]
                       .round(3).to_dict("records")}
    else:
        res["bets"] = {"n": 0}
    return res


BANDS = [1, 2, 3, 4.5, 7, 100]


def band_ratios(df: pd.DataFrame, market: str, col: str) -> Dict[float, float]:
    """Ratio médian Winamax / référence par tranche de la cote de RÉFÉRENCE (borne haute -> ratio)."""
    ref = df["winamax"] / df[col]
    sub = df[(df.market == market) & ref.notna()].assign(ref_price=lambda d: d["winamax"] / d[col])
    sub = sub.assign(ref_odds=df.loc[sub.index, "winamax"] / sub["ref_price"])
    out = {}
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        g = sub[(sub.ref_odds > lo) & (sub.ref_odds <= hi)]
        out[hi] = float(g["ref_price"].median()) if len(g) >= 10 else float(sub["ref_price"].median())
    return out


def _apply_bands(odds: pd.Series, bands: Dict[float, float]) -> pd.Series:
    """Cote de référence × ratio de sa tranche."""
    r = pd.Series(np.nan, index=odds.index)
    for lo, hi in zip(BANDS[:-1], BANDS[1:]):
        m = (odds > lo) & (odds <= hi)
        r[m] = bands[hi]
    return odds * r


def volume_with_haircut(h_soft, h_pin) -> Dict:
    """Rejoue 2023-25 (prédictions walk-forward) avec la décote mesurée, règle de prix de la prod.

    h_soft / h_pin : décote uniforme (float) ou par tranche de cote ({borne haute: ratio}).
    """
    from nhl.core.betting import BetParams, select_bets
    from nhl.scripts.export_simulator_data import load_preds
    p = load_preds("p1b_ens")
    p = p[p.eligible].copy()
    soft = _apply_bands(p["soft_median"], h_soft) if isinstance(h_soft, dict) else p["soft_median"] * h_soft
    pin = _apply_bands(p["pin_yes"], h_pin) if isinstance(h_pin, dict) else p["pin_yes"] * h_pin
    p["px"] = soft.where(soft.notna(), pin)
    p.loc[p.market == "ast", "px"] = pin[p.market == "ast"]  # passes : Pinnacle seul en live
    params, rows = BetParams.from_config(), []
    for _, day in p[p["px"].notna()].groupby("date"):
        rows += select_bets([{"market": x.market, "p_model": x.p_model, "p_novig": x.p_novig, "cote": x.px,
                              "game_id": x.gameId, "won": x.won, "date": x.date} for x in day.itertuples()],
                            100.0, params)
    b = pd.DataFrame(rows)
    if b.empty:
        return {"n": 0}
    b["profit"] = np.where(b.won == 1, b.mise * (b.cote - 1), -b.mise)
    daily = b.groupby("date")["profit"].sum().sort_index().cumsum()
    pin_b = b[b.p_novig.notna()]
    return {"n": int(len(b)), "by_market": b.groupby("market").size().to_dict(), "profit": float(b.profit.sum()),
            "roi": float(b.profit.sum() / b.mise.sum()), "max_dd": float((daily.cummax().clip(lower=0) - daily).max()),
            "ev_pinnacle": float((pin_b.p_novig * pin_b.cote - 1).mean())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="interroge The Odds API (sinon cache seul)")
    ap.add_argument("--max-credits", type=int, default=800)
    a = ap.parse_args()
    snap = pd.read_parquet(SNAPSHOTS)
    # Le cache est toujours lu d'abord ; sans --fetch, aucun crédit ne peut être dépensé
    raw = fetch_reference_odds(snap, a.max_credits if a.fetch else 0)
    ref = reference_table(raw)
    df = match_tables(snap, ref)
    from nhl.core.inference import FeatureEngine
    eng = FeatureEngine()
    eng.refresh(collect=True)  # collecte les logs 2026-27 (résultats de ces matchs)
    df = attach_outcomes(df, eng.logs)
    df["r_soft"] = df["winamax"] / df["soft_median"]
    df["r_pin"] = df["winamax"] / df["pin_yes"]
    df["ev_fair"] = df["p_shin"] * df["winamax"] - 1
    df = model_predictions(df, eng)
    out = os.path.join(ODDS_DIR, "winamax_calibration_rows.parquet")
    df.to_parquet(out, index=False)
    print(f"Lignes rapprochées -> {out}")
    res = analyze(df)
    h_soft = res["but"]["vs_soft"]["median"]
    h_pin = {mk: res[mk]["vs_pin"]["median"] for mk in ("but", "ast")}
    res["volume"] = {"actuel (0.94 / 0.90)": volume_with_haircut(0.94, 0.90),
                     f"mesuré uniforme ({h_soft:.3f} / {h_pin['ast']:.3f})": volume_with_haircut(h_soft, h_pin["ast"])}
    bands_soft, bands_pin = band_ratios(df, "but", "soft_median"), band_ratios(df, "ast", "pin_yes")
    res["bands"] = {"but_vs_soft": bands_soft, "ast_vs_pin": bands_pin}
    res["volume"]["mesuré par tranche de cote"] = volume_with_haircut(bands_soft, bands_pin)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps({k: v for k, v in res.items() if k != "bets"}, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: v for k, v in res["bets"].items() if k != "list"}, indent=1, default=str))


if __name__ == "__main__":
    main()
