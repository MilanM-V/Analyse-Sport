"""Bugs remontés par le VPS le 2026-10-04 : /pris non idempotent, « database is locked » à l'auto-résolution."""
import sqlite3

import pytest

from nhl.config.settings import cfg


@pytest.fixture
def real_mode(tmp_path, monkeypatch):
    """Base du bot et portefeuille temporaires, mode réel (paper_trading = False)."""
    import nhl.core.database as db
    import shared.portfolio as pf
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    monkeypatch.setattr(pf, "_PORTFOLIO_DB", str(tmp_path / "portfolio.db"))
    monkeypatch.setattr(pf.Portfolio.__init__, "__defaults__", (str(tmp_path / "portfolio.db"),))
    monkeypatch.setattr(cfg.mode, "paper_trading", False)
    pf.Portfolio(str(tmp_path / "portfolio.db"))  # crée la table
    db.init_db()
    but = db.insert_pick("picks", {"date": "2026-10-10", "joueur": "Cole Caufield", "cote": 3.0, "mise": 1.0, "cote_seuil": 2.8})
    ast = db.insert_pick("picks_assists", {"date": "2026-10-10", "joueur": "Nick Suzuki", "cote": 2.5, "mise": 1.5, "cote_seuil": 2.3})
    assert but == ast == 1  # séquences d'id distinctes : même id dans les deux tables
    return str(tmp_path / "portfolio.db")


def _bets(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT player, market, cote, mise FROM portfolio WHERE sport = 'nhl' ORDER BY id").fetchall()
    finally:
        conn.close()


def test_pris_twice_keeps_one_bet_with_last_odds(real_mode):
    from nhl.core.services import handle_pick_command
    handle_pick_command(["B1", "3.05"], taken=True)
    handle_pick_command(["B1", "3.20", "betclic"], taken=True)
    assert _bets(real_mode) == [("Cole Caufield", "BUTEUR", 3.20, 1.0)]


def test_skip_after_pris_removes_the_bet(real_mode):
    from nhl.core.services import handle_pick_command
    handle_pick_command(["B1", "3.05"], taken=True)
    handle_pick_command(["B1"], taken=False)
    assert _bets(real_mode) == []


def test_scorer_and_assist_picks_with_same_id_stay_separate(real_mode):
    from nhl.core.services import handle_pick_command
    handle_pick_command(["B1", "3.05"], taken=True)
    handle_pick_command(["A1", "2.60"], taken=True)
    handle_pick_command(["A1"], taken=False)
    assert _bets(real_mode) == [("Cole Caufield", "BUTEUR", 3.05, 1.0)]


def test_under_threshold_odds_are_not_bet(real_mode):
    from nhl.core.services import handle_pick_command
    assert "SOUS la cote seuil" in handle_pick_command(["B1", "2.50"], taken=True)
    assert _bets(real_mode) == []


def test_paper_mode_never_touches_portfolio(real_mode, monkeypatch):
    from nhl.core.services import handle_pick_command
    monkeypatch.setattr(cfg.mode, "paper_trading", True)
    handle_pick_command(["B1", "3.05"], taken=True)
    assert _bets(real_mode) == []


def test_connection_uses_wal(tmp_path, monkeypatch):
    import nhl.core.database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    conn = db.get_connection()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_auto_resolution_does_not_lock_db_during_downloads(tmp_path, monkeypatch):
    """Pendant le téléchargement des boxscores, un autre job doit pouvoir écrire dans la base."""
    import nhl.core.database as db
    import nhl.core.updater as up
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "bot.db"))
    db.init_db()
    for d in ("2026-10-08", "2026-10-09"):
        db.insert_pick("picks", {"date": d, "joueur": "Cole Caufield", "equipe": "MTL", "cote": 3.0, "mise": 1.0, "player_id": 8481540})

    def fake_fetch(date_str):
        other = sqlite3.connect(db.DB_PATH, timeout=0.5)  # un autre job écrit pendant le « réseau »
        try:
            other.execute("UPDATE picks SET mise = 1.0 WHERE date = ?", (date_str,))
            other.commit()
        finally:
            other.close()
        stats = {"goals": 1 if date_str.endswith("08") else 0, "assists": 0, "points": 0}
        return {"MTL": {"by_id": {8481540: stats}, "by_name": {"Cole Caufield": stats}}}

    from shared.portfolio import Portfolio
    monkeypatch.setattr(up, "portfolio", Portfolio(str(tmp_path / "portfolio.db")))  # jamais le vrai portfolio.db
    monkeypatch.setattr(up, "fetch_final_boxscores", fake_fetch)
    assert up.update_pending_picks() == 2
    conn = db.get_connection()
    try:
        assert conn.execute("SELECT date, but FROM picks ORDER BY date").fetchall() == [("2026-10-08", 1), ("2026-10-09", 0)]
    finally:
        conn.close()
