"""
nhl/dashboard.py — Dashboard NHL (Streamlit).

Lancement : streamlit run nhl/dashboard.py

Pages : le bot (performances, picks, projection), base de données complète, classement NHL,
meilleurs joueurs, résultats par soirée, calendrier, fiches équipe (effectif par poste,
statistiques, matchs) et fiches joueur (saison en cours, historique par saison, vu par le bot).

L'ancien dashboard (simulation de l'ancienne stratégie Kelly 1/8) a été remplacé le 2026-10-04 ;
le simulateur de bankroll de la stratégie actuelle est `simulateur.html`.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st  # noqa: E402

from nhl.dash import pages  # noqa: E402

st.set_page_config(page_title="NHL Dashboard", page_icon="🏒", layout="wide", initial_sidebar_state="expanded")

PAGE_TEAM = st.Page(pages.page_team, title="Équipes", icon="👥", url_path="equipes")
PAGE_PLAYER = st.Page(pages.page_player, title="Joueurs", icon="🧑", url_path="joueurs")
pages.PAGES.update(team=PAGE_TEAM, player=PAGE_PLAYER)

nav = st.navigation({
    "Bot": [st.Page(pages.page_bot, title="Performances & picks", icon="🏒", default=True),
            st.Page(pages.page_db, title="Base de données", icon="🗄️", url_path="base")],
    "NHL": [st.Page(pages.page_standings, title="Classement", icon="🏆", url_path="classement"),
            st.Page(pages.page_leaders, title="Meilleurs joueurs", icon="⭐", url_path="leaders"),
            st.Page(pages.page_results, title="Résultats par soirée", icon="📅", url_path="resultats"),
            st.Page(pages.page_calendar, title="Calendrier", icon="🗓️", url_path="calendrier"),
            PAGE_TEAM, PAGE_PLAYER],
    "Infos": [st.Page(pages.page_about, title="À propos", icon="ℹ️", url_path="a-propos")],
})
nav.run()
