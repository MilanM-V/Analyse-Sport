"""Envoi des picks en deux temps (2026-10-05) : aperçu sur compos probables, puis picks confirmés.

Aperçu dès que les compos probables d'un créneau sont publiées ; picks confirmés quand les deux
gardiens de chaque match sont « Confirmed » sur RotoWire, ou au plus tard 17 min avant le match.
"""
from datetime import timedelta

from bs4 import BeautifulSoup

from nhl.core import scraper
from nhl.core.bot_logic import PREVIEW_BANNER, NhlBot, plan_wave_sends
from shared.utils import paris_now


# ── RotoWire : statut des gardiens ──────────────────────────────────────────
def _team_ul(side: str, goalie: str, status: str, players: list) -> str:
    items = "".join(f'<li class="lineup__player"><a>{p}</a></li>' for p in players)
    return (f'<ul class="lineup__list {side}">'
            f'<li class="lineup__player-highlight"><div class="lineup__player-highlight-name"><a>{goalie}</a></div>'
            f'<div class="flex-row align-center is-{status}">{status.title()}</div></li>'
            f'<li class="lineup__title">POWER PLAY #1</li>{items}</ul>')


def _rotowire(away_status: str, home_status: str) -> BeautifulSoup:
    html = ('<div class="lineup is-nhl"><div class="lineup__mteam is-visit">Mammoth</div>'
            '<div class="lineup__mteam is-home">Rangers</div>'
            + _team_ul("is-visit", "Karel Vejmelka", away_status, ["A B", "C D", "E F", "G H", "I J"])
            + _team_ul("is-home", "Igor Shesterkin", home_status, ["K L", "M N", "O P", "Q R", "S T"])
            + "</div>")
    return BeautifulSoup(html, "html.parser")


def test_lineup_reports_goalie_confirmation(monkeypatch):
    monkeypatch.setattr(scraper, "_get_rotowire_soup", lambda: _rotowire("confirmed", "expected"))
    compo = scraper.get_lineups("1", "New York Rangers", "Utah Mammoth")
    assert compo["goalDom"] == "Igor Shesterkin" and compo["goalext"] == "Karel Vejmelka"
    assert (compo["goalDomConfirmed"], compo["goalextConfirmed"], compo["confirmed"]) == (False, True, False)
    monkeypatch.setattr(scraper, "_get_rotowire_soup", lambda: _rotowire("confirmed", "confirmed"))
    assert scraper.get_lineups("1", "New York Rangers", "Utah Mammoth")["confirmed"] is True


# ── Répartition aperçu / confirmé ───────────────────────────────────────────
def _plan(waves, complete=(), forced=(), confirmed=(), previewed=()):
    return plan_wave_sends(waves, is_complete=lambda w: w[0] in complete, is_forced=lambda w: w[0] in forced,
                           is_confirmed=lambda m: m in confirmed, previewed=set(previewed))


def test_plan_wave_sends():
    waves = [["a", "b"], ["c"], ["d"]]
    # compos probables publiées : aperçu ; créneau incomplet : rien
    assert _plan(waves, complete={"a", "c"}) == (["a", "b", "c"], [])
    # aperçu déjà parti : pas de second aperçu ; un nouveau match du créneau a le sien
    assert _plan([["a", "b", "e"]], complete={"a"}, previewed={"a", "b"}) == (["e"], [])
    # tous les gardiens confirmés : envoi confirmé ; un seul match confirmé : on attend
    assert _plan(waves, complete={"a", "c"}, confirmed={"a", "b", "c"}) == ([], ["a", "b", "c"])
    assert _plan([["a", "b"]], complete={"a"}, confirmed={"a"}, previewed={"a", "b"}) == ([], [])
    # match imminent : envoi confirmé même sans compo complète ni gardien confirmé
    assert _plan(waves, forced={"d"}) == ([], ["d"])


# ── Scénario d'une soirée ───────────────────────────────────────────────────
def _bot(tmp_path, monkeypatch, calls):
    bot = object.__new__(NhlBot)  # sans __init__ : ni Telegram, ni base, ni modèles
    bot.matchs_envoyes, bot.apercus_envoyes, bot.vagues_envoyees = set(), set(), set()
    bot.compos_en_memoire = {}
    bot.ecart_max_vague_min, bot.force_envoi_min_avant = 5, 17
    bot.sent_state_path = str(tmp_path / "sent_matches.json")
    monkeypatch.setattr(NhlBot, "run_analysis_and_send",
                        lambda self, ids, label, preview=False: calls.append((sorted(ids), label, preview)))
    return bot


def _matches(minutes_ahead: int, ids=("1", "2")):
    t = (paris_now() + timedelta(minutes=minutes_ahead)).strftime("%d.%m. %H:%M")
    return [{"id": i, "time": t, "home": "Home", "away": "Away"} for i in ids]


def test_preview_then_confirmed_picks(tmp_path, monkeypatch):
    calls = []
    bot = _bot(tmp_path, monkeypatch, calls)
    matches = _matches(180)
    bot.compos_en_memoire = {m["id"]: {"match_info": m, "compo": {"confirmed": False}} for m in matches}

    bot.evaluate_waves(matches)
    assert calls == [(["1", "2"], "APERÇU (2 matchs)", True)]
    bot.evaluate_waves(matches)                       # scan suivant : pas de second aperçu
    bot.compos_en_memoire["1"]["compo"]["confirmed"] = True
    bot.evaluate_waves(matches)                       # un seul match du créneau confirmé : on attend
    assert len(calls) == 1

    bot.compos_en_memoire["2"]["compo"]["confirmed"] = True
    bot.evaluate_waves(matches)
    assert calls[-1] == (["1", "2"], "PICKS CONFIRMÉS (2 matchs)", False)
    bot.evaluate_waves(matches)
    assert len(calls) == 2                            # plus rien à envoyer pour ce créneau


def test_imminent_match_is_sent_confirmed_without_preview(tmp_path, monkeypatch):
    calls = []
    bot = _bot(tmp_path, monkeypatch, calls)
    matches = _matches(10, ids=("3",))
    bot.compos_en_memoire = {"3": {"match_info": matches[0], "compo": {"confirmed": False}}}
    bot.evaluate_waves(matches)
    assert calls == [(["3"], "PICKS CONFIRMÉS (1 match)", False)]


def test_sent_state_survives_a_restart(tmp_path, monkeypatch):
    calls = []
    bot = _bot(tmp_path, monkeypatch, calls)
    bot.apercus_envoyes, bot.matchs_envoyes = {"1", "2"}, {"2"}
    bot._save_sent_matches()
    fresh = _bot(tmp_path, monkeypatch, calls)  # redémarrage par le watchdog
    fresh._load_sent_matches()
    assert fresh.apercus_envoyes == {"1", "2"} and fresh.matchs_envoyes == {"2"}


def test_preview_banner_says_picks_are_not_final():
    assert "APERÇU" in PREVIEW_BANNER and "non définitifs" in PREVIEW_BANNER and "17 min" in PREVIEW_BANNER
