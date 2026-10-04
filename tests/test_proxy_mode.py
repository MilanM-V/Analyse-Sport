"""Mode proxy : cote seuil, prix proxy, commandes /pris et /skip, affichage Telegram."""
import sqlite3

import pytest

from nhl.core import database
from nhl.core.betting import BetParams, ev_threshold, min_odds, select_bets
from nhl.core import services
from nhl.core.formatter import _pick_line, format_match_time
from nhl.core.services import handle_pick_command, parse_odds_reply, pick_card_text
from shared.odds_api import apply_proxy


def _params():
    return BetParams(blend_w={"but": 0.5, "ast": 0.5}, cote_min={"but": 1.5, "ast": 1.5},
                     cote_max={"but": 20.0, "ast": 20.0}, ev_low=0.04, ev_mid=0.04, ev_high=0.04,
                     low_cut=2.0, mid_cut=3.5, no_pinnacle_extra_ev=0.05, kelly_fraction=1 / 6,
                     min_stake=0.5, max_stake={"but": 1.5, "ast": 2.0}, max_game_exposure=5.0,
                     max_daily_exposure=30.0)


# ── Cote seuil ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("p,thr", [(0.30, 0.04), (0.45, 0.04), (0.123, 0.09)])
def test_min_odds_is_smallest_value_odds(p, thr):
    c = min_odds(p, thr)
    assert p * c - 1 >= thr - 1e-12              # value à la cote affichée
    assert p * (c - 0.01) - 1 < thr              # plus value un centième en dessous


def test_select_bets_exposes_threshold_odds():
    params = _params()
    cands = [{"market": "but", "p_model": 0.40, "p_novig": 0.36, "cote": 3.2, "game_id": 1}]
    (b,) = select_bets(cands, 100.0, params)
    assert b["cote_seuil"] == min_odds(b["p_final"], ev_threshold(3.2, params, True))
    assert b["cote_seuil"] <= b["cote"]          # le proxy est au-dessus du seuil


# ── Prix proxy ──────────────────────────────────────────────────────────────
def test_proxy_uses_soft_median():
    d = {"soft": [3.0, 2.6, 3.4, 2.8], "pin_yes": 3.1}
    apply_proxy(d, 0.94, 0.90)
    assert d["soft_median"] == pytest.approx(2.9)
    assert d["price"] == pytest.approx(2.9 * 0.94, abs=1e-3)
    assert d["price_source"] == "soft"


def test_proxy_falls_back_to_pinnacle():
    d = {"pin_yes": 2.5, "pin_no": 1.5}
    apply_proxy(d, 0.94, 0.90)
    assert d["price"] == pytest.approx(2.25) and d["price_source"] == "pinnacle"


def test_proxy_without_any_price():
    d = {}
    apply_proxy(d, 0.94, 0.90)
    assert "price" not in d


# ── /pris et /skip ──────────────────────────────────────────────────────────
@pytest.fixture
def pick_db(tmp_path, monkeypatch):
    path = tmp_path / "bot.db"
    conn = sqlite3.connect(path)
    for t in ("picks", "picks_assists"):
        conn.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, date TEXT, joueur TEXT, mise REAL, "
                     "cote_seuil REAL, cote_reelle REAL, book_reel TEXT, pris INTEGER)")
    conn.execute("INSERT INTO picks VALUES (12, '2026-10-10', 'Cole Caufield', 1.0, 2.85, NULL, NULL, NULL)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(database, "DB_PATH", str(path))
    return path


def _row(path):
    conn = sqlite3.connect(path)
    r = conn.execute("SELECT pris, cote_reelle, book_reel FROM picks WHERE id = 12").fetchone()
    conn.close()
    return r


def test_pris_records_real_odds(pick_db):
    msg = handle_pick_command(["B12", "3,05", "Betclic"], taken=True)
    assert msg.startswith("✅") and "Cole Caufield" in msg
    assert _row(pick_db) == (1, 3.05, "betclic")


def test_pris_under_threshold_warns(pick_db):
    msg = handle_pick_command(["#b12", "2.70"], taken=True)
    assert "SOUS la cote seuil" in msg
    assert _row(pick_db)[:2] == (1, 2.70)


def test_skip_and_bad_refs(pick_db):
    assert handle_pick_command(["B12"], taken=False).startswith("⏭️")
    assert _row(pick_db)[0] == 0
    assert "introuvable" in handle_pick_command(["A99", "2.0"], taken=True)
    assert "invalide" in handle_pick_command(["X1", "2.0"], taken=True)
    assert handle_pick_command(["B12"], taken=True).startswith("Usage")


# ── Affichage Telegram ──────────────────────────────────────────────────────
def test_pick_line_shows_only_threshold():
    """Canal public : cote seuil et mise, ni cote proxy ni référence."""
    line = _pick_line({"Cote": 3.10, "Bookmaker": "Proxy US", "CoteSeuil": 2.85, "Mise": "1.0 U", "Ref": "B12"})
    assert "à prendre si cote &gt; <b>2.85</b>" in line
    assert "3.10" not in line and "Proxy" not in line and "B12" not in line


@pytest.mark.parametrize("raw,expected", [("04.10. 20:00", "20h00"), ("12.01. 01:30", "01h30"), ("TBD", "TBD")])
def test_format_match_time(raw, expected):
    assert format_match_time(raw) == expected


# ── Fiches privées admin (boutons Pris / Skip) ──────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("3.05", (3.05, None)), ("3,05 Betclic", (3.05, "betclic")), ("  2.5   winamax ", (2.5, "winamax")),
    ("abc", None), ("0.9", None), ("", None),
])
def test_parse_odds_reply(text, expected):
    assert parse_odds_reply(text) == expected


PICK = {"Joueur": "Kirill Kaprizov", "Ref": "B12", "CoteSeuil": 2.89, "Mise": "1.0 U", "IsHome": True,
        "Match": "Minnesota Wild vs Boston Bruins", "Heure": "05.10. 02:20"}


def test_pick_card_text_has_match_context():
    txt = pick_card_text(PICK, "but")
    for part in ("Kirill Kaprizov", "Buteur", "\U0001f3e0", "Minnesota Wild vs Boston Bruins", "02h20",
                 "2.89", "1.0 U", "B12"):
        assert part in txt


def test_send_pick_card_payload(monkeypatch):
    sent = {}
    monkeypatch.setenv("TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", "42")
    monkeypatch.setattr(services, "safe_post", lambda url, json, timeout: sent.update(url=url, json=json))
    services.TelegramNotifier().send_pick_card(PICK, "but")
    assert sent["json"]["chat_id"] == "42"
    buttons = sent["json"]["reply_markup"]["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == ["pick:take:B12", "pick:skip:B12"]
    assert [b["text"] for b in buttons] == ["✅ Pris", "⏭️ Skip"]
