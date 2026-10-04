"""Audit du 2026-10-04, phase P0 : correctifs bloquants (un test par bug corrigé)."""
import importlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from test_features_parity import _synthetic_logs


# ── P0-1 : historique tronqué = aucune inférence ─────────────────────────────
def test_check_history_rejects_truncated_logs():
    from nhl.core.inference import InsufficientHistoryError, check_history
    with pytest.raises(InsufficientHistoryError):
        check_history(pd.DataFrame({"gameDate": pd.to_datetime(["2025-10-07", "2026-01-10"])}))
    with pytest.raises(InsufficientHistoryError):
        check_history(pd.DataFrame({"gameDate": pd.to_datetime([])}))
    check_history(pd.DataFrame({"gameDate": pd.to_datetime(["2008-10-04", "2026-01-10"])}))


def test_engine_refresh_refuses_truncated_history(monkeypatch):
    import nhl.core.inference as inf
    import nhl.scripts.combine_season_data as comb
    monkeypatch.setattr(comb, "ensure_combined", lambda: None)
    monkeypatch.setattr(inf, "load_all_gamelogs", lambda: _synthetic_logs())  # commence en 2023
    eng = inf.FeatureEngine()
    with pytest.raises(inf.InsufficientHistoryError):
        eng.refresh(collect=False)
    assert eng.logs is None  # rien n'est servi


# ── P0-2 : gate du retrain évalué hors échantillon ──────────────────────────
def test_gate_rows_exclude_current_model_training_period():
    from nhl.scripts.train_models import gate_rows
    hold = pd.DataFrame({"date": pd.date_range("2026-03-01", periods=60, freq="D")})
    rows = gate_rows(hold, "2026-04-16")
    assert rows["date"].min() > pd.Timestamp("2026-04-16")
    assert len(rows) == 13  # du 17 au 29 avril
    assert gate_rows(hold, None).empty


def test_gate_decision():
    from nhl.scripts.train_models import gate_decision
    assert gate_decision(0.50, 0.51, 5000, False)[0] is True
    assert gate_decision(0.52, 0.51, 5000, False)[0] is False
    ok, why = gate_decision(0.40, None, 120, False)  # pas assez de lignes : on garde l'ancien
    assert ok is False and "non concluant" in why
    assert gate_decision(0.60, 0.51, 5000, True)[0] is True


# ── P0-3 : events de cotes filtrés par date et par affiche ──────────────────
def _ev(i, home, away, start):
    return {"id": i, "home_team": home, "away_team": away, "commence_time": start.strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_select_events_ignores_next_day_back_to_back():
    from shared.odds_api import nhl_team_key, select_events
    now = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
    events = [
        _ev("tonight", "Boston Bruins", "Toronto Maple Leafs", now + timedelta(hours=1)),
        _ev("tomorrow", "Boston Bruins", "Montréal Canadiens", now + timedelta(hours=25)),
        _ev("other", "Ottawa Senators", "Buffalo Sabres", now + timedelta(hours=1)),
    ]
    ids = select_events(events, ["Boston Bruins"], [("Boston Bruins", "Toronto Maple Leafs")],
                        now=now, team_key=nhl_team_key())
    assert ids == ["tonight"]
    # Sans affiches : filtre par équipe, mais toujours limité à la soirée
    assert select_events(events, ["Boston Bruins"], None, now=now) == ["tonight"]


def test_select_events_handles_api_team_aliases():
    from shared.odds_api import nhl_team_key, select_events
    now = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
    events = [_ev("a", "Montréal Canadiens", "St Louis Blues", now + timedelta(hours=1)),
              _ev("b", "Utah Mammoth", "Columbus Blue Jackets", now + timedelta(hours=2))]
    games = [("Montreal Canadiens", "St. Louis Blues"), ("Utah Hockey Club", "Columbus Blue Jackets")]
    assert select_events(events, [], games, now=now, team_key=nhl_team_key()) == ["a", "b"]


# ── P0-4 : GP de la saison depuis les logs (pas de repli saison précédente) ──
def test_season_games_ignores_previous_season():
    from nhl.core.inference import FeatureEngine
    logs = _synthetic_logs()  # saisons 2023 et 2024
    eng = FeatureEngine()
    eng.logs = logs
    eng._build_name_index()
    last = logs[logs.season == 2024]["gameDate"].max()
    n24 = int(((logs.season == 2024) & (logs.playerId == 1)).sum())
    assert eng.season_games("P1", "AAA", (last + pd.Timedelta(days=1)).date().isoformat()) == n24
    # Octobre 2025 : saison 2025 sans aucun match -> 0, même si le joueur a joué l'an dernier
    assert eng.season_games("P1", "AAA", "2025-10-08") == 0


def test_home_only_passeur_aligned_with_simulation():
    from nhl.config.settings import cfg
    assert cfg.thresholds.passeurs.home_only is False


# ── P0-5 : joueur non aligné = pari annulé ; pick_id buteur ≠ passeur ───────
@pytest.fixture
def dbs(tmp_path, monkeypatch):
    import nhl.core.database as db
    import nhl.core.updater as upd
    from shared.portfolio import Portfolio
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    pf = Portfolio(str(tmp_path / "pf.db"))
    monkeypatch.setattr(upd, "portfolio", pf)
    return db, upd, pf


def test_scratched_player_is_voided(dbs, monkeypatch):
    db, upd, pf = dbs
    pid_play = db.insert_pick("picks", {"date": "2026-10-10", "joueur": "Joue Bien", "equipe": "BOS",
                                        "verdict": "BUTEUR", "cote": 3.0, "mise": 1.0, "player_id": 11})
    pid_scr = db.insert_pick("picks", {"date": "2026-10-10", "joueur": "Pas Aligne", "equipe": "BOS",
                                       "verdict": "BUTEUR", "cote": 3.0, "mise": 1.0, "player_id": 22})
    pf.log_bet("nhl", "Joue Bien", "BUTEUR", 3.0, 1.0, pid_play)
    pf.log_bet("nhl", "Pas Aligne", "BUTEUR", 3.0, 1.0, pid_scr)
    box = {"BOS": {"by_id": {11: {"goals": 1, "assists": 0, "points": 1, "shots": 3}},
                   "by_name": {"J. Bien": {"goals": 1, "assists": 0, "points": 1, "shots": 3}}}}
    monkeypatch.setattr(upd, "fetch_final_boxscores", lambda d: box)
    assert upd.update_pending_picks() == 2
    conn = db.get_connection()
    rows = dict(conn.execute("SELECT player_id, COALESCE(statut, but) FROM picks").fetchall())
    conn.close()
    assert rows == {11: 1, 22: "void"}
    assert pf.get_pending_exposure() == 0          # plus d'exposition fantôme
    assert pf.get_balance() == pytest.approx(102.0)  # +2 U gagnés, 0 sur le void
    assert upd.update_pending_picks() == 0          # le void n'est plus re-interrogé


def test_portfolio_resolution_distinguishes_markets(tmp_path):
    from shared.portfolio import Portfolio
    pf = Portfolio(str(tmp_path / "pf.db"))
    pf.log_bet("nhl", "A", "BUTEUR", 4.0, 1.0, pick_id=7)
    pf.log_bet("nhl", "B", "PASSEUR", 2.0, 1.0, pick_id=7)  # même id, autre table
    pf.resolve_bet_by_pick_id(7, "nhl", won=True, market="PASSEUR")
    hist = {h["player_name"]: h["status"] for h in pf.get_history(5)}
    assert hist == {"A": "PENDING", "B": "WIN"}


def test_void_is_not_a_loss(tmp_path):
    from shared.portfolio import Portfolio
    pf = Portfolio(str(tmp_path / "pf.db"))
    bid = pf.log_bet("nhl", "A", "BUTEUR", 4.0, 1.0, pick_id=1)
    pf.resolve_bet(bid, won=False, void=True)
    pnl = pf.get_daily_pnl()
    assert pnl["nb_lost"] == 0 and pf.get_balance() == 100.0


# ── P0-6 : import absolu de l'updater ───────────────────────────────────────
def test_updater_uses_absolute_imports():
    upd = importlib.import_module("nhl.core.updater")
    assert upd.get_connection.__module__ == "nhl.core.database"
