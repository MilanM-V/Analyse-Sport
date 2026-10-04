import sqlite3
import logging
from datetime import datetime, timedelta
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger("NHL.Database")

DB_PATH = "./bot_database.db"

def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15.0)

# V14 : Ajout dynamique des colonnes XGBoost si elles n'existent pas
def ensure_schema():
    """Vérifie et met à jour le schéma si nécessaire."""
    conn = get_connection()
    c = conn.cursor()
    for table in ["picks", "picks_assists", "players"]:
        for col, col_type in [
            ("is_home", "BOOLEAN DEFAULT 0"),
            ("opp_b2b", "BOOLEAN DEFAULT 0"),
            ("consec_goals", "INTEGER DEFAULT 0"),
            ("is_top6", "BOOLEAN DEFAULT 0"),
            ("linemate_synergy", "REAL DEFAULT 0"),
            ("team_scoring_env", "REAL DEFAULT 0"),
            ("prior_g60", "REAL DEFAULT 0"),
            ("prior_a60", "REAL DEFAULT 0"),
            ("prior_sog60", "REAL DEFAULT 0"),
            ("prior_sh_pct", "REAL DEFAULT 0"),
            ("opp_xga_60", "REAL DEFAULT 0")
        ]:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
    conn.commit()
    conn.close()

def init_db():
    """Initialise le schéma de la base de données SQL si elle n'existe pas."""
    logger.info("Initialisation de la base SQLite...")
    conn = get_connection()
    c = conn.cursor()

    # Table des picks BUTS
    c.execute('''
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, vague TEXT, joueur TEXT, equipe TEXT, adversaire TEXT,
            score REAL, verdict TEXT, pp1 BOOLEAN, backup BOOLEAN, b2b BOOLEAN,
            ixg REAL, hdcf REAL, sog REAL, atoi REAL, l10_g REAL, season_g REAL,
            pdo REAL, ga_g REAL, cf_pct REAL, hdca_g REAL, pk_pct REAL,
            rebounds REAL, rush REAL, is_home BOOLEAN, opp_b2b BOOLEAN,
            consec_goals INTEGER, but INTEGER DEFAULT NULL,
            is_top6 BOOLEAN DEFAULT 0, linemate_synergy REAL DEFAULT 0,
            team_scoring_env REAL DEFAULT 0, prior_g60 REAL DEFAULT 0,
            prior_a60 REAL DEFAULT 0, prior_sog60 REAL DEFAULT 0,
            prior_sh_pct REAL DEFAULT 0, opp_xga_60 REAL DEFAULT 0
        )
    ''')

    # Table des picks ASSISTS
    c.execute('''
        CREATE TABLE IF NOT EXISTS picks_assists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, vague TEXT, joueur TEXT, equipe TEXT, adversaire TEXT,
            score REAL, verdict TEXT, pp1 BOOLEAN, backup BOOLEAN, b2b BOOLEAN,
            atoi REAL, l10_a REAL, season_a REAL,
            pdo REAL, ga_g REAL, cf_pct REAL, pk_pct REAL,
            is_home BOOLEAN, opp_b2b BOOLEAN, assist INTEGER DEFAULT NULL,
            is_top6 BOOLEAN DEFAULT 0, linemate_synergy REAL DEFAULT 0,
            team_scoring_env REAL DEFAULT 0, prior_g60 REAL DEFAULT 0,
            prior_a60 REAL DEFAULT 0, prior_sog60 REAL DEFAULT 0,
            prior_sh_pct REAL DEFAULT 0, opp_xga_60 REAL DEFAULT 0
        )
    ''')

    # Table des picks POINTS
    c.execute('''
        CREATE TABLE IF NOT EXISTS picks_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, vague TEXT, joueur TEXT, equipe TEXT, adversaire TEXT,
            score REAL, verdict TEXT, pp1 BOOLEAN, backup BOOLEAN, b2b BOOLEAN,
            atoi REAL, l10_pts REAL, season_pts REAL, pdo REAL, ga_g REAL, 
            cf_pct REAL, is_home BOOLEAN, opp_b2b BOOLEAN,
            point INTEGER DEFAULT NULL
        )
    ''')

    # Table unique pour tous les joueurs évalués (log global)
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, vague TEXT, joueur TEXT, equipe TEXT, adversaire TEXT,
            score_but REAL, score_assist REAL, score_point REAL,
            picked_but BOOLEAN, picked_assist BOOLEAN, picked_point BOOLEAN,
            pp1 BOOLEAN, backup BOOLEAN, b2b BOOLEAN,
            ixg REAL, hdcf REAL, sog REAL, atoi REAL,
            l10_g REAL, l10_a REAL, l10_pts REAL,
            season_g REAL, season_a REAL, season_pts REAL,
            pdo REAL, ga_g REAL, cf_pct REAL, hdca_g REAL,
            pk_pct REAL, consec_goals INTEGER, game_mode TEXT,
            cote REAL, goalie_sv_pct REAL,
            is_top6 BOOLEAN DEFAULT 0, linemate_synergy REAL DEFAULT 0,
            team_scoring_env REAL DEFAULT 0, prior_g60 REAL DEFAULT 0,
            prior_a60 REAL DEFAULT 0, prior_sog60 REAL DEFAULT 0,
            prior_sh_pct REAL DEFAULT 0, opp_xga_60 REAL DEFAULT 0,
            but INTEGER DEFAULT NULL, assist INTEGER DEFAULT NULL, point INTEGER DEFAULT NULL
        )
    ''')

    # Table des paris combinés (V18.2)
    c.execute('''
        CREATE TABLE IF NOT EXISTS picks_parlays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, vague TEXT, type_combo TEXT,
            leg1_joueur TEXT, leg2_joueur TEXT, leg3_joueur TEXT,
            cote_totale REAL, mise REAL, resultat INTEGER DEFAULT NULL
        )
    ''')

    conn.commit()
    
    # Upgrade existing tables if necessary (V14-V19 Migration)
    logger.info("Vérification de l'intégrité de la base de données...")
    tables_to_fix = ["picks", "picks_assists", "picks_points", "players"]
    
    # Colonnes universelles (V14 à V19)
    # On s'assure que TOUTES les tables ont ces colonnes pour la cohérence des stats
    common_cols = [
        ("is_home", "BOOLEAN DEFAULT 0"),
        ("opp_b2b", "BOOLEAN DEFAULT 0"),
        ("consec_goals", "INTEGER DEFAULT 0"),
        ("cote", "REAL DEFAULT NULL"),
        ("mise", "REAL DEFAULT NULL"),
        ("closing_cote", "REAL DEFAULT NULL"),
        ("game_mode", "TEXT DEFAULT 'regular'"),
        ("ixg", "REAL DEFAULT 0"),
        ("hdcf", "REAL DEFAULT 0"),
        ("sog", "REAL DEFAULT 0"),
        ("atoi", "REAL DEFAULT 0"),
        ("goalie_sv_pct", "REAL DEFAULT NULL"),  # P5: Save % du gardien adverse
        # Audit P2/P3 : traçabilité complète du pari
        ("p_model", "REAL DEFAULT NULL"),
        ("p_novig", "REAL DEFAULT NULL"),
        ("p_final", "REAL DEFAULT NULL"),
        ("ev", "REAL DEFAULT NULL"),
        ("bookmaker", "TEXT DEFAULT NULL"),
        ("closing_p_novig", "REAL DEFAULT NULL"),
        ("model_version", "TEXT DEFAULT NULL"),
        ("features_json", "TEXT DEFAULT NULL"),
        # Mode proxy (aucun book FR dans The Odds API) : cote seuil + cote réellement prise
        ("cote_proxy", "REAL DEFAULT NULL"),
        ("cote_seuil", "REAL DEFAULT NULL"),
        ("price_source", "TEXT DEFAULT NULL"),
        ("cote_reelle", "REAL DEFAULT NULL"),
        ("book_reel", "TEXT DEFAULT NULL"),
        ("pris", "INTEGER DEFAULT NULL"),
    ]
    
    for table in tables_to_fix:
        for col_name, col_type in common_cols:
            try:
                # Vérifier si la colonne existe déjà pour éviter des logs inutiles
                c.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                # La colonne n'existe pas, on l'ajoute
                try:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    logger.info(f"🛠️ Migration : Colonne '{col_name}' ajoutée à la table '{table}'.")
                except Exception as e:
                    logger.error(f"❌ Erreur migration {table}.{col_name}: {e}")

    # Colonnes spécifiques à la table 'players' (Transition V12 -> V14)
    player_cols = [
        ("score_but", "REAL"), ("score_assist", "REAL"), ("score_point", "REAL"),
        ("picked_but", "BOOLEAN"), ("picked_assist", "BOOLEAN"), ("picked_point", "BOOLEAN"),
        ("l10_a", "REAL"), ("l10_pts", "REAL"), ("season_a", "REAL"), ("season_pts", "REAL"),
        ("assist", "INTEGER DEFAULT NULL"), ("point", "INTEGER DEFAULT NULL")
    ]
    for col_name, col_type in player_cols:
        try:
            c.execute(f"ALTER TABLE players ADD COLUMN {col_name} {col_type}")
            logger.info(f"Migration V14 : Colonne '{col_name}' ajoutée à la table 'players'.")
        except sqlite3.OperationalError: pass
    
    # P0 : un seul pick par (date, joueur) et par marché. Les redémarrages du bot
    # (watchdog) renvoyaient les mêmes vagues et loggaient des doublons.
    for table in ("picks", "picks_assists", "picks_points"):
        try:
            c.execute(f"DELETE FROM {table} WHERE id NOT IN (SELECT MIN(id) FROM {table} GROUP BY date, joueur)")
            if c.rowcount:
                logger.info(f"🧹 {c.rowcount} doublon(s) supprimé(s) dans '{table}'.")
            c.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_date_joueur ON {table} (date, joueur)")
        except sqlite3.Error as e:
            logger.error(f"❌ Index d'unicité {table} : {e}")

    conn.commit()
    conn.close()
    ensure_schema()

def insert_pick(table: str, pick_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """
    Inserts a selected pick into the specified table.

    Un pick déjà présent pour (date, joueur) est ignoré (index unique).

    Args:
        table: Table name ('picks', 'picks_assists', 'picks_points').
        pick_data: Dictionary containing pick statistics.
        conn: Optional existing database connection.

    Returns:
        L'id du pick inséré, ou None s'il existait déjà.
    """
    auto_close = conn is None
    if auto_close:
        conn = get_connection()
    c = conn.cursor()

    cols = ', '.join(pick_data.keys())
    placeholders = ', '.join(['?'] * len(pick_data))

    sql = f'INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})'
    c.execute(sql, list(pick_data.values()))
    pick_id = c.lastrowid if c.rowcount else None
    if pick_id is None:
        logger.info(f"Pick déjà enregistré ignoré : {pick_data.get('joueur')} ({pick_data.get('date')}, {table})")

    if auto_close:
        conn.commit()
        conn.close()
        
    return pick_id

PICK_TABLES = {"B": "picks", "A": "picks_assists"}


def pick_ref(table: str, pick_id: int) -> str:
    """Référence courte affichée sur Telegram : B12 (buteur), A7 (passeur)."""
    prefix = {v: k for k, v in PICK_TABLES.items()}[table]
    return f"{prefix}{pick_id}"


def get_pick_id(table: str, date: str, joueur: str, conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Id d'un pick déjà enregistré pour (date, joueur), sinon None."""
    own = conn is None
    conn = conn or get_connection()
    row = conn.execute(f"SELECT id FROM {table} WHERE date = ? AND joueur = ?", (date, joueur)).fetchone()
    if own:
        conn.close()
    return row[0] if row else None


def _parse_ref(ref: str) -> Optional[tuple]:
    ref = ref.strip().lstrip("#").upper()
    if len(ref) < 2 or ref[0] not in PICK_TABLES or not ref[1:].isdigit():
        return None
    return PICK_TABLES[ref[0]], int(ref[1:])


def record_pick_decision(ref: str, cote: Optional[float] = None, book: Optional[str] = None) -> Dict[str, Any]:
    """Enregistre la décision de l'utilisateur sur un pick (/pris ou /skip).

    Args:
        ref: Référence du pick (ex. "B12", "A7", "#B12").
        cote: Cote réellement obtenue ; None = pari non pris (/skip).
        book: Book où le pari a été pris (optionnel).

    Returns:
        {"ok": bool, "error"?: str, "joueur", "cote_seuil", "under_threshold": bool, "table", "id", "mise"}
    """
    parsed = _parse_ref(ref)
    if parsed is None:
        return {"ok": False, "error": f"Référence invalide : {ref} (attendu B12 ou A7)"}
    table, pick_id = parsed
    conn = get_connection()
    try:
        row = conn.execute(f"SELECT joueur, cote_seuil, mise FROM {table} WHERE id = ?", (pick_id,)).fetchone()
        if row is None:
            return {"ok": False, "error": f"Pick {ref} introuvable"}
        joueur, seuil, mise = row
        if cote is None:
            conn.execute(f"UPDATE {table} SET pris = 0 WHERE id = ?", (pick_id,))
        else:
            conn.execute(f"UPDATE {table} SET pris = 1, cote_reelle = ?, book_reel = ? WHERE id = ?",
                         (cote, book, pick_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "joueur": joueur, "cote_seuil": seuil, "table": table, "id": pick_id, "mise": mise,
            "under_threshold": cote is not None and seuil is not None and cote < seuil}


def insert_player(player_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Inserts an evaluated player log into the 'players' table.

    Args:
        player_data: Dictionary containing player evaluation data.
        conn: Optional existing database connection.
    """
    auto_close = conn is None
    if auto_close:
        conn = get_connection()
    c = conn.cursor()

    cols = ', '.join(player_data.keys())
    placeholders = ', '.join(['?'] * len(player_data))

    sql = f'INSERT INTO players ({cols}) VALUES ({placeholders})'
    c.execute(sql, list(player_data.values()))

    if auto_close:
        conn.commit()
        conn.close()

def insert_parlay(parlay_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Inserts a generated parlay (combiné) into the picks_parlays table.
    """
    auto_close = conn is None
    if auto_close:
        conn = get_connection()
    c = conn.cursor()

    cols = ', '.join(parlay_data.keys())
    placeholders = ', '.join(['?'] * len(parlay_data))

    sql = f'INSERT INTO picks_parlays ({cols}) VALUES ({placeholders})'
    c.execute(sql, list(parlay_data.values()))

    if auto_close:
        conn.commit()
        conn.close()

def reset_db() -> None:
    """Clears all content from all relevant tables."""
    conn = get_connection()
    c = conn.cursor()
    for table in ['picks', 'picks_assists', 'picks_points', 'players']:
        c.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()

def get_roi_stats(table: str = "picks", target_col: str = "but", days: str = "all", game_mode: str = "all") -> str:
    """
    Calculates and returns ROI statistics for a specific market.
    Uses actual odds (cote) for profit calculation when available.

    Args:
        table: The table to query.
        target_col: The column representing the result (but, assist, point).
        days: 'all' or string number of days.
        game_mode: 'all', 'regular', or 'playoff' to filter by game mode.

    Returns:
        A formatted HTML string with ROI stats.
    """
    conn = get_connection()
    c = conn.cursor()

    params = []
    # Cote réellement obtenue (/pris) si renseignée ; les picks refusés (/skip : cote FR
    # sous la cote seuil) ne sont pas joués, donc exclus du ROI.
    query = (f"SELECT {target_col}, COALESCE(cote_reelle, cote), verdict FROM {table} "
             f"WHERE {target_col} IS NOT NULL AND {target_col} != '' AND (pris IS NULL OR pris != 0)")
    if days != "all":
        try:
            days_int = int(days)
            cutoff = (datetime.now() - timedelta(days=days_int)).strftime('%Y-%m-%d')
            query += " AND date >= ?"
            params.append(cutoff)
        except ValueError:
            pass

    if game_mode in ("regular", "playoff"):
        query += " AND game_mode = ?"
        params.append(game_mode)

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    if not rows:
        return f"Pas assez de données pour {table}."

    # Calculer la cote moyenne pour les cotes manquantes
    cotes_valides = [r[1] for r in rows if r[1] is not None and r[1] != '']
    mean_cote = round(sum(cotes_valides) / len(cotes_valides), 2) if cotes_valides else 1.85

    total_played = len(rows)
    total_won = 0
    global_units = 0.0
    cat_stats = {}

    for result, cote, verdict in rows:
        result = int(result) if result else 0
        cote = float(cote) if cote else mean_cote

        unit = (cote - 1) if result > 0 else -1.0
        if result > 0:
            total_won += 1
        global_units += unit

        if verdict not in cat_stats:
            cat_stats[verdict] = {"played": 0, "won": 0, "units": 0.0}
        cat_stats[verdict]["played"] += 1
        if result > 0:
            cat_stats[verdict]["won"] += 1
        cat_stats[verdict]["units"] += unit

    global_units = round(global_units, 1)
    global_sign = "+" if global_units > 0 else ""
    winrate_global = (total_won / total_played) * 100
    roi_pct = round((global_units / total_played) * 100, 1)

    msg = f"<b>📊 STATS {table.upper()} : {global_sign}{global_units} U (ROI {roi_pct}%)</b>\n"
    msg += f"{total_won}✅ / {total_played} ({winrate_global:.1f}%) | Cote moy: {mean_cote}\n"
    msg += "──────────────────\n"

    for verdict in sorted(cat_stats.keys()):
        s = cat_stats[verdict]
        if s["played"] > 0:
            units_cat = round(s["units"], 1)
            cat_sign = "+" if units_cat > 0 else ""
            roi_cat = (s["won"] / s["played"]) * 100
            msg += f"<b>{verdict} [{cat_sign}{units_cat} U]</b> : {s['won']}✅ / {s['played']} ({roi_cat:.1f}%)\n"

    return msg

if not os.path.exists(DB_PATH):
    init_db()
else:
    ensure_schema()
