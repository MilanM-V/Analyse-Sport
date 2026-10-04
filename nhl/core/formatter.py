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


def format_match_time(raw: str) -> str:
    """'04.10. 20:00' (format de scraper.py) -> '20h00' ; valeur brute si illisible."""
    try:
        return datetime.strptime(raw.strip()[-5:], "%H:%M").strftime("%Hh%M")
    except (ValueError, AttributeError):
        return raw or ""


def _pick_line(r: Dict[str, Any]) -> str:
    """Suffixe d'une ligne de pick (message du canal).

    Mode proxy (CoteSeuil présente) : seulement la cote minimale à trouver sur un book FR
    et la mise — ni la cote proxy US, ni la référence (réservée aux fiches privées admin).
    """
    if r.get('CoteSeuil'):
        return f" — à prendre si cote &gt; <b>{r['CoteSeuil']:.2f}</b> | Mise: {r.get('Mise', '1 U')}"
    if r.get('Cote'):
        edge = (r.get('Proba', 0) * r['Cote'] - 1) * 100
        return f" @{r['Cote']:.2f} chez {r.get('Bookmaker', 'Inconnu')} | Edge: {edge:.1f}% | Mise: {r.get('Mise', '1 U')}"
    return ""


def _leg(p: Dict[str, Any], label: str) -> str:
    """Jambe de combiné : cote seuil en mode proxy, sinon cote du book."""
    if p.get('CoteSeuil'):
        return f"  • {p['Joueur']} ({label}) cote &gt; {p['CoteSeuil']:.2f}\n"
    return f"  • {p['Joueur']} ({label}) @{p['Cote']:.2f}\n"


def _combo_line(p1: Dict[str, Any], p2: Dict[str, Any], cote_combo: float, label: str, mise: float) -> str:
    """Ligne de cote du combiné (produit des cotes seuils en mode proxy)."""
    if p1.get('CoteSeuil') and p2.get('CoteSeuil'):
        return f"  => <b>{label} : à prendre si cote &gt; {p1['CoteSeuil'] * p2['CoteSeuil']:.2f}</b> | Mise: {mise} U\n\n"
    return f"  => <b>{label} : @{cote_combo:.2f}</b> | Mise: {mise} U\n\n"


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
    if cfg.mode.paper_trading:
        msg = "<b>\U0001f4c4 PAPER TRADING \u2014 ne pas miser (validation du mod\u00e8le en cours)</b>\n" + msg

    for mid in wave_ids:
        data = compos_en_memoire.get(mid)
        if not data:
            continue

        m = data["match_info"]
        t1_full = loaders.REVERSE_TEAM_MAPPING.get(m['home'], m['home'])
        t2_full = loaders.REVERSE_TEAM_MAPPING.get(m['away'], m['away'])

        h_abbr = loaders.TEAM_MAPPING.get(m['home'], m['home'])
        a_abbr = loaders.TEAM_MAPPING.get(m['away'], m['away'])
        
        time_str = m.get('time', '')
        time_display = f" 🕒 {format_match_time(time_str)}" if time_str else ""

        msg += f"<b>Match {t1_full} vs {t2_full}{time_display} :</b>\n"

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
                    cote_str = _pick_line(r)
                    early = " \U0001f9ea" if r.get('Phase') == 'early' else ""
                    msg += f"  \u2022 {home_icon} <b>{r['Joueur']}</b>{early}{cote_str}\n"

        m_all = [r for picks_list in [buts, assists, points]
                 for r in picks_list if r['Equipe'] in (h_abbr, a_abbr)]
        if not m_all:
            msg += "  <i>\u26a0\ufe0f Aucun pick sur ce match.</i>\n"
        msg += "\n"

    if any(r.get('Phase') == 'early' for r in buts + assists + points):
        msg += ("\U0001f9ea <i>Mode découverte : joueur à moins de 10 matchs cette saison, estimation "
                "basée aussi sur la saison passée. Mise réduite de moitié.</i>\n\n")

    # --- COMBINÉS INTELLIGENTS (V18.3) ---
    msg += _build_parlays_section(buts, assists, points, wave_label)

    return msg


def _build_parlays_section(
    buts: List[Dict], assists: List[Dict], points: List[Dict], wave_label: str
) -> str:
    """Construit la section combinés du message Telegram et insère en DB.

    Utilise parlay_builder pour générer un combiné strictement inter-match.
    """
    from nhl.core.parlay_builder import build_best_parlay, build_synergy_parlay
    from nhl.core.database import insert_parlay

    msg = ""
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Combiné Inter-Match classique
    best_parlay = build_best_parlay(buts, assists)

    if best_parlay:
        p1 = best_parlay["pick1"]
        p2 = best_parlay["pick2"]
        cote_combo = best_parlay["cote"]
        ev_combo = best_parlay["ev"]
        mise = 0.25 # Fun bet

        msg += f"<b>🔥 COMBINÉ SÉCURISÉ INTER-MATCH (EV: +{ev_combo*100:.1f}%) :</b>\n"
        msg += _leg(p1, p1.get('Categorie', 'Pick')) + _leg(p2, p2.get('Categorie', 'Pick'))
        msg += _combo_line(p1, p2, cote_combo, "Cote Combo", mise)

        insert_parlay({
            "date": today_str, "vague": wave_label, "type_combo": "STRICT_INTER_MATCH",
            "leg1_joueur": p1["Joueur"], "leg2_joueur": p2["Joueur"],
            "leg3_joueur": None,
            "cote_totale": cote_combo, "mise": mise
        })
    else:
        msg += "  <i>Aucun combiné EV+ inter-match possible pour cette vague.</i>\n\n"

    # 2. MyMatch Synergy (Nouveau)
    synergy_parlay = build_synergy_parlay(buts, assists)
    
    if synergy_parlay:
        p1 = synergy_parlay["pick1"]
        p2 = synergy_parlay["pick2"]
        cote_combo = synergy_parlay["cote"]
        ev_combo = synergy_parlay["ev"]
        mise = 0.25 # Fun bet
        
        msg += f"<b>⚡ MYMATCH SYNERGY (CORRÉLATION DE LIGNE) (EV: +{ev_combo*100:.1f}%) :</b>\n"
        msg += _leg(p1, "Buteur") + _leg(p2, "Passeur")
        msg += _combo_line(p1, p2, cote_combo, "Cote MyMatch", mise)
        
        insert_parlay({
            "date": today_str, "vague": wave_label, "type_combo": "SYNERGY_MYMATCH",
            "leg1_joueur": p1["Joueur"], "leg2_joueur": p2["Joueur"],
            "leg3_joueur": None,
            "cote_totale": cote_combo, "mise": mise
        })

    return msg
