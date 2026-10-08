"""
sim/phases.py — Définition des phases simulées par nhl/scripts/simulate_roi.py.

Chaque fonction retourne un PhaseSpec décrivant les données, le modèle et les
règles de pari de la phase. Les règles de pari appellent le code de PROD tel
qu'il existe au moment de la simulation.
"""
import logging
import os
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NHL_DIR = os.path.join(ROOT, "nhl")
for p in (ROOT, NHL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from nhl.config.settings import cfg  # noqa: E402
from nhl.scripts.simulate_roi import PhaseSpec, season_to_date_stats  # noqa: E402

# Le code de prod logge chaque rejet : inutile en simulation
for name in ("NHL_Bot", "NHL.Filter", "NHL.BotLogic"):
    logging.getLogger(name).setLevel(logging.ERROR)

MAX_EXPOSURE = 15.0                       # plafond d'exposition journalier de bot_logic
BRIER_PENALTY = {"but": 0.0, "ast": 4.0}  # valeurs effectives en prod (holdout_brier 0.122 / 0.172)
CATEGORY = {"but": "BUTEUR", "ast": "PASSEUR"}


def _std_stats() -> pd.DataFrame:
    """Stats saison/L10 vues par le bot avant chaque match (gamelogs MoneyPuck + API NHL).

    Avant le 2026-10-08, seuls les logs MoneyPuck (jusqu'à 2024-25) étaient lus : std_gp, G/GP,
    A/GP et ATOI_L10 valaient 0 sur toutes les lignes à partir de 2025-26.
    """
    from nhl.core.features import load_all_gamelogs
    return season_to_date_stats(load_all_gamelogs())


# ─────────────────────────────────────────────────────────────────────────────
# Règles de prod (communes baseline / P0 / P1) — appellent le code réel
# ─────────────────────────────────────────────────────────────────────────────
def prod_eligible(df: pd.DataFrame, market: str) -> pd.Series:
    """Rejoue bot_logic (filtre ATOI) + market_filter.evaluate_player_markets."""
    from nhl.core.market_filter import evaluate_player_markets
    atoi_min = cfg.thresholds.general.atoi_min
    res = []
    for r in df[["ATOI_L10", "G_GP", "A_GP", "std_gp", "pos_bot", "is_home"]].itertuples(index=False):
        if r.ATOI_L10 < atoi_min:
            res.append(False)
            continue
        p_form = {"ATOI": r.ATOI_L10, "L10_SOG_G": 0.0, "L10_iHDCF_G": 0.0, "L10_A_G": 0.0}
        v5_p = {"G_GP": r.G_GP, "A_GP": r.A_GP, "GP": int(r.std_gp), "Position": r.pos_bot}
        cat_but, cat_ast = evaluate_player_markets("", p_form, v5_p, {}, bool(r.is_home))
        res.append(bool(cat_but) if market == "but" else bool(cat_ast))
    return pd.Series(res, index=df.index)


def historic_eligible(df: pd.DataFrame, market: str) -> pd.Series:
    """Éligibilité de prod telle qu'elle était avant l'audit du 2026-10-04 (passeurs à domicile
    seulement), figée pour que baseline / p0 / p1* restent rejouables après les changements du TOML."""
    return make_eligible(home_only_ast=True, fallback_prev_season=False)(df, market)


def prod_select_and_stake(day: pd.DataFrame) -> pd.DataFrame:
    """Rejoue bot_logic.run_analysis_and_send : filtre EV, is_cote_valid, Kelly + exposition."""
    from nhl.sim.legacy import apply_kelly_to_picks, get_adaptive_ev_threshold, is_cote_valid
    exposure = 0.0
    rows = []
    for market, cote_min in (("but", cfg.thresholds.buteurs.cote_min), ("ast", cfg.thresholds.passeurs.cote_min)):
        d = day[day["market"] == market]
        picks = []
        for r in d.itertuples(index=False):
            cote = float(r.exec_price)
            ev = r.p_model * cote - 1.0
            if r.p_model >= 0.60 or ev >= get_adaptive_ev_threshold(cote):
                picks.append({"Joueur": r.playerId, "Proba": float(r.p_model), "Cote": cote,
                              "Categorie": CATEGORY[market], "_won": r.won, "_pnv": r.p_novig})
        picks = [p for p in picks if is_cote_valid(p, cote_min)]
        picks.sort(key=lambda p: p["Proba"] * p["Cote"], reverse=True)
        exposure = apply_kelly_to_picks(picks, exposure, MAX_EXPOSURE, brier_penalty=BRIER_PENALTY[market])
        for p in picks:
            rows.append({"date": day["date"].iloc[0], "market": market, "playerId": p["Joueur"],
                         "p": p["Proba"], "cote": p["Cote"], "mise": p.get("MiseNum", 0.0),
                         "won": p["_won"], "p_novig": p["_pnv"]})
    return pd.DataFrame(rows)


# Listes de features de l'ancien train_models.py (figées ici pour rejouer la baseline)
_HIST_BASE = [
    'ixg_l10', 'hdcf_l10', 'sog_l10', 'atoi_l10', 'l10_g', 'l10_a',
    'season_g', 'season_a', 'season_pts', 'ixg_x_hdcf', 'sog_x_atoi',
    'is_top6', 'prior_g60', 'prior_a60', 'prior_sog60', 'prior_sh_pct',
    'opp_xga_60', 'opp_hdca_60', 'opp_goalie_gsax_60', 'team_xg_60',
    'ixg_x_opp_xga', 'is_home', 'goalie_weakness'
]
FEATURES_HIST_BUT = [f for f in _HIST_BASE if f not in ['season_a', 'l10_a', 'prior_a60']]
FEATURES_HIST_AST = [f for f in _HIST_BASE if f not in ['prior_sh_pct']]


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE — pipeline actuel tel quel
# ─────────────────────────────────────────────────────────────────────────────
def baseline() -> PhaseSpec:
    """Pipeline existant : historical_dataset.parquet + NHLEnsembleClassifier + règles de prod."""
    from nhl.sim.legacy import NHLEnsembleClassifier

    def load() -> pd.DataFrame:
        df = pd.read_parquet(os.path.join(NHL_DIR, "data", "historical_dataset.parquet"))
        df["date"] = pd.to_datetime(df["gameDate"])
        df["target_but"] = df["target_but_0_5"]
        df["target_ast"] = df["target_ast_0_5"]
        df["goalie_weakness"] = 0.08  # comme train_models.py (pas de SV% dans le parquet)
        std = _std_stats().rename(columns={"position": "pos_bot"})
        df = df.merge(std, on=["playerId", "gameId"], how="left")
        df["pos_bot"] = df["pos_bot"].fillna("")
        for c in ("ATOI_L10", "G_GP", "A_GP", "std_gp"):
            df[c] = df[c].fillna(0)
        return df

    return PhaseSpec(
        name="baseline",
        load=load,
        features={"but": FEATURES_HIST_BUT, "ast": FEATURES_HIST_AST},
        model_factory=lambda m: NHLEnsembleClassifier(market=m, mode="ensemble", n_splits=3, random_state=42),
        train_mask=lambda df, m: pd.Series(True, index=df.index),
        eligible=historic_eligible,
        select_and_stake=prod_select_and_stake,
        notes=("Pipeline actuel : features MoneyPuck (xG inclus, défenseurs dans le train), ensemble "
               "XGB/LGBM/CatBoost (scale_pos_weight + sigmoid), filtres de prod (bug ailiers L/R inclus), "
               "cote_min 4,5 / 2,5, EV adaptatif, Kelly 1/8 plancher 0,5 U, exposition 15 U/jour. "
               "⚠️ Optimiste vs la prod réelle : le backtest voit le xG MoneyPuck que la prod n'a pas."),
    )


# ─────────────────────────────────────────────────────────────────────────────
# P0 — correctifs bloquants (seul le filtre ailiers change la simulation)
# ─────────────────────────────────────────────────────────────────────────────
def p0() -> PhaseSpec:
    """Baseline + correctifs P0 : même modèle, éligibilité corrigée (ailiers L/R)."""
    spec = baseline()
    spec.name = "p0"
    spec.extra["reuse_preds"] = "baseline"
    spec.notes = ("P0 : ailiers L/R réintégrés au marché buteur (market_filter), dédoublonnage des picks, "
                  "mode paper, crash `dt` corrigé. Même modèle que la baseline (prédictions réutilisées).")
    return spec


# ─────────────────────────────────────────────────────────────────────────────
# P1a — données & features à parité train/serve (même modèle que la baseline)
# ─────────────────────────────────────────────────────────────────────────────
def _p1_load() -> pd.DataFrame:
    """Features de nhl.core.features sur tous les gamelogs (MoneyPuck 2008-2024 + API NHL 2025)."""
    from nhl.core.features import build_features, load_all_gamelogs, load_season_priors
    df = build_features(load_all_gamelogs(), load_season_priors())
    df = df[df["season"] >= 2009]  # 2008 = rodage des fenêtres glissantes
    std = _std_stats()[["playerId", "gameId", "std_gp", "G_GP", "A_GP", "ATOI_L10"]]
    df = df.drop(columns=["std_gp"]).merge(std, on=["playerId", "gameId"], how="left")
    df["std_gp_bot"] = df["std_gp"]
    df["pos_bot"] = df["position"]
    for c in ("ATOI_L10", "G_GP", "A_GP", "std_gp"):
        df[c] = df[c].fillna(0)
    return df


def _p1_features() -> Dict[str, List[str]]:
    from nhl.core.features import FEATURES
    return {m: list(FEATURES[m]) for m in FEATURES}


def p1a() -> PhaseSpec:
    """Features unifiées (parité prod), attaquants seuls pour le buteur, modèle inchangé."""
    from nhl.sim.legacy import NHLEnsembleClassifier
    return PhaseSpec(
        name="p1a",
        load=_p1_load,
        features=_p1_features(),
        model_factory=lambda m: NHLEnsembleClassifier(market=m, mode="ensemble", n_splits=3, random_state=42),
        train_mask=lambda df, m: (df["position"] != "D") if m == "but" else pd.Series(True, index=df.index),
        eligible=historic_eligible,
        select_and_stake=prod_select_and_stake,
        notes=("P1a : features construites par nhl/core/features.py à partir de stats identiques MoneyPuck / "
               "API NHL (plus de xG en cours de saison ; xG seulement en prior de saison précédente), clé playerId, "
               "saison 2025-26 ajoutée via l'API NHL, priors de saison issus des *_all.csv, défenseurs exclus du "
               "train buteur, données depuis 2009. Modèle identique à la baseline pour isoler l'effet des données."),
    )


# ─────────────────────────────────────────────────────────────────────────────
# P1b — modélisation : sans repondération, isotonique sur bloc temporel
# ─────────────────────────────────────────────────────────────────────────────
def _p1b(name: str, algos: tuple) -> PhaseSpec:
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    spec = p1a()
    spec.name = name
    spec.model_factory = lambda m: TemporalCalibratedGBM(algos=algos, calib_frac=0.15)
    spec.notes = (f"P1b : features P1a + modèle TemporalCalibratedGBM{algos} — scale_pos_weight=1, "
                  "calibration isotonique sur les 15 % de lignes les plus récentes (hors apprentissage). "
                  "Sélection du modèle sur la log-loss de VALIDATION (2023-24), pas sur le ROI.")
    return spec


def p1b_lgbm() -> PhaseSpec:
    return _p1b("p1b_lgbm", ("lgbm",))


def p1b_ens() -> PhaseSpec:
    return _p1b("p1b_ens", ("lgbm", "xgb", "cat"))


# ─────────────────────────────────────────────────────────────────────────────
# P2 — stratégie de mise (nhl/core/betting.py), réglée sur la validation seulement
# ─────────────────────────────────────────────────────────────────────────────
def best_p1b() -> str:
    """Phase P1b dont la log-loss moyenne (but + ast) en VALIDATION est la plus basse."""
    from nhl.scripts.simulate_roi import REPORT_CSV
    r = pd.read_csv(REPORT_CSV)
    r = r[r.phase.isin(["p1b_lgbm", "p1b_ens"]) & (r.period == "val") & (r.price == "exec")
          & r.market.isin(["but", "ast"])]
    return str(r.groupby("phase")["ll_model"].mean().idxmin())


def p2_params(src: str):
    """BetParams issus de tune_betting.py (validation) pour la phase source `src`."""
    import json
    from nhl.core.betting import BetParams
    from nhl.scripts.simulate_roi import REPORT_DIR
    with open(os.path.join(REPORT_DIR, f"betting_params_{src}.json"), encoding="utf-8") as f:
        t = json.load(f)
    ev = t["ev_thresholds"]
    markets = tuple(m for m in ("but", "ast") if t.get(f"enable_{m}", True))
    return BetParams.from_config(
        markets=markets, blend_w={"but": t["blend_w_but"], "ast": t["blend_w_ast"]},
        cote_min={m: t[f"cote_min_{m}"] for m in ("but", "ast")},
        cote_max={m: t[f"cote_max_{m}"] for m in ("but", "ast")},
        ev_low=ev[0], ev_mid=ev[1], ev_high=ev[2], no_pinnacle_extra_ev=t["no_pinnacle_extra_ev"])


def p2_eligible(df: pd.DataFrame, market: str) -> pd.Series:
    """Éligibilité de prod sans le filtre 'passeurs à domicile seulement' (déjà une feature du modèle)."""
    prev = cfg.thresholds.passeurs.home_only
    cfg.thresholds.passeurs.home_only = False
    try:
        return prod_eligible(df, market)
    finally:
        cfg.thresholds.passeurs.home_only = prev


def p2_apriori_params(src: str, w_model_only: bool = False):
    """Stratégie fixée A PRIORI : seul w est appris (log-loss de validation), le reste est standard.

    EV ≥ 5 % uniforme, cotes but [1.5, 15] / ast [1.5, 6], paris sans Pinnacle à EV ≥ 10 %.
    """
    import json
    from nhl.core.betting import BetParams
    from nhl.scripts.simulate_roi import REPORT_DIR
    with open(os.path.join(REPORT_DIR, f"betting_params_{src}.json"), encoding="utf-8") as f:
        t = json.load(f)
    w = {"but": 1.0, "ast": 1.0} if w_model_only else {"but": t["blend_w_but"], "ast": t["blend_w_ast"]}
    return BetParams.from_config(
        markets=("but", "ast"), blend_w=w, cote_min={"but": 1.5, "ast": 1.5}, cote_max={"but": 15.0, "ast": 6.0},
        ev_low=0.05, ev_mid=0.05, ev_high=0.05, no_pinnacle_extra_ev=0.05)


def p2(name: str = "p2", params=None, label: str = "réglée sur la validation (grille ROI)") -> PhaseSpec:
    """Prédictions du meilleur P1b + stratégie betting.select_bets."""
    from nhl.core.betting import select_bets
    src = best_p1b()
    params = params or p2_params(src)
    spec = p1a()
    spec.name = name
    spec.extra["reuse_preds"] = src
    spec.eligible = p2_eligible

    def select_and_stake(day: pd.DataFrame) -> pd.DataFrame:
        cands = [{"market": r.market, "p_model": float(r.p_model), "p_novig": r.p_novig,
                  "cote": float(r.exec_price), "game_id": r.gameId, "won": r.won, "playerId": r.playerId}
                 for r in day.itertuples(index=False)]
        bets = select_bets(cands, 100.0, params)
        return pd.DataFrame([{"date": day["date"].iloc[0], "market": b["market"], "playerId": b["playerId"],
                              "p": b["p_final"], "cote": b["cote"], "mise": b["mise"], "won": b["won"],
                              "p_novig": b["p_novig"]} for b in bets])

    spec.select_and_stake = select_and_stake
    spec.notes = (f"P2 [{label}] : prédictions de `{src}` (meilleure log-loss de validation) + nhl/core/betting.py — "
                  f"mélange modèle/Pinnacle (w but={params.blend_w['but']:.2f}, ast={params.blend_w['ast']:.2f}), "
                  f"marchés {params.markets}, cotes but [{params.cote_min['but']}, {params.cote_max['but']}], "
                  f"ast [{params.cote_min['ast']}, {params.cote_max['ast']}], seuils EV "
                  f"{params.ev_low}/{params.ev_mid}/{params.ev_high}, majoration sans Pinnacle "
                  f"{params.no_pinnacle_extra_ev}, Kelly {params.kelly_fraction} sans plancher, "
                  f"plafond {params.max_game_exposure} U/match.")
    return spec


def p2_apriori() -> PhaseSpec:
    return p2("p2_apriori", p2_apriori_params(best_p1b()), "a priori : w appris en log-loss, seuils standards")


def p2_model() -> PhaseSpec:
    return p2("p2_model", p2_apriori_params(best_p1b(), w_model_only=True), "a priori : modèle seul (w=1)")


def p3() -> PhaseSpec:
    """P2 rejoué avec le code P3 (tests, monitoring, imports, timezone) : non-régression attendue."""
    from nhl.core.betting import BetParams
    spec = p2("p3", BetParams.from_config(), "config de prod settings.toml [betting]")
    spec.notes = ("P3 : stratégie lue dans settings.toml [betting] (code de prod final, après P3). "
                  "Les chiffres doivent être identiques à `p2_apriori`.")
    return spec


PHASES = {
    "baseline": baseline,
    "p0": p0,
    "p1a": p1a,
    "p1b_lgbm": p1b_lgbm,
    "p1b_ens": p1b_ens,
    "p2": p2,
    "p2_apriori": p2_apriori,
    "p2_model": p2_model,
    "p3": p3,
}


# ─────────────────────────────────────────────────────────────────────────────
# Pistes d'amélioration (PISTES_AMELIORATION.md) : variantes de la config de prod
# ─────────────────────────────────────────────────────────────────────────────
def _variant(name: str, label: str, **overrides) -> callable:
    def factory() -> PhaseSpec:
        from nhl.core.betting import BetParams
        return p2(name, BetParams.from_config(**overrides), label)
    return factory


VARIANTS = {
    "x_ev3": _variant("x_ev3", "piste B : EV ≥ 3 %", ev_low=0.03, ev_mid=0.03, ev_high=0.03),
    "x_ev4": _variant("x_ev4", "piste B : EV ≥ 4 %", ev_low=0.04, ev_mid=0.04, ev_high=0.04),
    "x_ev8": _variant("x_ev8", "piste B : EV ≥ 8 %", ev_low=0.08, ev_mid=0.08, ev_high=0.08),
    "x_kelly6": _variant("x_kelly6", "piste C : Kelly 1/6", kelly_fraction=1 / 6),
    "x_kelly4": _variant("x_kelly4", "piste C : Kelly 1/4", kelly_fraction=0.25),
    "x_caps_wide": _variant("x_caps_wide", "piste H : plafonds 5 U/match, 30 U/jour",
                            max_game_exposure=5.0, max_daily_exposure=30.0),
    "x_nopin_off": _variant("x_nopin_off", "piste B' : aucun pari sans référence Pinnacle",
                            no_pinnacle_extra_ev=9.0),
    "x_nopin_10": _variant("x_nopin_10", "piste B' : +10 % d'EV exigée sans Pinnacle",
                           no_pinnacle_extra_ev=0.10),
}
PHASES.update(VARIANTS)
PHASES["x_combo"] = _variant("x_combo", "combo : EV ≥ 4 % + Kelly 1/6 + plafonds 5 U/match, 30 U/jour",
                             ev_low=0.04, ev_mid=0.04, ev_high=0.04, kelly_fraction=1 / 6,
                             max_game_exposure=5.0, max_daily_exposure=30.0)


def _config_select(day: pd.DataFrame) -> pd.DataFrame:
    """Stratégie de mise ACTUELLE (settings.toml [betting]) appliquée à une soirée."""
    from nhl.core.betting import BetParams, select_bets
    cands = [{"market": r.market, "p_model": float(r.p_model), "p_novig": r.p_novig, "cote": float(r.exec_price),
              "game_id": r.gameId, "won": r.won, "playerId": r.playerId} for r in day.itertuples(index=False)]
    bets = select_bets(cands, 100.0, BetParams.from_config())
    return pd.DataFrame([{"date": day["date"].iloc[0], "market": b["market"], "playerId": b["playerId"],
                          "p": b["p_final"], "cote": b["cote"], "mise": b["mise"], "won": b["won"],
                          "p_novig": b["p_novig"]} for b in bets])


def _model_variant(name: str, label: str, feature_set: str = "base", algos: tuple = ("lgbm",),
                   tuned: bool = False) -> callable:
    """Variante de MODÈLE (features / hyperparamètres), stratégie de mise = config actuelle."""
    def factory() -> PhaseSpec:
        import json
        from nhl.core import features as F
        from nhl.core.ensemble_model import TemporalCalibratedGBM
        feats = {"base": F.FEATURES, "v2": F.FEATURES_V2}[feature_set]
        params = {}
        if tuned:
            with open(os.path.join(NHL_DIR, "config", "tuned_gbm_params.json"), encoding="utf-8") as f:
                t = json.load(f)
            params = {m: {"lgbm": t[m]["lgbm"]} for m in ("but", "ast")}
        spec = p1a()
        spec.name = name
        spec.features = {m: list(feats[m]) for m in ("but", "ast")}
        spec.model_factory = lambda m: TemporalCalibratedGBM(algos=algos, params=params.get(m))
        spec.eligible = p2_eligible
        spec.select_and_stake = _config_select
        spec.notes = f"Piste modèle [{label}] — features `{feature_set}`, algos {algos}, tuning={tuned}, stratégie = config actuelle."
        return spec
    return factory


PHASES.update({
    "x_base_lgbm": _model_variant("x_base_lgbm", "référence LGBM", "base"),
    "x_feat_lgbm": _model_variant("x_feat_lgbm", "piste F : features V2", "v2"),
    "x_tuned_lgbm": _model_variant("x_tuned_lgbm", "piste E : LGBM tuné Optuna", "base", tuned=True),
    "x_combo_ens": _model_variant("x_combo_ens", "référence ensemble + config actuelle", "base",
                                  ("lgbm", "xgb", "cat")),
})


def x_monthly() -> PhaseSpec:
    """Piste D : prédictions du retrain MENSUEL (p1b_ens --retrain monthly) + stratégie actuelle."""
    from nhl.core.betting import BetParams
    spec = p2("x_monthly", BetParams.from_config(), "piste D : retrain mensuel + config actuelle")
    spec.extra["reuse_preds"] = "p1b_ens_monthly"
    return spec


PHASES["x_monthly"] = x_monthly


# ─────────────────────────────────────────────────────────────────────────────
# Audit du 2026-10-04 : phases q_* (une par phase P0 → P3 du plan d'exécution)
# Les paramètres de chaque phase sont FIGÉS ici, pour qu'elle reste rejouable
# après les changements ultérieurs de settings.toml.
# ─────────────────────────────────────────────────────────────────────────────
Q_FROZEN_0410 = dict(  # settings.toml [betting] au 2026-10-04 (avant l'audit)
    markets=("but", "ast"), blend_w={"but": 0.65, "ast": 0.80},
    cote_min={"but": 1.5, "ast": 1.5}, cote_max={"but": 15.0, "ast": 6.0},
    ev_low=0.04, ev_mid=0.04, ev_high=0.04, no_pinnacle_extra_ev=0.05, kelly_fraction=0.1667,
    min_stake=0.5, max_stake={"but": 1.5, "ast": 2.0}, max_game_exposure=5.0, max_daily_exposure=30.0,
)


def make_eligible(home_only_ast: bool = False, fallback_prev_season: bool = False):
    """Éligibilité de prod paramétrée.

    Args:
        home_only_ast: applique `[thresholds.passeurs] home_only` (prod au 2026-10-04 : True).
        fallback_prev_season: reproduit le repli de `fetcher.fetch_all` : un joueur sans
            match cette saison mais présent la saison précédente est vu avec GP ≥ 10
            (ses G/GP, A/GP de saison ne sont pas reconstitués : seul le critère ATOI joue).
    """
    def eligible(df: pd.DataFrame, market: str) -> pd.Series:
        d = df
        if fallback_prev_season and "prev_toi_pg_h" in df:
            d = df.copy()
            fb = (d["std_gp"] == 0) & d["prev_toi_pg_h"].notna()
            d.loc[fb, "std_gp"] = 10
        prev = cfg.thresholds.passeurs.home_only
        cfg.thresholds.passeurs.home_only = home_only_ast
        try:
            return prod_eligible(d, market)
        finally:
            cfg.thresholds.passeurs.home_only = prev
    return eligible


def _q_phase(name: str, label: str, params_kw: dict, eligible, exec_is_prod: bool,
             src: str = "p1b_ens") -> PhaseSpec:
    """Phase q_* : prédictions walk-forward de `src` + stratégie et éligibilité données."""
    from nhl.core.betting import BetParams, select_bets
    params = BetParams.from_config(**params_kw)
    spec = p1a()
    spec.name = name
    spec.extra["reuse_preds"] = src
    spec.extra["exec_is_prod"] = exec_is_prod
    spec.eligible = eligible

    def select_and_stake(day: pd.DataFrame) -> pd.DataFrame:
        cands = [{"market": r.market, "p_model": float(r.p_model), "p_novig": r.p_novig,
                  "cote": float(r.exec_price), "game_id": r.gameId, "won": r.won, "playerId": r.playerId}
                 for r in day.itertuples(index=False)]
        bets = select_bets(cands, 100.0, params)
        return pd.DataFrame([{"date": day["date"].iloc[0], "market": b["market"], "playerId": b["playerId"],
                              "p": b["p_final"], "cote": b["cote"], "mise": b["mise"], "won": b["won"],
                              "p_novig": b["p_novig"]} for b in bets])

    spec.select_and_stake = select_and_stake
    spec.notes = (f"[{label}] prédictions `{src}`, prix {'PROD (passes = Pinnacle × pin_haircut)' if exec_is_prod else 'médiane soft × 0,94'}, "
                  f"marchés {params.markets}, w={params.blend_w}, EV ≥ {params.ev_low}, Kelly {params.kelly_fraction:.4f}, "
                  f"plafonds {params.max_game_exposure}/{params.max_daily_exposure} U.")
    return spec


def q_ref() -> PhaseSpec:
    return _q_phase("q_ref", "référence : config du 2026-10-04 telle que simulée", Q_FROZEN_0410,
                    make_eligible(False, False), exec_is_prod=False)


def q_prod() -> PhaseSpec:
    return _q_phase("q_prod", "prod réelle au 2026-10-04 : passeurs domicile seul, repli saison, prix prod",
                    Q_FROZEN_0410, make_eligible(True, True), exec_is_prod=True)


PHASES.update({"q_ref": q_ref, "q_prod": q_prod})


def q_p0() -> PhaseSpec:
    return _q_phase("q_p0", "après P0 : passeurs domicile+extérieur, GP saison depuis les logs, prix prod",
                    Q_FROZEN_0410, make_eligible(False, False), exec_is_prod=True)


PHASES["q_p0"] = q_p0


Q_P1 = dict(Q_FROZEN_0410, blend_w={"but": 0.50, "ast": 0.75})  # w réappris (log-loss val) avec le no-vig Shin


def q_p1_devig() -> PhaseSpec:
    spec = _q_phase("q_p1_devig", "P1 : no-vig Pinnacle de Shin (au lieu de multiplicatif) + w réappris",
                    Q_P1, make_eligible(False, False), exec_is_prod=True)
    spec.extra["devig"] = "shin"
    return spec


PHASES["q_p1_devig"] = q_p1_devig


def _q_model_phase(name: str, label: str, **model_kw) -> PhaseSpec:
    """Variante de MODÈLE (walk-forward complet), stratégie et prix de q_p1 (Shin, w 0,50/0,75)."""
    from nhl.core.ensemble_model import TemporalCalibratedGBM
    spec = _q_phase(name, label, Q_P1, make_eligible(False, False), exec_is_prod=True)
    spec.extra.pop("reuse_preds", None)
    spec.extra["devig"] = "shin"
    spec.model_factory = lambda m: TemporalCalibratedGBM(algos=("lgbm", "xgb", "cat"), calib_frac=0.15, **model_kw)
    return spec


def q_p1_ref() -> PhaseSpec:
    return _q_model_phase("q_p1_ref", "référence modèle : walk-forward de l'ensemble actuel (contrôle de reproductibilité)")


def q_p2_refit() -> PhaseSpec:
    return _q_model_phase("q_p2_refit", "P2 : arbres ré-entraînés sur 100 % des lignes après calibration",
                          refit_full=True)


def q_p2_split() -> PhaseSpec:
    return _q_model_phase("q_p2_split", "P2 : refit + poids et isotonique sur deux moitiés du bloc de calibration",
                          refit_full=True, split_calib=True)


PHASES.update({"q_p1_ref": q_p1_ref, "q_p2_refit": q_p2_refit, "q_p2_split": q_p2_split})


def q_p2() -> PhaseSpec:
    """P2 : refit_full et split_calib rejetés (règle a priori) ; journalisation sans effet sur les paris."""
    spec = q_p1_devig()
    spec.name = "q_p2"
    spec.notes = "[après P2] modèle inchangé (refit_full / split_calib rejetés), journalisation du marché sans effet. " + spec.notes
    return spec


def q_p3() -> PhaseSpec:
    """P3 : config de prod lue dans settings.toml (doit être identique à q_p2 : non-régression)."""
    from nhl.config.settings import cfg
    spec = _q_phase("q_p3", "après P3 : stratégie lue dans settings.toml [betting] (non-régression)",
                    {}, make_eligible(cfg.thresholds.passeurs.home_only, False), exec_is_prod=True)
    spec.extra["devig"] = cfg.betting.devig_method
    return spec


PHASES.update({"q_p2": q_p2, "q_p3": q_p3})


def q_winamax() -> PhaseSpec:
    """Config de prod après calibration du prix Winamax (exec_haircut 1,078, pin_haircut 1,00).

    Les phases q_* précédentes ont été calculées avec 0,94 / 0,90 (décotes lues dans le TOML
    au moment du calcul) : les rejouer aujourd'hui donnerait les chiffres calibrés.
    """
    from nhl.config.settings import cfg
    spec = _q_phase("q_winamax", "prix Winamax calibré sur 15 matchs (1,078 × médiane US ; = Pinnacle aux passes)",
                    {}, make_eligible(cfg.thresholds.passeurs.home_only, False), exec_is_prod=True)
    spec.extra["devig"] = cfg.betting.devig_method
    return spec


PHASES["q_winamax"] = q_winamax


def q_winamax_but() -> PhaseSpec:
    """Scénario (non adopté) : prix Winamax calibré, marché buteur seul."""
    from nhl.config.settings import cfg
    spec = _q_phase("q_winamax_but", "scénario : prix Winamax calibré, buteur seul (passeur à edge Pinnacle négatif)",
                    {"markets": ("but",)}, make_eligible(cfg.thresholds.passeurs.home_only, False), exec_is_prod=True)
    spec.extra["devig"] = cfg.betting.devig_method
    return spec


PHASES["q_winamax_but"] = q_winamax_but


def q_final() -> PhaseSpec:
    """Config de prod retenue le 2026-10-04 : « Équilibré, 1 pari / match » (lue dans settings.toml)."""
    from nhl.config.settings import cfg
    spec = _q_phase("q_final", "config retenue : Équilibré, 1 pari / match (EV ≥ 8 %, w 0,65 / 0,90)",
                    {}, make_eligible(cfg.thresholds.passeurs.home_only, False), exec_is_prod=True)
    spec.extra["devig"] = cfg.betting.devig_method
    return spec


PHASES["q_final"] = q_final
