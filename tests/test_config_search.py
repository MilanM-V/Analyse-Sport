"""Recherche de configuration : option « N paris max par match », règles de sélection, reproductibilité."""
import os

import pandas as pd
import pytest

from nhl.core.betting import BetParams, select_bets


def _params(**kw):
    base = dict(blend_w={"but": 0.5, "ast": 0.5}, cote_min={"but": 1.5, "ast": 1.5},
                cote_max={"but": 20.0, "ast": 20.0}, ev_low=0.04, ev_mid=0.04, ev_high=0.04,
                low_cut=2.0, mid_cut=3.5, no_pinnacle_extra_ev=0.05, kelly_fraction=1 / 6,
                min_stake=0.5, max_stake={"but": 1.5, "ast": 2.0}, max_game_exposure=5.0,
                max_daily_exposure=30.0)
    base.update(kw)
    return BetParams(**base)


def test_max_bets_per_game_keeps_best_ev():
    cands = [{"market": "but", "p_model": p, "p_novig": p, "cote": 4.0, "game_id": 1} for p in (0.30, 0.40, 0.35)]
    cands.append({"market": "but", "p_model": 0.33, "p_novig": 0.33, "cote": 4.0, "game_id": 2})
    unlimited = select_bets(cands, 100.0, _params())
    one = select_bets(cands, 100.0, _params(max_bets_per_game=1))
    assert len(unlimited) == 4
    assert sorted((b["game_id"], b["p_model"]) for b in one) == [(1, 0.40), (2, 0.33)]


def test_per_game_limit_defaults_to_unlimited():
    # Valeur par défaut du code (la prod la fixe à 1 dans settings.toml)
    assert _params().max_bets_per_game == 0


def test_scenario_rules_on_toy_grid():
    from nhl.scripts.search_config import select_scenarios
    g = pd.DataFrame([
        # clé, marchés, n, gain/saison, ROI, DD, sharpe, IC bas
        ("a", "but+ast", 800, 150.0, 0.12, 25.0, 0.10, 5.0),   # meilleur gain, DD > 20 -> agressif
        ("b", "but+ast", 600, 120.0, 0.14, 18.0, 0.12, 5.0),   # équilibré
        ("c", "but+ast", 300, 60.0, 0.30, 9.0, 0.20, 2.0),     # prudent (meilleur sharpe, DD ≤ 15)
        ("d", "but", 400, 70.0, 0.20, 16.0, 0.11, 1.0),        # buteur seul
        ("e", "but+ast", 100, 500.0, 0.90, 5.0, 0.90, 50.0),   # trop peu de paris : exclu
        ("f", "but+ast", 900, 400.0, 0.30, 5.0, 0.80, -50.0),  # IC trop bas : exclu
    ], columns=["key", "markets", "val_n", "val_profit_season", "val_roi", "val_max_dd", "val_sharpe_night",
                "val_profit_ci_lo"])
    assert select_scenarios(g) == {"prudent": "c", "equilibre": "b", "agressif": "a", "buteur": "d"}


PREDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nhl", "reports", "preds_p1b_ens.parquet")


@pytest.mark.skipif(not os.path.exists(PREDS), reason="prédictions walk-forward absentes (fichiers dérivés, hors git)")
def test_current_config_reproduces_search_row():
    """La config de settings.toml redonne exactement sa ligne de config_search.csv."""
    from nhl.scripts.search_config import GRID_CSV, current_config, day_candidates, load_engine, run_config
    from nhl.scripts.simulate_roi import VAL_END
    cfg = current_config()
    row = pd.read_csv(GRID_CSV).set_index("key").loc[cfg.key()]
    b = run_config(day_candidates(load_engine(cfg.engine)), cfg)
    val, ctl = b[b["date"] < VAL_END], b[b["date"] >= VAL_END]
    assert (len(val), len(ctl)) == (row["val_n"], row["ctl_n"])
    assert round(val["profit"].sum(), 6) == round(row["val_profit"], 6)


def test_prod_config_is_balanced_one_per_game():
    """Choix du 2026-10-04 : « Équilibré, 1 pari / match », mode proxy (cote seuil) conservé."""
    from nhl.config.settings import cfg
    p = BetParams.from_config()
    assert p.max_bets_per_game == 1 and p.ev_mid == 0.08 and p.blend_w == {"but": 0.65, "ast": 0.90}
    assert cfg.betting.exec_mode == "proxy" and cfg.mode.paper_trading is True
