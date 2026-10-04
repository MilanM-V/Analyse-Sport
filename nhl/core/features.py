"""
core/features.py — Construction UNIQUE des features (entraînement, simulation, production).

Entrée : des logs de match au schéma `nhl.data.gamelog_schema` (MoneyPuck pour
l'historique, API NHL pour la saison en cours et la prod), éventuellement complétés
par des lignes "match à venir" (stats NaN) pour l'inférence du jour.

Toutes les features d'un match n'utilisent QUE des informations antérieures au
match (shift(1) systématique), et ne dépendent que de stats définies à l'identique
dans les deux sources (buts, passes, tirs, tentatives, TOI, TOI PP) — c'est la
garantie de parité train/serve (cf. audit P0-1).

Les agrégats de saison MoneyPuck (`nhl/data/*_all.csv`) servent uniquement de
priors de la SAISON PRÉCÉDENTE (aucune fuite) ; s'ils manquent, les colonnes
correspondantes valent NaN (gérées nativement par les modèles de boosting).
"""
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from nhl.data.gamelog_schema import GAMELOG_COLUMNS, clean_team

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FEATURES_VERSION = "p1-2026-10"

# Priors de shrinkage (en matchs ou en heures) — volontairement simples et documentés
SH_PCT_PRIOR, SH_PCT_K = 0.095, 60.0       # Beta : ~60 tirs de poids vers 9,5 %
TEAM_K_GAMES = 10.0                         # contexte équipe : 10 matchs de poids vers la moyenne


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _shift_roll(df: pd.DataFrame, key: str, cols: List[str], window: int, prefix: str = "") -> pd.DataFrame:
    """Moyenne glissante des `window` matchs PRÉCÉDENTS (shift 1) par `key`."""
    sh = df.groupby(key, sort=False)[cols].shift(1)
    out = sh.groupby(df[key], sort=False).rolling(window, min_periods=1).mean()
    out = out.reset_index(level=0, drop=True).reindex(df.index)
    return out.add_suffix(f"_l{window}").add_prefix(prefix)


def _shift_ewm(df: pd.DataFrame, key: str, cols: List[str], halflife: float) -> pd.DataFrame:
    """Moyenne exponentielle des matchs précédents (shift 1) par `key`."""
    sh = df.groupby(key, sort=False)[cols].shift(1)
    out = sh.groupby(df[key], sort=False).transform(lambda s: s.ewm(halflife=halflife, ignore_na=True).mean())
    return out.add_suffix("_ewm")


def _shift_cum(df: pd.DataFrame, keys: List[str], cols: List[str]) -> pd.DataFrame:
    """Somme cumulée des matchs précédents par `keys` (NaN -> 0)."""
    # fillna(0) AVANT cumsum : sinon la ligne d'un match à venir (stats NaN) vaudrait NaN
    vals = df[cols].fillna(0)
    return vals.groupby([df[k] for k in keys], sort=False).cumsum() - vals


# ─────────────────────────────────────────────────────────────────────────────
# Priors de saison précédente (agrégats MoneyPuck combinés)
# ─────────────────────────────────────────────────────────────────────────────
def load_season_priors(data_dir: str = DATA_DIR) -> Dict[str, pd.DataFrame]:
    """Charge les priors (saison s-1 rattachée à la saison s) depuis *_all.csv.

    Returns:
        {'player': DataFrame[playerId, season, prev_*], 'team': DataFrame[team, season, prev_*]}
        (DataFrames vides si les fichiers sont absents).
    """
    out: Dict[str, pd.DataFrame] = {"player": pd.DataFrame(), "team": pd.DataFrame()}
    sk_path = os.path.join(data_dir, "skaters_all.csv")
    if os.path.exists(sk_path):
        cols = ["playerId", "season", "situation", "icetime", "I_F_xGoals", "I_F_goals",
                "I_F_primaryAssists", "I_F_secondaryAssists", "I_F_shotsOnGoal", "OnIce_F_xGoals"]
        sk = pd.read_csv(sk_path, usecols=cols)
        allsit = sk[sk.situation == "all"].copy()
        pp = sk[sk.situation == "5on4"][["playerId", "season", "icetime"]].rename(columns={"icetime": "pp_icetime"})
        allsit = allsit.merge(pp, on=["playerId", "season"], how="left")
        h = (allsit["icetime"] / 3600.0)
        lg = allsit[["I_F_xGoals", "I_F_goals", "I_F_shotsOnGoal", "OnIce_F_xGoals"]].sum() / h.sum()
        lg_a = (allsit["I_F_primaryAssists"] + allsit["I_F_secondaryAssists"]).sum() / h.sum()
        k = 5.0  # 5 heures de glace de poids vers la moyenne de la ligue
        p = pd.DataFrame({"playerId": allsit["playerId"], "season": allsit["season"] + 1})
        p["prev_ixg60"] = (allsit["I_F_xGoals"] + k * lg["I_F_xGoals"]) / (h + k)
        p["prev_g60"] = (allsit["I_F_goals"] + k * lg["I_F_goals"]) / (h + k)
        p["prev_sog60"] = (allsit["I_F_shotsOnGoal"] + k * lg["I_F_shotsOnGoal"]) / (h + k)
        p["prev_a60"] = (allsit["I_F_primaryAssists"] + allsit["I_F_secondaryAssists"] + k * lg_a) / (h + k)
        p["prev_onice_xgf60"] = (allsit["OnIce_F_xGoals"] + k * lg["OnIce_F_xGoals"]) / (h + k)
        p["prev_pp_share"] = (allsit["pp_icetime"].fillna(0) / allsit["icetime"].replace(0, np.nan))
        p["prev_toi_pg_h"] = h
        out["player"] = p.drop_duplicates(["playerId", "season"], keep="last")

    tm_path = os.path.join(data_dir, "teams_all.csv")
    gk_path = os.path.join(data_dir, "goalies_all.csv")
    if os.path.exists(tm_path):
        tm = pd.read_csv(tm_path, usecols=["team", "season", "situation", "iceTime", "xGoalsAgainst", "goalsAgainst"])
        tm = tm[tm.situation == "all"].copy()
        tm["team"] = tm["team"].map(clean_team)
        t = pd.DataFrame({"team": tm["team"], "season": tm["season"] + 1,
                          "prev_xga60": tm["xGoalsAgainst"] / tm["iceTime"] * 3600})
        if os.path.exists(gk_path):
            gk = pd.read_csv(gk_path, usecols=["team", "season", "situation", "icetime", "xGoals", "goals"])
            gk = gk[gk.situation == "all"].copy()
            gk["team"] = gk["team"].map(clean_team)
            ga = gk.groupby(["team", "season"])[["icetime", "xGoals", "goals"]].sum().reset_index()
            ga["prev_gsax60"] = (ga["xGoals"] - ga["goals"]) / ga["icetime"] * 3600
            ga["season"] = ga["season"] + 1
            t = t.merge(ga[["team", "season", "prev_gsax60"]], on=["team", "season"], how="left")
        # Relocalisation Arizona -> Utah (2024) : on prolonge les priors de l'ancienne franchise
        ari = t[t.team == "ARI"].copy()
        ari["team"] = "UTA"
        t = pd.concat([t, ari[~ari.season.isin(t[t.team == "UTA"].season)]], ignore_index=True)
        out["team"] = t.drop_duplicates(["team", "season"], keep="first")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Construction des features
# ─────────────────────────────────────────────────────────────────────────────
def build_features(logs: pd.DataFrame, priors: Optional[Dict[str, pd.DataFrame]] = None) -> pd.DataFrame:
    """Construit la table de features (une ligne par joueur x match).

    Args:
        logs: logs de match au schéma GAMELOG_COLUMNS. Les matchs à venir sont des
            lignes dont les colonnes de stats (g, a1, sog...) sont NaN.
        priors: sortie de load_season_priors() (optionnel).

    Returns:
        DataFrame avec identifiants, features, cibles (`target_but`, `target_ast`,
        NaN pour les matchs à venir) et la colonne `date`.
    """
    missing = [c for c in GAMELOG_COLUMNS if c not in logs.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {missing}")
    df = logs[GAMELOG_COLUMNS].copy()
    df["gameDate"] = pd.to_datetime(df["gameDate"])
    df = (df.sort_values(["gameDate", "gameId", "playerId"])
            .drop_duplicates(["playerId", "gameId"], keep="last"))
    df = df.sort_values(["playerId", "gameDate", "gameId"]).reset_index(drop=True)

    stat_cols = ["g", "a1", "a2", "sog", "missed", "blocked_att", "pp_g", "pp_sog", "toi", "pp_toi"]
    df[stat_cols] = df[stat_cols].astype(float)
    df["a"] = df["a1"] + df["a2"]
    df["att"] = df["sog"] + df["missed"] + df["blocked_att"]
    upcoming = df["toi"].isna()

    # ── Forme récente du joueur (tous matchs précédents, à travers les saisons) ──
    roll_cols = ["sog", "att", "toi", "pp_toi", "pp_sog", "g", "a", "a1"]
    parts = [df]
    for w in (5, 10, 20):
        parts.append(_shift_roll(df, "playerId", roll_cols, w))
    parts.append(_shift_ewm(df, "playerId", ["sog", "att", "toi", "pp_toi", "a"], halflife=8))
    df = pd.concat(parts, axis=1)

    # ── Saison en cours (to-date, strictement avant le match) ──
    cum_cols = ["g", "a", "a1", "sog", "att", "toi", "pp_toi"]
    cum = _shift_cum(df, ["playerId", "season"], cum_cols)
    df["std_gp"] = df.groupby(["playerId", "season"], sort=False).cumcount().astype(float)
    gp = df["std_gp"].replace(0, np.nan)
    for c in cum_cols:
        df[f"std_{c}_pg"] = cum[c] / gp

    # ── Carrière (depuis le début des logs) : taux par 60 min et réussite au tir shrinkés ──
    car = _shift_cum(df, ["playerId"], ["g", "a", "sog", "toi"])
    hours = car["toi"] / 60.0
    df["car_hours"] = hours
    df["car_g60"] = (car["g"] + 0.85 * 3) / (hours + 3)        # ~0,85 but/60 moyen attaquant, 3 h de poids
    df["car_a60"] = (car["a"] + 1.30 * 3) / (hours + 3)
    df["car_sog60"] = (car["sog"] + 7.0 * 3) / (hours + 3)
    df["sh_pct_shrunk"] = (car["g"] + SH_PCT_PRIOR * SH_PCT_K) / (car["sog"] + SH_PCT_K)
    df["exp_g_l20"] = df["sog_l20"] * df["sh_pct_shrunk"]
    df["exp_g_ewm"] = df["sog_ewm"] * df["sh_pct_shrunk"]

    # ── Rôle dans l'équipe (rangs calculés parmi les joueurs alignés ce match) ──
    grp = df.groupby(["gameId", "team"], sort=False)
    df["pp_rank"] = grp["pp_toi_l10"].rank(ascending=False, method="first")
    df["toi_rank"] = grp["toi_l10"].rank(ascending=False, method="first")
    df["team_pp_share"] = df["pp_toi_l10"] / grp["pp_toi_l10"].transform("sum").replace(0, np.nan)
    df["is_D"] = (df["position"] == "D").astype(int)
    df["is_C"] = (df["position"] == "C").astype(int)
    fwd = df["is_D"] == 0
    df["toi_rank_pos"] = df[fwd].groupby(["gameId", "team"])["toi_l10"].rank(ascending=False, method="first")
    df.loc[~fwd, "toi_rank_pos"] = df[~fwd].groupby(["gameId", "team"])["toi_l10"].rank(ascending=False, method="first")

    # ── Contexte équipe / adversaire (agrégé par match, décalé) ──
    tg = (df.groupby(["gameId", "gameDate", "season", "team", "opp"], sort=False)
            .agg(gf=("g", lambda s: s.sum(min_count=1)), sog_f=("sog", lambda s: s.sum(min_count=1)),
                 att_f=("att", lambda s: s.sum(min_count=1)), pp_gf=("pp_g", lambda s: s.sum(min_count=1)))
            .reset_index())
    against = tg[["gameId", "team", "gf", "sog_f", "att_f", "pp_gf"]].rename(
        columns={"team": "opp", "gf": "ga", "sog_f": "sa", "att_f": "att_a", "pp_gf": "pp_ga"})
    tg = tg.merge(against, on=["gameId", "opp"], how="left")
    tg = tg.sort_values(["team", "gameDate", "gameId"]).reset_index(drop=True)
    tcols = ["gf", "sog_f", "ga", "sa", "att_a", "pp_ga"]
    tcum = _shift_cum(tg, ["team", "season"], tcols)
    tg["t_gp"] = tg.groupby(["team", "season"], sort=False).cumcount().astype(float)
    # Moyennes de ligue "à date" (matchs des jours strictement antérieurs de la saison)
    # pour le shrinkage — utiliser la moyenne de toute la saison serait une fuite.
    daily = tg.groupby(["season", "gameDate"])[tcols].agg(["sum", "count"])
    prior_cum = daily.groupby(level="season").cumsum() - daily
    lg_vals = {c: prior_cum[(c, "sum")] / prior_cum[(c, "count")].replace(0, np.nan) for c in tcols}
    lg = pd.DataFrame(lg_vals).reset_index()
    defaults = {"gf": 3.0, "ga": 3.0, "sog_f": 30.0, "sa": 30.0, "att_a": 55.0, "pp_ga": 0.6}  # début de saison
    lg = tg[["season", "gameDate"]].merge(lg, on=["season", "gameDate"], how="left")
    lg = lg.fillna(defaults)
    for c in tcols:
        tg[f"t_{c}_pg"] = (tcum[c] + TEAM_K_GAMES * lg[c]) / (tg["t_gp"] + TEAM_K_GAMES)
    tg["t_sv_pct"] = 1.0 - tg["t_ga_pg"] / tg["t_sa_pg"]
    tl = _shift_roll(tg, "team", ["ga", "gf", "sa"], 10, prefix="t_")
    tg = pd.concat([tg, tl], axis=1)
    prev_date = tg.groupby("team", sort=False)["gameDate"].shift(1)
    tg["rest_days"] = (tg["gameDate"] - prev_date).dt.days.clip(upper=10)
    tg["b2b"] = (tg["rest_days"] == 1).astype(int)

    own = tg[["gameId", "team", "t_gf_pg", "t_sog_f_pg", "t_gf_l10", "rest_days", "b2b"]].rename(
        columns={"t_gf_pg": "team_gf_pg", "t_sog_f_pg": "team_sog_pg", "t_gf_l10": "team_gf_l10"})
    opp = tg[["gameId", "team", "t_ga_pg", "t_sa_pg", "t_att_a_pg", "t_sv_pct", "t_ga_l10", "t_sa_l10",
              "t_pp_ga_pg", "rest_days", "b2b"]].rename(columns={
        "team": "opp", "t_ga_pg": "opp_ga_pg", "t_sa_pg": "opp_sa_pg", "t_att_a_pg": "opp_att_a_pg",
        "t_sv_pct": "opp_sv_pct", "t_ga_l10": "opp_ga_l10", "t_sa_l10": "opp_sa_l10",
        "t_pp_ga_pg": "opp_pp_ga_pg", "rest_days": "opp_rest_days", "b2b": "opp_b2b"})
    df = df.merge(own, on=["gameId", "team"], how="left").merge(opp, on=["gameId", "opp"], how="left")
    # Interactions joueur x adversaire (piste F)
    df["sog_x_opp_leak"] = df["sog_l20"] * (1.0 - df["opp_sv_pct"])
    df["pp_x_opp_pk"] = df["team_pp_share"] * df["opp_pp_ga_pg"]

    # ── Priors de saison précédente (agrégats MoneyPuck) ──
    if priors:
        if not priors.get("player", pd.DataFrame()).empty:
            df = df.merge(priors["player"], on=["playerId", "season"], how="left")
        if not priors.get("team", pd.DataFrame()).empty:
            tp = priors["team"].rename(columns={"team": "opp", "prev_xga60": "opp_prev_xga60",
                                                "prev_gsax60": "opp_prev_gsax60"})
            df = df.merge(tp, on=["opp", "season"], how="left")
    for c in ("prev_ixg60", "prev_g60", "prev_sog60", "prev_a60", "prev_onice_xgf60",
              "prev_pp_share", "prev_toi_pg_h", "opp_prev_xga60", "opp_prev_gsax60"):
        if c not in df:
            df[c] = np.nan

    # ── Cibles ──
    df["target_but"] = np.where(upcoming, np.nan, (df["g"] > 0).astype(float))
    df["target_ast"] = np.where(upcoming, np.nan, (df["a"] > 0).astype(float))
    # Marchés candidats (piste G) : points ≥ 1, tirs cadrés ≥ 2 / ≥ 3
    df["target_pts"] = np.where(upcoming, np.nan, ((df["g"] + df["a"]) > 0).astype(float))
    df["target_sog2"] = np.where(upcoming, np.nan, (df["sog"] >= 2).astype(float))
    df["target_sog3"] = np.where(upcoming, np.nan, (df["sog"] >= 3).astype(float))
    df["date"] = df["gameDate"]
    return df


# Listes de features par marché (ordre figé, enregistré avec le modèle)
_COMMON = [
    "sog_l5", "sog_l10", "sog_l20", "att_l10", "att_l20", "toi_l5", "toi_l10", "toi_l20",
    "pp_toi_l10", "pp_sog_l10", "sog_ewm", "att_ewm", "toi_ewm", "pp_toi_ewm",
    "std_gp", "std_sog_pg", "std_att_pg", "std_toi_pg", "std_pp_toi_pg",
    "car_hours", "car_sog60", "sh_pct_shrunk",
    "pp_rank", "toi_rank", "toi_rank_pos", "is_home", "rest_days", "b2b", "opp_rest_days", "opp_b2b",
    "opp_ga_pg", "opp_sa_pg", "opp_att_a_pg", "opp_sv_pct", "opp_ga_l10", "opp_sa_l10",
    "team_gf_pg", "team_sog_pg", "team_gf_l10",
    "prev_ixg60", "prev_sog60", "prev_pp_share", "prev_toi_pg_h", "prev_onice_xgf60",
    "opp_prev_xga60", "opp_prev_gsax60",
]
FEATURES: Dict[str, List[str]] = {
    "but": _COMMON + ["g_l10", "g_l20", "std_g_pg", "car_g60", "prev_g60", "exp_g_l20", "exp_g_ewm", "is_C"],
    "ast": _COMMON + ["a_l10", "a_l20", "a1_l10", "a_ewm", "std_a_pg", "std_a1_pg", "car_a60", "prev_a60",
                      "is_D", "is_C"],
}


def load_all_gamelogs(gamelog_dir: Optional[str] = None) -> pd.DataFrame:
    """Concatène l'historique MoneyPuck et toutes les saisons API NHL disponibles.

    En cas de recouvrement (même playerId, gameId), la source API NHL l'emporte.
    """
    gamelog_dir = gamelog_dir or os.path.join(DATA_DIR, "gamelogs")
    frames = []
    mp = os.path.join(gamelog_dir, "mp_gamelogs.parquet")
    if os.path.exists(mp):
        frames.append(pd.read_parquet(mp))
    for f in sorted(os.listdir(gamelog_dir)) if os.path.isdir(gamelog_dir) else []:
        if f.startswith("nhlapi_") and f.endswith(".parquet"):
            frames.append(pd.read_parquet(os.path.join(gamelog_dir, f)))
    if not frames:
        raise FileNotFoundError(f"Aucun gamelog dans {gamelog_dir}")
    logs = pd.concat(frames, ignore_index=True)
    return logs.drop_duplicates(["playerId", "gameId"], keep="last")

# Piste F : features additionnelles (évaluées dans nhl/sim/phases.py avant adoption)
FEATURES_EXTRA = ["team_pp_share", "opp_pp_ga_pg", "sog_x_opp_leak", "pp_x_opp_pk"]
FEATURES_V2: Dict[str, List[str]] = {m: FEATURES[m] + FEATURES_EXTRA for m in FEATURES}
# Piste G : marchés candidats (même socle que le buteur / passeur)
FEATURES_G: Dict[str, List[str]] = {
    "pts": FEATURES_V2["ast"] + ["g_l10", "g_l20", "std_g_pg", "car_g60", "exp_g_l20"],
    "sog2": FEATURES_V2["but"],
    "sog3": FEATURES_V2["but"],
}
