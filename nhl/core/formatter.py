"""
core/formatter.py — Formatage des messages Telegram et construction des combinés.

Extrait de bot_logic.py pour réutilisation et tests indépendants.
"""
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

import nhl.core.loaders as loaders
from nhl.core.database import insert_parlay

from nhl.config.settings import cfg

logger = logging.getLogger("NHL.Formatter")


def find_cross_duo(list1: List[Dict], list2: List[Dict]) -> Optional[Tuple[Dict, Dict]]:
    """Trouve une paire de picks venant de matchs différents.

    Args:
        list1: Premier pool de picks triés par EV.
        list2: Second pool de picks triés par EV.

    Returns:
        Tuple de deux picks de matchs différents, ou None.
    """
    for p1 in list1:
        g1 = {p1['Equipe'], p1.get('Adversaire', '')}
        for p2 in list2:
            if p1['Joueur'] == p2['Joueur']:
                continue
            g2 = {p2['Equipe'], p2.get('Adversaire', '')}
            if not g1.intersection(g2):
                return (p1, p2)
    return None


def get_best_per_match(picks_list: List[Dict]) -> List[Dict]:
    """Retourne le meilleur pick par match (meilleur EV).

    Args:
        picks_list: Liste de picks avec 'Cote', 'Proba', 'Equipe', 'Adversaire'.

    Returns:
        Liste du meilleur pick de chaque match.
    """
    best: Dict[str, Dict] = {}
    for p in picks_list:
        if p.get('Cote') and p['Cote'] > 1.05:
            m_key = f"{p['Equipe']}-{p.get('Adversaire', '')}"
            if m_key not in best or (p.get('Proba', 0) * p['Cote']) > (best[m_key].get('Proba', 0) * best[m_key].get('Cote', 1)):
                best[m_key] = p
    return list(best.values())


def format_telegram_v18(
    buts: List[Dict[str, Any]],
    assists: List[Dict[str, Any]],
    points: List[Dict[str, Any]],
    wave_label: str,
    wave_ids: List[str],
    compos_en_memoire: Dict[str, Dict[str, Any]],
) -> str:
    """Formate le message Telegram V18.3 complet (singles + combinés).

    Args:
        buts: Picks buteurs filtrés et enrichis.
        assists: Picks passeurs filtrés et enrichis.
        points: Picks pointeurs filtrés et enrichis.
        wave_label: Label de la vague (horaire).
        wave_ids: IDs des matchs de la vague.
        compos_en_memoire: Compos en mémoire du bot.

    Returns:
        Message HTML formaté pour Telegram.
    """
    if cfg.api.mode == "playoff":
        msg = f"<b>\U0001f3c6 NHL PLAYOFF V18.3 \u2014 VAGUE {wave_label}</b>\n\n"
    else:
        msg = f"<b>\U0001f3d2 NHL V18.3 \u2014 VAGUE {wave_label}</b>\n\n"

    for mid in wave_ids:
        data = compos_en_memoire.get(mid)
        if not data:
            continue

        m = data["match_info"]
        t1_full = loaders.REVERSE_TEAM_MAPPING.get(m['home'], m['home'])
        t2_full = loaders.REVERSE_TEAM_MAPPING.get(m['away'], m['away'])

        h_abbr = loaders.TEAM_MAPPING.get(m['home'], m['home'])
        a_abbr = loaders.TEAM_MAPPING.get(m['away'], m['away'])

        msg += f"<b>Match {t1_full} vs {t2_full} :</b>\n"

        for emoji, label, picks_list in [
            ("\U0001f525", "Buteurs", buts), ("\U0001f170\ufe0f", "Passeurs", assists),
            ("\U0001f3c6", "Pointeurs", points)
        ]:
            m_picks = [r for r in picks_list if r['Equipe'] in (h_abbr, a_abbr)]
            m_picks.sort(key=lambda x: (x.get('Proba', 0) * (x.get('Cote') or 0)) - 1.0, reverse=True)
            if m_picks:
                msg += f"  {emoji} <i>{label} :</i>\n"
                for r in m_picks:
                    home_icon = '\U0001f3e0' if r['IsHome'] else '\u2708\ufe0f'
                    cote_str = f" @{r['Cote']:.2f} chez {r.get('Bookmaker', 'Inconnu')} | Edge: {((r.get('Proba', 0) * (r.get('Cote', 1) or 1)) - 1)*100:.1f}% | Mise: {r.get('Mise', '1 U')}" if r.get('Cote') else ""
                    msg += f"  \u2022 {home_icon} <b>{r['Joueur']}</b>{cote_str}\n"

        m_all = [r for picks_list in [buts, assists, points]
                 for r in picks_list if r['Equipe'] in (h_abbr, a_abbr)]
        if not m_all:
            msg += "  <i>\u26a0\ufe0f Aucun pick sur ce match.</i>\n"
        msg += "\n"

    # --- COMBINÉS INTELLIGENTS (V18.3) ---
    msg += _build_parlays_section(buts, assists, points, wave_label)

    return msg


def _build_parlays_section(
    buts: List[Dict], assists: List[Dict], points: List[Dict], wave_label: str
) -> str:
    """Construit la section combinés du message Telegram et insère en DB.

    Utilise parlay_builder pour générer un combiné strictement inter-match.
    """
    from nhl.core.parlay_builder import build_best_parlay
    from nhl.core.database import insert_parlay

    msg = ""
    today_str = datetime.now().strftime("%Y-%m-%d")

    best_parlay = build_best_parlay(buts, assists)

    if best_parlay:
        p1 = best_parlay["pick1"]
        p2 = best_parlay["pick2"]
        cote_combo = best_parlay["cote"]
        ev_combo = best_parlay["ev"]
        mise = 0.25 # Fun bet

        msg += f"<b>🔥 COMBINÉ SÉCURISÉ INTER-MATCH (EV: +{ev_combo*100:.1f}%) :</b>\n"
        msg += f"  • {p1['Joueur']} ({p1.get('Categorie', 'Pick')}) @{p1['Cote']:.2f}\n"
        msg += f"  • {p2['Joueur']} ({p2.get('Categorie', 'Pick')}) @{p2['Cote']:.2f}\n"
        msg += f"  => <b>Cote Combo : @{cote_combo:.2f}</b> | Mise: {mise} U\n\n"

        insert_parlay({
            "date": today_str, "vague": wave_label, "type_combo": "STRICT_INTER_MATCH",
            "leg1_joueur": p1["Joueur"], "leg2_joueur": p2["Joueur"],
            "leg3_joueur": None,
            "cote_totale": cote_combo, "mise": mise
        })
    else:
        msg += "  <i>Aucun combiné EV+ inter-match possible pour cette vague.</i>\n"

    return msg
