"""Extraction des pages Winamax sauvegardées et calibration du prix (2026-10-04)."""
import glob
import os

import pytest

from nhl.scripts.parse_winamax_pages import PAGES_DIR, clean_player, parse_goalscorer, parse_ladder, parse_page


def test_clean_player_formats():
    assert clean_player("Michaels, Owen") == "Owen Michaels"
    assert clean_player("Elias Pettersson (1998)") == "Elias Pettersson"
    assert clean_player("Auston Matthews") == "Auston Matthews"


def test_goalscorer_section_stops_at_repeated_name():
    # Une seconde liste sans titre (autre marché) suit parfois la section buteur
    lines = ["Buteur", "?", "i", "A Un", "40%", "2,00", "B Deux", "5%", "3,50",
             "A Un", "0%", "1,58", "B Deux", "0%", "2,15"]
    assert parse_goalscorer(lines) == [("A Un", 2.0), ("B Deux", 3.5)]


def test_ladder_reads_both_teams():
    lines = ["Passes décisives du joueur (paliers)", "?", "i", "1 ou plus", "2 ou plus", "3 ou plus",
             "Home Team", "A Un", "2,15", "26%", "6,25", "8%", "28", "0%", "Moins de sélections",
             "Away Team", "B Deux", "1,95", "3%", "5,10", "0%", "Moins de sélections", "Autre section", "?"]
    assert parse_ladder(lines, "Passes décisives du joueur", ("Home Team", "Away Team")) == [
        ("Home Team", "A Un", 2.15), ("Away Team", "B Deux", 1.95)]


PAGES = sorted(glob.glob(os.path.join(PAGES_DIR, "*.htm")))


@pytest.mark.skipif(not PAGES, reason="pages Winamax privées absentes (dossier ignoré par git)")
def test_real_page_known_odds():
    page = next(pg for pg in map(parse_page, PAGES) if pg["home"].startswith("Toronto"))
    rows = {(m, n): o for m, _, n, o in page["rows"]}
    assert rows[("but", "Auston Matthews")] == 2.75
    assert rows[("ast", "William Nylander")] == 2.15
    assert 30 <= sum(1 for m, *_ in page["rows"] if m == "but") <= 50
