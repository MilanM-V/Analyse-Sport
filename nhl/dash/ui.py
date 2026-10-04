"""
dash/ui.py — Éléments visuels communs du dashboard (thème, cartes KPI, graphiques Plotly, cache API).
"""
from typing import Any, Dict, Optional

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from nhl.dash import api

ACCENT = "#3B82F6"
GREEN = "#22C55E"
RED = "#EF4444"
AMBER = "#F59E0B"
PALETTE = [ACCENT, "#A855F7", GREEN, AMBER, "#06B6D4", RED, "#EC4899", "#84CC16"]

CSS = """
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  .kpi {border-radius: 14px; padding: 16px 18px; background: var(--secondary-background-color);
        border: 1px solid rgba(128,128,128,.18); height: 100%;}
  .kpi .l {font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; opacity: .7;}
  .kpi .v {font-size: 1.75rem; font-weight: 700; margin-top: 4px; line-height: 1.15;}
  .kpi .s {font-size: .82rem; opacity: .7; margin-top: 4px;}
  .pos {color: #22C55E;} .neg {color: #EF4444;} .warn {color: #F59E0B;}
  .hero {display: flex; gap: 22px; align-items: center; margin-bottom: 6px;}
  .hero img {border-radius: 14px; background: var(--secondary-background-color);}
  .hero h1 {margin: 0; font-size: 2rem;}
  .hero .meta {opacity: .75; font-size: .95rem;}
  .chip {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem;
         background: rgba(59,130,246,.15); color: #3B82F6; margin-right: 6px;}
  div[data-testid="stDataFrame"] {border-radius: 12px;}
</style>
"""


def setup(title: str) -> None:
    """Thème Plotly + CSS, à appeler en tête de chaque page."""
    pio.templates.default = "plotly_white"
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)


def kpi(col: Any, label: str, value: str, sub: str = "", tone: Optional[str] = None) -> None:
    """Carte KPI (tone : 'pos', 'neg', 'warn' ou None)."""
    cls = f"v {tone}" if tone else "v"
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="{cls}">{value}</div>'
                 f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)


def img(col: Any, url: Any, width: int) -> None:
    """Image distante ; rien si l'API n'a pas fourni d'URL (évite une erreur Streamlit)."""
    if isinstance(url, str) and url.startswith("http"):
        col.image(url, width=width)


def tone(x: float) -> Optional[str]:
    """Couleur d'un nombre signé."""
    if x is None or x != x:
        return None
    return "pos" if x > 0 else ("neg" if x < 0 else None)


def fmt_u(x: float) -> str:
    return "–" if x is None or x != x else f"{x:+.1f} U"


def fmt_pct(x: float) -> str:
    return "–" if x is None or x != x else f"{x * 100:+.1f} %"


def style_fig(fig: go.Figure, height: int = 380) -> go.Figure:
    """Mise en forme commune des graphiques."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=60, b=10), colorway=PALETTE,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=None),
                      font=dict(size=13), title=dict(x=0, xanchor="left", y=0.98, yanchor="top"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)")
    return fig


@st.cache_data(ttl=600, show_spinner="Chargement des données NHL…")
def nhl(path: str) -> Dict[str, Any]:
    """Appel API NHL mis en cache 10 minutes."""
    return api.get_json(path)


def nhl_safe(path: str) -> Optional[Dict[str, Any]]:
    """Comme `nhl`, mais affiche une erreur lisible au lieu de planter la page."""
    try:
        return nhl(path)
    except api.NHLApiError as e:
        st.error(f"Données NHL indisponibles : {e}")
        return None
