"""Dashboard Vercel : export JSON du bot (bot.json, db.json) et garde-fous du site statique."""
import json
import os
import re

import pytest

from dashboard import botdata, exporter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "dashboard")


@pytest.fixture
def bot_db(tmp_path, monkeypatch):
    import nhl.core.database as db
    path = str(tmp_path / "bot.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    rows = [("A", 3.0, 1.0, 1, "normal", 0.40), ("B", 2.5, 1.0, 0, "normal", None),
            ("C", 4.0, 0.5, 1, "early", 0.30), ("D", 3.5, 1.0, None, "normal", None)]
    for j, cote, mise, won, phase, pnv in rows:
        db.insert_pick("picks", {"date": "2026-10-10", "joueur": j, "equipe": "MTL", "adversaire": "TOR", "cote": cote,
                                 "mise": mise, "but": won, "phase": phase, "closing_p_novig": pnv,
                                 "features_json": "{}"})
    monkeypatch.setattr(botdata, "BOT_DB", path)
    monkeypatch.setattr(botdata, "PORTFOLIO_DB", str(tmp_path / "absent.db"))
    return path


def test_bot_json_splits_normal_and_discovery_picks(bot_db):
    b = exporter.get_bot_data()
    json.dumps(b, allow_nan=False)  # JSON strict : aucun NaN
    assert len(b["picks"]) == 4
    assert b["summary"]["n_picks"] == 3 and b["summary"]["gain"] == pytest.approx(2.0 - 1.0)
    assert b["summary_early"]["n_picks"] == 1 and b["summary_early"]["gain"] == pytest.approx(0.5 * 3.0)
    assert {p["phase"] for p in b["picks"]} == {"normal", "early"}
    assert b["early"]["stake_mult"] == 0.5 and b["mode"]["paper"] is True


def test_db_json_exports_every_table_without_json_columns(bot_db):
    d = exporter.get_db_data()
    json.dumps(d, allow_nan=False)
    t = d["bot_database.db"]["picks"]
    assert t["total"] == 4 and len(t["rows"]) == 4
    assert "features_json" not in t["columns"] and "phase" in t["columns"]
    assert d["portfolio.db"] == {}


def test_publish_pushes_all_dashboard_files(tmp_path, monkeypatch):
    import subprocess
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    for name, attr in (("data.json", "OUTPUT_JSON"), ("bot.json", "BOT_JSON"), ("db.json", "DB_JSON")):
        f = tmp_path / name
        f.write_text(json.dumps({"file": name}), encoding="utf-8")
        monkeypatch.setattr(exporter, attr, str(f))
    assert exporter.git_commit_and_push(repo_dir=str(tmp_path / "pub"), remote_url=str(remote)) is True
    files = subprocess.run(["git", "ls-tree", "--name-only", "dashboard-data"], cwd=str(remote),
                           capture_output=True, text=True, check=True).stdout.split()
    assert sorted(files) == ["bot.json", "data.json", "db.json"]


def _site_js() -> str:
    out = []
    for d, _, files in os.walk(os.path.join(SITE, "js")):
        out += [open(os.path.join(d, f), encoding="utf-8").read() for f in files if f.endswith(".js")]
    return "\n".join(out)


def test_site_only_uses_nhl_endpoints_without_redirect():
    # `standings/now`, `roster/X/current`, `club-stats/X/now`... répondent 307 vers api-web.nhle.com :
    # derrière le relais Vercel, le navigateur suivrait la redirection et serait bloqué (pas de CORS).
    js = _site_js()
    calls = re.findall(r"nhl\(`([^`]+)`\)", js)
    assert calls, "aucun appel à l'API NHL trouvé"
    assert not [c for c in calls if re.search(r"/(now|current)\b", c)]


def test_vercel_rewrite_and_every_route_module_exist():
    cfg = json.load(open(os.path.join(SITE, "vercel.json"), encoding="utf-8"))
    assert {"source": "/nhl/:path*", "destination": "https://api-web.nhle.com/v1/:path*"} in cfg["rewrites"]
    app = open(os.path.join(SITE, "js", "app.js"), encoding="utf-8").read()
    for mod in re.findall(r"from '\./pages/(\w+)\.js'", app):
        assert os.path.exists(os.path.join(SITE, "js", "pages", f"{mod}.js")), mod
    assert 'src="js/app.js"' in open(os.path.join(SITE, "index.html"), encoding="utf-8").read()


def test_bankroll_follows_bets_taken_and_cash_moves(bot_db, tmp_path, monkeypatch):
    """Solde = 100 U + gains résolus (règle de Portfolio.get_balance) ; en attente = exposition seulement.
    Courbe : 102 U après le pari gagné, 100 U après le perdu (baisse de 2 U), 110 U après le dépôt."""
    from shared.portfolio import Portfolio
    path = str(tmp_path / "portfolio.db")
    pf = Portfolio(path)
    won = pf.log_bet("nhl", "A", "BUTEUR", 3.0, 1.0, pick_id=1)
    lost = pf.log_bet("nhl", "B", "PASSEUR", 2.0, 2.0, pick_id=2)
    pf.log_bet("nhl", "C", "BUTEUR", 4.0, 0.5, pick_id=3)
    pf.resolve_bet(won, True)
    pf.resolve_bet(lost, False)
    pf.deposit(10.0)
    monkeypatch.setattr(botdata, "PORTFOLIO_DB", path)

    b = exporter.get_bot_data()["bankroll"]
    json.dumps(b, allow_nan=False)
    assert b["balance"] == pytest.approx(pf.get_balance()) == pytest.approx(110.0)
    assert b["pending"] == {"n": 1, "stake": 0.5}
    assert b["stats"]["gain_paris"] == pytest.approx(0.0) and b["stats"]["n_joues"] == 2
    assert b["stats"]["drawdown_max"] == pytest.approx(2.0) and b["stats"]["depots"] == 10.0
    assert [e["statut"] for e in b["events"]] == ["dépôt", "en attente", "perdu", "gagné"]
    assert len(b["daily"]) == 1 and b["daily"][0]["solde"] == pytest.approx(110.0)


def test_bankroll_without_portfolio_is_empty(bot_db):
    b = exporter.get_bot_data()["bankroll"]
    assert b["balance"] == 100.0 and b["events"] == [] and b["stats"] is None
