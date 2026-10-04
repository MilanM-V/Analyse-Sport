"""Décote du prix proxy propre à chaque marché (bug corrigé le 2026-10-04 : passes surestimées de ~8 %)."""
import asyncio

import pandas as pd


def test_fetch_nhl_odds_uses_market_specific_haircut(monkeypatch):
    import nhl.core.odds as odds
    from nhl.config.settings import cfg
    seen = {}

    async def fake(sport, market, players_map, **kw):
        seen[market] = kw["proxy"]
        return {}
    monkeypatch.setattr(odds.OddsAPIClient, "fetch_odds", staticmethod(fake))
    asyncio.run(odds.fetch_nhl_odds({"A B": "BOS"}, games=[("BOS", "TOR")]))
    assert seen["player_goal_scorer_anytime"] == (cfg.betting.exec_haircut, cfg.betting.pin_haircut)
    assert seen["player_assists"] == (cfg.betting.exec_haircut_ast, cfg.betting.pin_haircut)
    assert cfg.betting.exec_haircut_ast == 1.00


def test_simulation_prices_assists_like_prod(monkeypatch):
    """Simulation = règle de la prod : médiane US × décote du marché, sinon Pinnacle."""
    from nhl.sim.version import EXEC_HAIRCUT, EXEC_HAIRCUT_AST, PIN_HAIRCUT
    from nhl.scripts.simulate_roi import add_prod_price
    p = pd.DataFrame({"market": ["but", "ast", "ast"], "soft_median": [4.0, 2.5, None],
                      "pin_yes": [3.9, 2.4, 2.6], "date": pd.to_datetime(["2024-01-01"] * 3), "playerId": [1, 2, 3]})
    out = add_prod_price(p)["prod_price"].tolist()
    assert out == [4.0 * EXEC_HAIRCUT, 2.5 * EXEC_HAIRCUT_AST, 2.6 * PIN_HAIRCUT]
