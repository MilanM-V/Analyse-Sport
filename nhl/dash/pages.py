"""
dash/pages.py — Pages du dashboard. Chaque fonction est une page Streamlit (st.navigation).

Navigation entre pages : l'équipe et le joueur sélectionnés sont gardés dans
st.session_state ("team", "player_id"), puis st.switch_page ouvre la fiche.
"""
import json
import os
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from nhl.dash import api, botdata, ui
from nhl.dash.ui import fmt_pct, fmt_u, kpi, style_fig, tone

PAGES = {}  # rempli par nhl/dashboard.py : {"team": st.Page, "player": st.Page}
PLURAL = {"Centre": "Centres", "Ailier gauche": "Ailiers gauches", "Ailier droit": "Ailiers droits",
          "Défenseur": "Défenseurs", "Gardien": "Gardiens"}
REPORTS = os.path.join(botdata.NHL_DIR, "reports")


def _open_team(abbrev: str) -> None:
    st.session_state["team"] = abbrev
    st.switch_page(PAGES["team"])


def _open_player(pid: int) -> None:
    st.session_state["player_id"] = int(pid)
    st.switch_page(PAGES["player"])


def _selected_row(event) -> int:
    rows = (event.selection or {}).get("rows", []) if event is not None else []
    return rows[0] if rows else -1


# ─────────────────────────────────────────────────────────────────────────────
# 1. Le bot : performances, picks, projection
# ─────────────────────────────────────────────────────────────────────────────
def page_bot() -> None:
    ui.setup("🏒 Le bot — performances")
    p = botdata.picks()
    s = botdata.summary(p) if not p.empty else None
    from nhl.config.settings import cfg
    mode = "PAPER (aucun argent réel)" if cfg.mode.paper_trading else "RÉEL"
    st.caption(f"Mode : **{mode}** · stratégie « Équilibré, 1 pari / match » · base : `{botdata.BOT_DB}`")

    c = st.columns(5)
    if s:
        kpi(c[0], "Gain net", fmt_u(s["gain"]), f"paris résolus : {s['n_joues']}", tone(s["gain"]))
        kpi(c[1], "ROI", fmt_pct(s["roi"]), f"mise totale {s['mise']:.1f} U", tone(s["roi"]))
        kpi(c[2], "Réussite", "–" if s["reussite"] != s["reussite"] else f"{s['reussite'] * 100:.0f} %",
            f"{s['en_attente']} en attente")
        min_bets = int(getattr(cfg.mode, "go_live_min_bets", 300))
        kpi(c[3], "EV de clôture", fmt_pct(s["ev_cloture"]), f"{s['n_ev_cloture']} / {min_bets} paris requis",
            tone(s["ev_cloture"]))
        kpi(c[4], "Picks envoyés", str(s["n_picks"]), "buteur + passeur")
    else:
        st.info("Aucun pick dans la base pour l'instant : les premiers arriveront quand les joueurs auront 10 matchs joués.")

    _projection()

    cum = botdata.cumulative(p) if s else None
    if cum is not None and cum["date"].nunique() >= 2:
        st.subheader("Gain cumulé")
        fig = px.line(cum, x="date", y="gain_cumule", color="marche", markers=True,
                      labels={"gain_cumule": "Gain cumulé (U)", "date": "", "marche": ""})
        fig.add_hline(y=0, line_dash="dot", opacity=.5)
        st.plotly_chart(style_fig(fig), width="stretch")

    if not p.empty:
        st.subheader("Picks")
        f1, f2, f3 = st.columns(3)
        mk = f1.multiselect("Marché", sorted(p["marche"].unique()), default=sorted(p["marche"].unique()))
        stt = f2.multiselect("Statut", sorted(p["statut"].unique()), default=sorted(p["statut"].unique()))
        q = f3.text_input("Joueur / équipe", "")
        v = p[p["marche"].isin(mk) & p["statut"].isin(stt)]
        if q:
            v = v[v["joueur"].str.contains(q, case=False, na=False) | v["equipe"].str.contains(q, case=False, na=False)]
        st.dataframe(v[["ref", "date", "marche", "joueur", "equipe", "adversaire", "cote_seuil", "cote", "mise",
                        "p_final", "statut", "profit", "ev_cloture"]],
                     column_config={"date": st.column_config.DateColumn("Date"), "ref": "Réf.", "marche": "Marché",
                                    "joueur": "Joueur", "equipe": "Équipe", "adversaire": "Adversaire",
                                    "mise": st.column_config.NumberColumn("Mise (U)", format="%.1f"), "statut": "Statut",
                                    "cote_seuil": st.column_config.NumberColumn("Cote seuil", format="%.2f"),
                                    "cote": st.column_config.NumberColumn("Cote", format="%.2f"),
                                    "p_final": st.column_config.ProgressColumn("Proba", min_value=0, max_value=1, format="%.2f"),
                                    "profit": st.column_config.NumberColumn("Gain (U)", format="%+.2f"),
                                    "ev_cloture": st.column_config.NumberColumn("EV clôture", format="%+.1%%")},
                     hide_index=True, width="stretch")
        by = (p[p["statut"].isin(["gagné", "perdu"])].groupby("marche")
              .agg(paris=("ref", "size"), gain=("profit", "sum"), mise=("mise", "sum")))
        if not by.empty:
            by["roi"] = by["gain"] / by["mise"]
            st.markdown("**Par marché** (paris résolus)")
            st.dataframe(by.reset_index(), hide_index=True, column_config={"marche": "Marché", "paris": "Paris",
                                            "gain": st.column_config.NumberColumn("Gain (U)", format="%+.1f"),
                                            "mise": st.column_config.NumberColumn("Mise (U)", format="%.1f"),
                                            "roi": st.column_config.NumberColumn("ROI", format="%+.1%%")},
                         width="stretch")


def _projection() -> None:
    """Ce que la simulation prévoit pour la config de prod (config_scenarios.json)."""
    path = os.path.join(REPORTS, "config_scenarios.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        sc = json.load(f)["scenarios"].get("actuelle")
    if not sc:
        return
    with st.expander("📈 Ce que la simulation prévoit pour une saison (config actuelle)", expanded=False):
        v, c = sc["val"], sc["ctl"]
        cols = st.columns(4)
        kpi(cols[0], "Gain / saison (2023-24)", fmt_u(v["profit_season"]), f"ROI {fmt_pct(v['roi'])}", tone(v["profit_season"]))
        kpi(cols[1], "Gain / saison (2024-25)", fmt_u(c["profit_season"]), f"ROI {fmt_pct(c['roi'])}", tone(c["profit_season"]))
        kpi(cols[2], "Pire série de pertes", f"{max(v['max_dd'], c['max_dd']):.1f} U", "drawdown maximal")
        kpi(cols[3], "Paris par match", f"{v['per_game']:.2f}", "≈ 1 match sur 2")
        st.caption("Backtest au prix Winamax calibré, Kelly 1/6, bankroll 100 U. Ce n'est pas une garantie : "
                   "seule l'EV de clôture des paris réels prouvera l'avantage. Détails : simulateur.html.")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Base de données
# ─────────────────────────────────────────────────────────────────────────────
def page_db() -> None:
    ui.setup("🗄️ Base de données")
    dbs = {"Bot (bot_database.db)": botdata.BOT_DB, "Portefeuille (portfolio.db)": botdata.PORTFOLIO_DB}
    name = st.radio("Base", list(dbs), horizontal=True)
    tables = botdata.list_tables(dbs[name])
    if not tables:
        st.warning(f"Base introuvable ou vide : `{dbs[name]}`")
        return
    t = st.selectbox("Table", list(tables), format_func=lambda x: f"{x} ({tables[x]} lignes)")
    df = botdata.read_table(t, dbs[name])
    q = st.text_input("Filtrer (texte présent dans n'importe quelle colonne)", "")
    if q:
        df = df[df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)]
    st.caption(f"{len(df)} ligne(s) · {len(df.columns)} colonne(s) · lecture seule")
    st.dataframe(df, hide_index=True, width="stretch", height=560)
    st.download_button("Télécharger en CSV", df.to_csv(index=False).encode("utf-8"), f"{t}.csv", "text/csv")
    if name.startswith("Portefeuille"):
        pf = botdata.portfolio()
        if not pf.empty:
            fig = px.line(pf, x="timestamp", y="solde", markers=True, labels={"solde": "Solde (U)", "timestamp": ""})
            st.plotly_chart(style_fig(fig, 320), width="stretch")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Classement
# ─────────────────────────────────────────────────────────────────────────────
def page_standings() -> None:
    ui.setup("🏆 Classement NHL")
    data = ui.nhl_safe("standings/now")
    if not data:
        return
    df = api.standings(data)
    view = st.radio("Vue", ["Ligue", "Conférences", "Divisions"], horizontal=True)
    cols = ["#", "logo", "Équipe", "MJ", "V", "D", "DP", "Pts", "% Pts", "BP", "BC", "Diff", "10 derniers", "Série",
            "Domicile", "Extérieur"]
    cfg = {"logo": st.column_config.ImageColumn("", width="small"),
           "% Pts": st.column_config.ProgressColumn("% Pts", min_value=0, max_value=1, format="%.3f")}
    groups = {"Ligue": [("NHL", df)], "Conférences": list(df.groupby("Conférence")),
              "Divisions": list(df.groupby("Division"))}[view]
    for gname, g in groups:
        st.subheader(gname)
        g = g.sort_values(["Pts", "% Pts"], ascending=False).reset_index(drop=True)
        g["#"] = range(1, len(g) + 1)
        ev = st.dataframe(g[cols], column_config=cfg, hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="single-row", key=f"std_{gname}")
        i = _selected_row(ev)
        if i >= 0:
            _open_team(g.iloc[i]["abbrev"])
    st.caption("Cliquez sur une ligne pour ouvrir la fiche de l'équipe.")
    d = df.sort_values(["Pts", "% Pts"])
    fig = px.bar(d, x="Pts", y="abbrev", orientation="h", color="Conférence", text="Pts",
                 labels={"abbrev": "", "Pts": "Points", "Conférence": ""}, title="Points par équipe")
    fig.update_yaxes(categoryorder="array", categoryarray=d["abbrev"].tolist())
    fig.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(style_fig(fig, 780), width="stretch")
    fig = px.scatter(df, x="BP", y="BC", text="abbrev", color="Conférence", size=df["Pts"].clip(lower=1),
                     labels={"BP": "Buts pour", "BC": "Buts contre"}, title="Attaque contre défense")
    fig.update_traces(textposition="top center")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style_fig(fig, 520), width="stretch")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Meilleurs joueurs
# ─────────────────────────────────────────────────────────────────────────────
def page_leaders() -> None:
    ui.setup("⭐ Meilleurs joueurs")
    n = st.slider("Nombre de joueurs", 5, 30, 15)
    data = ui.nhl_safe(f"skater-stats-leaders/current?categories=goals,assists,points&limit={n}")
    if not data:
        return
    tabs = st.tabs(["🎯 Buteurs", "🅰️ Passeurs", "📊 Pointeurs"])
    for tab, (cat, label) in zip(tabs, [("goals", "Buts"), ("assists", "Passes"), ("points", "Points")]):
        with tab:
            df = api.leaders(data, cat).rename(columns={"Valeur": label})
            if df.empty:
                st.info("Aucune donnée pour l'instant.")
                continue
            top = df.head(3)
            cols = st.columns(3)
            for col, (_, r) in zip(cols, top.iterrows()):
                ui.img(col, r["photo"], 110)
                col.markdown(f"**{r['Rang']}. {r['Joueur']}**  \n{r['Équipe']} · {r['Poste']} · **{r[label]} {label.lower()}**")
            d = df.assign(nom=df["Joueur"] + " (" + df["Équipe"] + ")").sort_values([label, "Rang"], ascending=[True, False])
            fig = px.bar(d, x=label, y="nom", orientation="h", text=label, labels={"nom": ""},
                         color_discrete_sequence=[ui.ACCENT])
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_yaxes(categoryorder="array", categoryarray=d["nom"].tolist())
            st.plotly_chart(style_fig(fig, max(320, 28 * len(df))), width="stretch")
            ev = st.dataframe(df[["Rang", "photo", "Joueur", "Équipe", "Poste", label]],
                              column_config={"photo": st.column_config.ImageColumn("", width="small")},
                              hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key=f"lead_{cat}")
            i = _selected_row(ev)
            if i >= 0:
                _open_player(df.iloc[i]["playerId"])
    st.caption("Cliquez sur un joueur pour ouvrir sa fiche.")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Résultats par soirée et calendrier
# ─────────────────────────────────────────────────────────────────────────────
def page_results() -> None:
    ui.setup("📅 Résultats par soirée")
    d = st.date_input("Soirée (date NHL, heure de l'Est)", value=date.today() - timedelta(days=1))
    data = ui.nhl_safe(f"score/{d.isoformat()}")
    if not data:
        return
    df = api.scores(data)
    if df.empty:
        st.info("Aucun match ce jour-là.")
        return
    p = botdata.picks()
    picks_day = p[p["date"].dt.date == d] if not p.empty else p
    for _, g in df.iterrows():
        c = st.columns([1, 3, 2, 3, 1, 6])
        ui.img(c[0], g["logo_ext"], 46)
        c[1].markdown(f"**{g['Extérieur']}**")
        sc = f"{g['Score ext.']} – {g['Score dom.']}" if pd.notna(g["Score ext."]) else "à venir"
        c[2].markdown(f"### {sc}" + (f" <small>({g['Fin']})</small>" if g["Fin"] and g["Fin"] != "REG" else ""),
                      unsafe_allow_html=True)
        c[3].markdown(f"**{g['Domicile']}**")
        ui.img(c[4], g["logo_dom"], 46)
        bets = picks_day[picks_day["equipe"].isin([g["Extérieur"], g["Domicile"]])] if not picks_day.empty else picks_day
        txt = f"Tirs {g['Tirs ext.']}–{g['Tirs dom.']}" if pd.notna(g["Tirs ext."]) else ""
        if len(bets):
            txt += " · 🎯 picks : " + ", ".join(f"{r.joueur} ({r.marche}, {r.statut})" for r in bets.itertuples())
        c[5].caption(txt + (f"  \nButeurs : {g['Buteurs']}" if g["Buteurs"] else ""))
        st.divider()


def page_calendar() -> None:
    ui.setup("🗓️ Calendrier")
    d = st.date_input("Semaine du", value=date.today())
    data = ui.nhl_safe(f"schedule/{api.week_start(d).isoformat()}")
    if not data:
        return
    df = api.schedule_week(data)
    if df.empty:
        st.info("Aucun match cette semaine.")
        return
    per_day = df.groupby("Date").size().reset_index(name="Matchs")
    fig = px.bar(per_day, x="Date", y="Matchs", text="Matchs", title="Matchs par jour")
    st.plotly_chart(style_fig(fig, 260), width="stretch")
    for day, g in df.groupby("Date"):
        st.subheader(pd.Timestamp(day).strftime("%A %d %B %Y"))
        st.dataframe(g.drop(columns=["Date", "gameId"]), hide_index=True, width="stretch")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Équipes
# ─────────────────────────────────────────────────────────────────────────────
def page_team() -> None:
    ui.setup("👥 Équipes")
    teams = api.TEAMS
    cur = st.session_state.get("team", "MTL")
    team = st.selectbox("Équipe", teams, index=teams.index(cur) if cur in teams else 0)
    st.session_state["team"] = team

    std = ui.nhl_safe("standings/now")
    row = None
    if std:
        s = api.standings(std)
        m = s[s["abbrev"] == team]
        row = m.iloc[0] if len(m) else None
    h1, h2 = st.columns([1, 6])
    ui.img(h1, api.team_logo(team), 110)
    if row is not None:
        h2.markdown(f"## {row['Équipe']}\n<span class='chip'>{row['Conférence']}</span>"
                    f"<span class='chip'>{row['Division']}</span><span class='chip'>{int(row['Rang'])}ᵉ de la ligue</span>",
                    unsafe_allow_html=True)
        c = st.columns(6)
        kpi(c[0], "Bilan", f"{row['V']}-{row['D']}-{row['DP']}", f"{row['MJ']} matchs")
        kpi(c[1], "Points", str(row["Pts"]), f"{row['% Pts']:.3f} %pts")
        kpi(c[2], "Buts pour", str(row["BP"]), f"{row['BP'] / max(row['MJ'], 1):.2f} / match")
        kpi(c[3], "Buts contre", str(row["BC"]), f"{row['BC'] / max(row['MJ'], 1):.2f} / match")
        kpi(c[4], "Différentiel", f"{row['Diff']:+d}", "", tone(row["Diff"]))
        kpi(c[5], "10 derniers", row["10 derniers"], f"série {row['Série']}")

    t1, t2, t3 = st.tabs(["📋 Effectif", "📊 Statistiques", "🗓️ Matchs"])
    with t1:
        data = ui.nhl_safe(f"roster/{team}/current")
        if data:
            r = api.roster(data)
            for pos in ["Centre", "Ailier gauche", "Ailier droit", "Défenseur", "Gardien"]:
                g = r[r["Poste"] == pos].reset_index(drop=True)
                if g.empty:
                    continue
                st.markdown(f"**{PLURAL[pos]} ({len(g)})**")
                ev = st.dataframe(g[["photo", "N°", "Joueur", "Tir", "Taille (cm)", "Poids (kg)", "Naissance", "Pays"]],
                                  column_config={"photo": st.column_config.ImageColumn("", width="small")},
                                  hide_index=True, width="stretch", on_select="rerun",
                                  selection_mode="single-row", key=f"ros_{team}_{pos}")
                i = _selected_row(ev)
                if i >= 0:
                    _open_player(g.iloc[i]["playerId"])
            st.caption("Cliquez sur un joueur pour ouvrir sa fiche.")
    with t2:
        data = ui.nhl_safe(f"club-stats/{team}/now")
        if data:
            cs = api.club_stats(data)
            sk = cs["skaters"]
            if not sk.empty:
                top = sk.head(15).iloc[::-1]
                fig = go.Figure([go.Bar(y=top["Joueur"], x=top["B"], name="Buts", orientation="h"),
                                 go.Bar(y=top["Joueur"], x=top["A"], name="Passes", orientation="h")])
                fig.update_layout(barmode="stack", title="Production offensive")
                st.plotly_chart(style_fig(fig, 480), width="stretch")
                ev = st.dataframe(sk.drop(columns=["playerId"]), hide_index=True, width="stretch",
                                  on_select="rerun", selection_mode="single-row", key=f"cs_{team}")
                i = _selected_row(ev)
                if i >= 0:
                    _open_player(sk.iloc[i]["playerId"])
            if not cs["goalies"].empty:
                st.markdown("**Gardiens**")
                st.dataframe(cs["goalies"].drop(columns=["playerId"]), hide_index=True, width="stretch")
    with t3:
        data = ui.nhl_safe(f"club-schedule-season/{team}/{api.season_id()}")
        if data:
            sch = api.team_schedule(data, team)
            done = sch[sch["Résultat"] != ""].copy()
            if not done.empty:
                done["Pts"] = done["Résultat"].map({"V": 2, "DP": 1, "D": 0})
                done["Points cumulés"] = done["Pts"].cumsum()
                fig = px.line(done, x="Date", y="Points cumulés", markers=True, title="Évolution des points")
                st.plotly_chart(style_fig(fig, 300), width="stretch")
            st.dataframe(sch, hide_index=True, width="stretch", height=420)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Joueurs
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Chargement des effectifs…")
def _all_players() -> pd.DataFrame:
    """Tous les joueurs des 32 effectifs (pour la recherche)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(t: str) -> pd.DataFrame:
        try:
            return api.roster(api.get_json(f"roster/{t}/current")).assign(Équipe=t)
        except api.NHLApiError as e:  # équipe indisponible : les autres restent cherchables
            api.logger.warning(f"Effectif {t} indisponible : {e}")
            return pd.DataFrame()

    with ThreadPoolExecutor(max_workers=8) as ex:
        frames = [f for f in ex.map(one, api.TEAMS) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def page_player() -> None:
    ui.setup("🧑 Joueurs")
    players = _all_players()
    pid = st.session_state.get("player_id")
    if not players.empty:
        labels = players.assign(lab=players["Joueur"] + " — " + players["Équipe"] + " (" + players["Poste"] + ")")
        ids = labels["playerId"].tolist()
        idx = ids.index(pid) if pid in ids else None
        choice = st.selectbox("Rechercher un joueur", labels["lab"].tolist(), index=idx,
                              placeholder="Tapez un nom…")
        if choice:
            pid = int(labels.loc[labels["lab"] == choice, "playerId"].iloc[0])
            st.session_state["player_id"] = pid
    if not pid:
        st.info("Choisissez un joueur, ou cliquez sur un joueur depuis une équipe ou le classement des meilleurs.")
        return
    data = ui.nhl_safe(f"player/{pid}/landing")
    if not data:
        return
    pr = api.player_profile(data)
    st.markdown(f"""<div class="hero"><img src="{pr['photo']}" width="140">
        <div><h1>{pr['nom']} <small>#{pr['numero'] or ''}</small></h1>
        <div class="meta">{pr['poste']} · {pr['equipe_nom'] or pr['equipe'] or ''} · né le {pr['naissance']} ({pr['lieu']})
        · {pr['taille'] or '?'} cm · {pr['poids'] or '?'} kg · tir {pr['tir'] or '?'}</div>
        <div class="meta">Repêché : {pr['draft'].get('year', '–')}, {pr['draft'].get('round', '–')}ᵉ tour,
        {pr['draft'].get('overallPick', '–')}ᵉ au total</div></div></div>""", unsafe_allow_html=True)
    if pr["equipe"] and st.button(f"Voir l'équipe {pr['equipe']}"):
        _open_team(pr["equipe"])

    h, car = pr["historique"], pr["carriere"]
    c = st.columns(5)
    kpi(c[0], "Matchs (carrière)", str(car.get("gamesPlayed", "–")))
    kpi(c[1], "Buts", str(car.get("goals", "–")))
    kpi(c[2], "Passes", str(car.get("assists", "–")))
    kpi(c[3], "Points", str(car.get("points", "–")))
    gp = car.get("gamesPlayed") or 0
    kpi(c[4], "Points / match", f"{(car.get('points') or 0) / gp:.2f}" if gp else "–")

    t1, t2, t3 = st.tabs(["📈 Saison en cours", "🗂️ Historique par saison", "🤖 Vu par le bot"])
    with t1:
        gl = ui.nhl_safe(f"player/{pid}/game-log/now")
        g = api.player_gamelog(gl) if gl else pd.DataFrame()
        if g.empty:
            st.info("Aucun match joué cette saison.")
        else:
            g["Points cumulés"] = g["Pts"].cumsum()
            fig = go.Figure([go.Bar(x=g["Date"], y=g["B"], name="Buts"), go.Bar(x=g["Date"], y=g["A"], name="Passes"),
                             go.Scatter(x=g["Date"], y=g["Points cumulés"], name="Points cumulés", yaxis="y2",
                                        mode="lines+markers")])
            fig.update_layout(barmode="stack", yaxis2=dict(overlaying="y", side="right", showgrid=False),
                              title="Match par match", xaxis_type="category")
            st.plotly_chart(style_fig(fig, 340), width="stretch")
            st.dataframe(g.iloc[::-1], hide_index=True, width="stretch")
    with t2:
        if h.empty:
            st.info("Pas d'historique NHL.")
        else:
            fig = go.Figure([go.Bar(x=h["Saison"], y=h["B"], name="Buts"), go.Bar(x=h["Saison"], y=h["A"], name="Passes"),
                             go.Scatter(x=h["Saison"], y=h["Pts / match"], name="Points / match", yaxis="y2",
                                        mode="lines+markers")])
            fig.update_layout(barmode="stack", yaxis2=dict(overlaying="y", side="right", showgrid=False),
                              title="Production par saison (saison régulière NHL)")
            st.plotly_chart(style_fig(fig, 380), width="stretch")
            st.dataframe(h.dropna(axis=1, how="all").iloc[::-1], hide_index=True, width="stretch")
    with t3:
        p = botdata.picks()
        mine = p[p["joueur"] == pr["nom"]] if not p.empty else p
        if mine.empty:
            st.info("Le bot n'a encore jamais proposé ce joueur.")
        else:
            st.dataframe(mine[["ref", "date", "marche", "cote_seuil", "cote", "p_final", "statut", "profit"]],
                         hide_index=True, width="stretch")
        ev = botdata.bot_players_for(pr["nom"])
        if not ev.empty:
            cols = [c for c in ("date", "adversaire", "score_but", "score_assist", "picked_but", "picked_assist",
                                "but", "assist") if c in ev]
            st.markdown("**Évaluations du bot** (probabilités du modèle)")
            st.dataframe(ev[cols], hide_index=True, width="stretch")


def page_about() -> None:
    ui.setup("ℹ️ À propos")
    st.markdown(f"""
- **Données NHL** : API publique `api-web.nhle.com`, rafraîchies toutes les 10 minutes.
- **Base du bot** : `{botdata.BOT_DB}` (lecture seule).
- **Portefeuille** : `{botdata.PORTFOLIO_DB}`.
- **Simulateur de bankroll** : `simulateur.html` à la racine du dépôt.
- Lancement : `streamlit run nhl/dashboard.py`.
""")
    st.caption(f"Généré le {datetime.now():%d/%m/%Y %H:%M}")
