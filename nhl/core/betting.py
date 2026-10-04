"""
core/betting.py — Stratégie de mise (audit P2), utilisée à l'identique par le bot et la simulation.

1. Probabilité finale = mélange du modèle et du no-vig Pinnacle :
       p = w * p_model + (1 - w) * p_novig      (w appris sur la saison de validation)
   Sans Pinnacle, p = p_model et l'EV exigée est majorée (`no_pinnacle_extra_ev`).
2. EV calculée UNIQUEMENT sur la cote d'exécution. En prod, aucun book FR ne cote les props
   dans The Odds API : la cote d'exécution est un PROXY (médiane US × exec_haircut) et chaque
   pari porte une `cote_seuil` = cote minimale à trouver sur un book FR pour rester value.
3. Seuils d'EV par tranche de cote lus dans [betting] ev_min_* (à défaut [thresholds.ev_adaptive]).
4. Kelly fractionné sur la bankroll réelle, SANS plancher (mise < min => pas de pari),
   plafonds par pari, par match (paris corrélés) et par jour.
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from nhl.config.settings import cfg


@dataclass
class BetParams:
    """Paramètres de la stratégie (défauts = [betting] de settings.toml)."""
    blend_w: Dict[str, float]
    cote_min: Dict[str, float]
    cote_max: Dict[str, float]
    ev_low: float
    ev_mid: float
    ev_high: float
    low_cut: float
    mid_cut: float
    no_pinnacle_extra_ev: float
    kelly_fraction: float
    min_stake: float
    max_stake: Dict[str, float]
    max_game_exposure: float
    max_daily_exposure: float
    markets: tuple = ("but", "ast")

    @classmethod
    def from_config(cls, **overrides: Any) -> "BetParams":
        b, ev = cfg.betting, cfg.thresholds.ev_adaptive
        p = cls(
            blend_w={"but": b.blend_w_but, "ast": b.blend_w_ast},
            cote_min={"but": b.cote_min_but, "ast": b.cote_min_ast},
            cote_max={"but": b.cote_max_but, "ast": b.cote_max_ast},
            ev_low=getattr(b, "ev_min_low", ev.low_odds_min_ev),
            ev_mid=getattr(b, "ev_min_mid", ev.mid_odds_min_ev),
            ev_high=getattr(b, "ev_min_high", ev.high_odds_min_ev),
            low_cut=ev.low_odds_cutoff, mid_cut=ev.mid_odds_cutoff,
            no_pinnacle_extra_ev=b.no_pinnacle_extra_ev, kelly_fraction=b.kelly_fraction,
            min_stake=b.min_stake_u, max_stake={"but": b.max_stake_but_u, "ast": b.max_stake_ast_u},
            max_game_exposure=b.max_game_exposure_u, max_daily_exposure=b.max_daily_exposure_u,
            markets=tuple(b.markets),
        )
        for k, v in overrides.items():
            setattr(p, k, v)
        return p


def blend_probability(p_model: float, p_novig: Optional[float], w: float) -> float:
    """Mélange modèle / marché sharp. Sans référence Pinnacle, renvoie p_model."""
    if p_novig is None or p_novig != p_novig:  # None ou NaN
        return p_model
    return w * p_model + (1.0 - w) * p_novig


def ev_threshold(cote: float, params: BetParams, has_pinnacle: bool = True) -> float:
    """EV minimale exigée selon la cote (et majoration sans référence Pinnacle)."""
    if cote < params.low_cut:
        thr = params.ev_low
    elif cote <= params.mid_cut:
        thr = params.ev_mid
    else:
        thr = params.ev_high
    return thr + (0.0 if has_pinnacle else params.no_pinnacle_extra_ev)


def min_odds(p_final: float, threshold: float) -> float:
    """Cote minimale à obtenir pour que l'EV atteigne `threshold` : (1 + seuil) / p.

    Arrondie au centième SUPÉRIEUR (l'EV reste ≥ seuil à la cote affichée).
    """
    return math.ceil((1.0 + threshold) / p_final * 100 - 1e-9) / 100


def kelly_units(p: float, cote: float, bankroll: float, params: BetParams, market: str) -> float:
    """Mise Kelly fractionnée en unités, arrondie à 0,5 U, sans plancher artificiel."""
    b = cote - 1.0
    if b <= 0:
        return 0.0
    f = (p * b - (1.0 - p)) / b
    if f <= 0:
        return 0.0
    units = round(bankroll * f * params.kelly_fraction * 2) / 2
    if units < params.min_stake:
        return 0.0
    return min(units, params.max_stake[market])


def select_bets(candidates: List[Dict[str, Any]], bankroll: float,
                params: Optional[BetParams] = None, current_exposure: float = 0.0) -> List[Dict[str, Any]]:
    """Filtre, classe et dimensionne les paris d'une vague.

    Args:
        candidates: dicts avec au minimum market ('but'|'ast'), p_model, cote (cote
            d'exécution, None si le book ne cote pas), game_id ; p_novig optionnel.
        bankroll: bankroll en unités (Portfolio.get_balance() en prod).
        params: paramètres (défaut : settings.toml).
        current_exposure: mises déjà engagées aujourd'hui.

    Returns:
        Les candidats retenus, enrichis de p_final, ev, cote_seuil (cote minimale à
        prendre) et mise (unités > 0), triés par EV.
    """
    params = params or BetParams.from_config()
    scored = []
    for c in candidates:
        m, cote = c["market"], c.get("cote")
        if m not in params.markets or not cote or cote <= 1.01:
            continue
        if not (params.cote_min[m] <= cote <= params.cote_max[m]):
            continue
        pnv = c.get("p_novig")
        has_pin = pnv is not None and pnv == pnv
        p = blend_probability(c["p_model"], pnv, params.blend_w[m])
        ev = p * cote - 1.0
        thr = ev_threshold(cote, params, has_pin)
        if ev < thr:
            continue
        scored.append({**c, "p_final": p, "ev": ev, "cote_seuil": min_odds(p, thr)})

    scored.sort(key=lambda x: x["ev"], reverse=True)
    out, per_game, total = [], {}, current_exposure
    for c in scored:
        units = kelly_units(c["p_final"], c["cote"], bankroll, params, c["market"])
        if units <= 0:
            continue
        g = c.get("game_id")
        room = min(params.max_game_exposure - per_game.get(g, 0.0), params.max_daily_exposure - total)
        units = min(units, round(room * 2) / 2)
        if units < params.min_stake:
            continue
        c["mise"] = units
        per_game[g] = per_game.get(g, 0.0) + units
        total += units
        out.append(c)
    return out
