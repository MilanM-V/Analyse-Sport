"""
core/fr_odds.py — Cotes joueurs NHL des books français (Winamax, Unibet, Betclic).

The Odds API ne couvre aucun prop NHL des books français (check_odds_coverage.py, 2026-10-04) :
on lit les pages publiques des sites, sans compte. Chaque site embarque ses cotes en JSON :
- Winamax : `PRELOADED_STATE` (pages tournoi et match). À défaut, son canal temps réel
  Socket.IO (routes `tournament:142` puis `match:{id}`, même schéma). Winamax refuse
  l'empreinte TLS de Python (403) : `curl_cffi` imite Chrome. Il ne sert ses données qu'aux
  IP françaises : depuis le VPS IONOS (Francfort), la page arrive sans `matches`.
- Unibet.fr (plateforme FDJ ParionsSport) : `<script id="serverApp-state">`.
- Betclic : `<script id="ng-state">`.

Rien ici n'interrompt une vague : un book en échec est déclaré indisponible (alerte admin
une fois par jour) et le bot garde la cote estimée (shared.odds_api.apply_proxy).

Usage :
    python -m nhl.core.fr_odds --probe                  # accès et couverture des books configurés
    python -m nhl.core.fr_odds --probe --books winamax,unibet,betclic
"""
import argparse
import html as html_lib
import json
import logging
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from nhl.config.constants import ALL_ABBRS, TEAM_FULL_TO_ABBR
from nhl.config.settings import cfg
from shared.odds_api import _norm, match_player

logger = logging.getLogger("NHL.FrOdds")

BOOKS = ("winamax", "unibet", "betclic")
BOOK_LABELS = {"winamax": "Winamax", "unibet": "Unibet", "betclic": "Betclic"}
MARKET_KEYS = {"but": "BUTS", "ast": "ASSISTS"}       # clés de nhl.core.odds.fetch_nhl_odds
_KEY_ALIASES = {"BUTS": "BUTEUR", "ASSISTS": "PASSEUR"}  # fetch_nhl_odds expose les deux noms


class BookUnavailable(RuntimeError):
    """Le book ne fournit pas de cotes exploitables (403, page sans données, format inconnu)."""


@dataclass(frozen=True)
class BookGame:
    """Match tel qu'un book le liste (libellés du site, référence de sa page)."""
    book: str
    home: str
    away: str
    ref: str
    start: Optional[int] = None  # début (epoch UTC) si le book le donne

    @property
    def pair(self) -> Optional[frozenset]:
        """Paire d'abréviations NHL (ordre domicile / extérieur ignoré), None si une équipe est inconnue."""
        h, a = team_abbr(self.home), team_abbr(self.away)
        return frozenset((h, a)) if h and a and h != a else None


@dataclass(frozen=True)
class PropRow:
    """Cote « 1 ou plus » d'un joueur sur un marché ('but' ou 'ast')."""
    market: str
    player: str
    price: float


@dataclass
class FrOdds:
    """Résultat de fetch_fr_odds.

    Attributes:
        prices: {joueur: {"BUTS" | "ASSISTS": {book: cote}}}, joueurs rapprochés de players_map.
        rows: une ligne par cote lue (book, home, away, market, joueur, matched, price).
        status: par book : matchs listés, matchs trouvés, cotes lues et rapprochées, erreur.
    """
    prices: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    status: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration ([fr_odds] de settings.toml)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FrConfig:
    enabled: bool = False
    books: Tuple[str, ...] = ("unibet", "betclic")
    use_as_exec: bool = False
    exec_books: Tuple[str, ...] = BOOKS
    winamax_source: str = "page"
    proxy_winamax: str = ""
    timeout_s: float = 20.0
    min_delay_s: float = 1.0


def settings() -> FrConfig:
    """Section [fr_odds] de settings.toml (valeurs par défaut si elle est absente)."""
    c = getattr(cfg, "fr_odds", None)
    if c is None:
        return FrConfig()
    d = FrConfig()
    return FrConfig(
        enabled=bool(getattr(c, "enabled", d.enabled)),
        books=tuple(getattr(c, "books", d.books)),
        use_as_exec=bool(getattr(c, "use_as_exec", d.use_as_exec)),
        exec_books=tuple(getattr(c, "exec_books", d.exec_books)),
        winamax_source=str(getattr(c, "winamax_source", d.winamax_source)),
        proxy_winamax=str(getattr(c, "proxy_winamax", d.proxy_winamax) or ""),
        timeout_s=float(getattr(c, "timeout_s", d.timeout_s)),
        min_delay_s=float(getattr(c, "min_delay_s", d.min_delay_s)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Noms d'équipes et de joueurs
# ─────────────────────────────────────────────────────────────────────────────
_FULL_IDX = {_norm(k): v for k, v in TEAM_FULL_TO_ABBR.items()}
# Surnoms NHL (mots normalisés) ; les formes compactes sont celles d'Unibet (« VEG GKnights »)
_NICKNAMES: Dict[Tuple[str, ...], str] = {
    ("ducks",): "ANA", ("bruins",): "BOS", ("sabres",): "BUF", ("flames",): "CGY",
    ("hurricanes",): "CAR", ("blackhawks",): "CHI", ("avalanche",): "COL",
    ("blue", "jackets"): "CBJ", ("bjackets",): "CBJ", ("stars",): "DAL",
    ("red", "wings"): "DET", ("rwings",): "DET", ("oilers",): "EDM", ("panthers",): "FLA",
    ("kings",): "LAK", ("wild",): "MIN", ("canadiens",): "MTL", ("predators",): "NSH",
    ("devils",): "NJD", ("islanders",): "NYI", ("rangers",): "NYR", ("senators",): "OTT",
    ("flyers",): "PHI", ("penguins",): "PIT", ("sharks",): "SJS", ("kraken",): "SEA",
    ("blues",): "STL", ("lightning",): "TBL", ("maple", "leafs"): "TOR", ("mleafs",): "TOR",
    ("canucks",): "VAN", ("golden", "knights"): "VGK", ("gknights",): "VGK",
    ("capitals",): "WSH", ("jets",): "WPG", ("mammoth",): "UTA", ("hockey", "club"): "UTA",
    ("hockeyclub",): "UTA",
}


def teams_in(text: str) -> List[str]:
    """Abréviations des équipes NHL nommées dans un texte, par leur surnom, dans l'ordre.

    Sert aux libellés Unibet (« CAL Flames ») et aux adresses Betclic
    (« new-york-rangers-utah-mammoth »).
    """
    tokens = _norm(text.replace("-", " ")).split()
    found: List[str] = []
    i = 0
    while i < len(tokens):
        for size in (2, 1):
            abbr = _NICKNAMES.get(tuple(tokens[i:i + size]))
            if abbr:
                if abbr not in found:
                    found.append(abbr)
                i += size
                break
        else:
            i += 1
    return found


def team_abbr(label: str) -> Optional[str]:
    """Libellé d'équipe d'un book (nom complet, abréviation, forme Unibet) -> abréviation NHL."""
    if not label:
        return None
    if label.strip().upper() in ALL_ABBRS:
        return label.strip().upper()
    hit = _FULL_IDX.get(_norm(label))
    if hit:
        return hit
    found = teams_in(label)
    return found[0] if len(found) == 1 else None


def clean_player(name: str) -> str:
    """Nom publié par un book -> « Prénom Nom ».

    Winamax et Unibet écrivent parfois « Nom, Prénom » (« Miller, J.T. »), et Winamax ajoute
    l'année de naissance aux homonymes (« Elias Pettersson (1998) »). L'année est retirée :
    deux homonymes d'une même équipe restent ambigus et ne sont pas rapprochés (volontaire).
    """
    name = re.sub(r"\s*\(\d{4}\)\s*$", "", str(name)).strip()
    if "," in name:
        last, first = [x.strip() for x in name.split(",", 1)]
        name = f"{first} {last}"
    return name


def _price(value: Any) -> Optional[float]:
    """Cote décimale (« 2,75 », 2.75) -> float, None si absente ou ≤ 1."""
    try:
        p = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return p if p > 1.0 else None


# ─────────────────────────────────────────────────────────────────────────────
# Parseurs (sans réseau)
# ─────────────────────────────────────────────────────────────────────────────
WINAMAX_NHL = "142"  # tournamentId de la NHL chez Winamax
WINAMAX_LIST = "https://www.winamax.fr/paris-sportifs/sports/4/37/142"
WINAMAX_MATCH = "https://www.winamax.fr/paris-sportifs/match/{}"
WINAMAX_SOCKET = "https://sports-eu-west-3.winamax.fr/uof-sports-server/socket.io/"
_WM_STATE = re.compile(r"PRELOADED_STATE\s*=\s*(\{.*?\});\s*(?:var|</script>)", re.S)
WM_MARKETS = {"Buteur": "but", "Passes décisives du joueur : 1 ou plus": "ast"}

UNIBET = "https://www.unibet.fr"
UNIBET_LIST = UNIBET + "/paris-hockey-sur-glace"
_UB_STATE = re.compile(r'<script id="serverApp-state" type="application/json">(.*?)</script>', re.S)
_UB_HREF = re.compile(r'href="(/paris-hockey-sur-glace/[^"]*/nhl/(\d+)/[^"]+)"')
_UB_TITLE = re.compile(r'title="Voir plus de paris pour le match : ([^"|]+?) \|')
UB_MARKETS = {"Nombre de Buts - Joueur": "but", "Nombre de Passes décisives - Joueur": "ast"}

BETCLIC = "https://www.betclic.fr"
BETCLIC_LIST = BETCLIC + "/hockey-sur-glace-sice_hockey/nhl-c83"
_BC_STATE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)
_BC_HREF = re.compile(r'href="(/hockey-sur-glace-sice_hockey/nhl-c83/([a-z0-9-]+)-m(\d+))"')
BC_GOALS = "Buteur (prol. inc.)"
BC_ASSISTS = "Nombre de passes décisives du joueur"


def winamax_state(page: str) -> Dict[str, Any]:
    """État JSON d'une page Winamax ; BookUnavailable si elle ne contient pas de données sportives."""
    m = _WM_STATE.search(page or "")
    if not m:
        raise BookUnavailable("winamax : page sans PRELOADED_STATE")
    state = json.loads(m.group(1))
    if "matches" not in state:
        raise BookUnavailable("winamax : page sans données sportives (IP hors de France ?)")
    return state


def parse_winamax_listing(state: Dict[str, Any]) -> List[BookGame]:
    """Matchs NHL d'un état Winamax (page tournoi ou route `tournament:142`), du plus proche au plus lointain."""
    games = []
    for mid, m in (state.get("matches") or {}).items():
        title = str(m.get("title", ""))
        if str(m.get("tournamentId")) != WINAMAX_NHL or " - " not in title:
            continue  # autres compétitions, paris à long terme (vainqueur de la Coupe Stanley…)
        home, away = (x.strip() for x in title.split(" - ", 1))
        games.append(BookGame("winamax", home, away, str(mid), m.get("matchStart")))
    return sorted(games, key=lambda g: g.start or 0)


def parse_winamax_match(state: Dict[str, Any], match_id: str) -> List[PropRow]:
    """Cotes buteur et passeur (1 ou plus) d'un match Winamax."""
    outcomes, odds = state.get("outcomes") or {}, state.get("odds") or {}
    rows = []
    for bet in (state.get("bets") or {}).values():
        market = WM_MARKETS.get(bet.get("betTitle"))
        if market is None or str(bet.get("matchId")) != str(match_id):
            continue
        for oid in bet.get("outcomes", []):
            o, price = outcomes.get(str(oid)) or {}, _price(odds.get(str(oid)))
            if o.get("label") and o.get("available", True) and price:
                rows.append(PropRow(market, clean_player(o["label"]), price))
    return rows


def parse_unibet_listing(page: str) -> List[BookGame]:
    """Matchs NHL listés sur la page hockey d'Unibet (liens « Voir plus de paris pour le match »)."""
    games: Dict[str, BookGame] = {}
    for tag in re.findall(r"<a\b[^>]*>", page or ""):
        href, title = _UB_HREF.search(tag), _UB_TITLE.search(tag)
        if href and title and " vs " in title.group(1):
            home, away = (html_lib.unescape(x).strip() for x in title.group(1).split(" vs ", 1))
            games.setdefault(href.group(2), BookGame("unibet", home, away, href.group(1)))
    return list(games.values())


def parse_unibet_match(page: str) -> List[PropRow]:
    """Cotes « 1+ » des marchés buts et passes d'une page de match Unibet."""
    m = _UB_STATE.search(page or "")
    if not m:
        raise BookUnavailable("unibet : page sans serverApp-state")
    events = (json.loads(m.group(1)).get("EventsDetail") or {}).get("events") or []
    if not events:
        raise BookUnavailable("unibet : page de match sans événement")
    rows = []
    for group in events[0].get("groupedMarkets", []):
        desc = str(group.get("description", ""))
        market = next((v for k, v in UB_MARKETS.items() if desc.startswith(k)), None)
        if market is None:
            continue
        for mk in group.get("markets", []):
            for o in mk.get("outcomes", []):
                label, price = str(o.get("description", "")), _price(o.get("price"))
                if label.endswith(" 1+") and price and not o.get("hidden") and not o.get("suspended"):
                    rows.append(PropRow(market, clean_player(label[:-3]), price))
    return rows


def parse_betclic_listing(page: str) -> List[BookGame]:
    """Matchs NHL de la page compétition Betclic ; équipes lues dans l'adresse du match."""
    games: Dict[str, BookGame] = {}
    for path, slug, mid in _BC_HREF.findall(page or ""):
        teams = teams_in(slug)
        if len(teams) == 2:
            games.setdefault(mid, BookGame("betclic", teams[0], teams[1], path))
    return list(games.values())


def _betclic_selections(market: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [s for g in market.get("splitCardGroups", []) for s in g.get("selections", [])]
    for row in market.get("selectionMatrix", []):
        for cell in row.get("selections", []):
            sel = (cell.get("selectionOneof") or {}).get("selection")
            if sel:
                out.append(sel)
    return out


def parse_betclic_match(page: str) -> List[PropRow]:
    """Cotes buteur (prolongation incluse) et passeur (« 1 ou + ») d'une page de match Betclic."""
    m = _BC_STATE.search(page or "")
    if not m:
        raise BookUnavailable("betclic : page sans ng-state")
    rows: List[PropRow] = []
    seen = set()

    def take(market: str, mk: Dict[str, Any]) -> None:
        for s in _betclic_selections(mk):
            price = _price(s.get("odds"))
            if s.get("name") and price and s.get("status", 1) == 1:
                rows.append(PropRow(market, clean_player(s["name"]), price))

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            name = o.get("name")
            if name == BC_GOALS and "splitCardGroups" in o and "but" not in seen:
                seen.add("but")
                take("but", o)
            elif name == BC_ASSISTS and "groupMarkets" in o and "ast" not in seen:
                seen.add("ast")
                for g in o["groupMarkets"]:
                    if g.get("name") == "1 ou +":
                        take("ast", g)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Accès réseau
# ─────────────────────────────────────────────────────────────────────────────
LIST_TTL, MATCH_TTL = 600.0, 120.0
_HEADERS = {"Accept-Language": "fr-FR,fr;q=0.9"}
_CACHE: Dict[str, Tuple[float, str]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_put(url: str, text: str) -> None:
    """Met une page en cache et retire les pages expirées (le bot tourne des semaines : pas de fuite)."""
    now = time.monotonic()
    with _CACHE_LOCK:
        for k in [k for k, (t0, _) in _CACHE.items() if now - t0 > LIST_TTL]:
            del _CACHE[k]
        _CACHE[url] = (now, text)


class _Client:
    """Session HTTP d'un book : imite Chrome (curl_cffi), cache, pause entre deux pages, 1 nouvel essai."""

    def __init__(self, book: str, timeout: float, min_delay: float, proxy: str = "") -> None:
        from curl_cffi import requests as cr  # import tardif : les parseurs restent utilisables sans
        kw = {"proxies": {"https": proxy, "http": proxy}} if proxy else {}
        self.session = cr.Session(impersonate="chrome", **kw)
        self.book, self.timeout, self.min_delay = book, timeout, min_delay
        self._last = 0.0

    def _pause(self) -> None:
        wait = self.min_delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, url: str, ttl: float = 0.0) -> str:
        """Texte de la page (depuis le cache si plus récent que `ttl` secondes)."""
        if ttl:
            with _CACHE_LOCK:
                hit = _CACHE.get(url)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        for attempt in (1, 2):
            self._pause()
            try:
                r = self.session.get(url, headers=_HEADERS, timeout=self.timeout)
            except Exception as e:  # erreur réseau de curl_cffi : un nouvel essai, puis indisponible
                if attempt == 2:
                    raise BookUnavailable(f"{self.book} : {type(e).__name__} sur {url}") from e
                logger.warning(f"[FR] {self.book} : {type(e).__name__} sur {url}, nouvel essai")
                continue
            if r.status_code >= 500 and attempt == 1:
                logger.warning(f"[FR] {self.book} : HTTP {r.status_code} sur {url}, nouvel essai")
                continue
            if r.status_code != 200:
                raise BookUnavailable(f"{self.book} : HTTP {r.status_code} sur {url}")
            if ttl:
                _cache_put(url, r.text)
            return r.text
        raise BookUnavailable(f"{self.book} : pas de réponse pour {url}")


class _WinamaxChannel:
    """Canal temps réel de Winamax (Socket.IO v4, transport polling) : routes `tournament:…`, `match:…`."""

    def __init__(self, client: _Client) -> None:
        self.s, self.t = client.session, client.timeout
        self.hdr = {**_HEADERS, "Origin": "https://www.winamax.fr", "Referer": "https://www.winamax.fr/"}
        self.q = {"language": "FR", "version": "2.0", "embed": "false", "EIO": "4", "transport": "polling"}
        r = self.s.get(WINAMAX_SOCKET, params={**self.q, "t": str(time.time())}, headers=self.hdr, timeout=self.t)
        if r.status_code != 200 or not r.text.startswith("0"):
            raise BookUnavailable(f"winamax (canal) : connexion HTTP {r.status_code}")
        self.q["sid"] = json.loads(r.text[1:])["sid"]
        self._post("40")
        self._poll()

    def _post(self, body: str) -> None:
        self.s.post(WINAMAX_SOCKET, params={**self.q, "t": str(time.time())}, data=body,
                    headers={**self.hdr, "Content-Type": "text/plain;charset=UTF-8"}, timeout=self.t)

    def _poll(self) -> List[str]:
        r = self.s.get(WINAMAX_SOCKET, params={**self.q, "t": str(time.time())}, headers=self.hdr, timeout=self.t)
        return r.text.split("\x1e")

    def ask(self, route: str) -> Dict[str, Any]:
        rid = f"r{time.monotonic_ns()}"
        self._post("42" + json.dumps(["m", {"route": route, "requestId": rid}]))
        for _ in range(5):
            for pkt in self._poll():
                if pkt == "2":  # ping du serveur
                    self._post("3")
                elif pkt.startswith("42"):
                    msg = json.loads(pkt[2:])
                    if len(msg) > 1 and isinstance(msg[1], dict) and msg[1].get("requestId") == rid:
                        return msg[1]
        raise BookUnavailable(f"winamax (canal) : pas de réponse pour {route}")


Fetcher = Callable[[BookGame], List[PropRow]]


def _winamax(client: _Client, conf: FrConfig) -> Tuple[List[BookGame], Fetcher]:
    sources = ["socket", "page"] if conf.winamax_source == "socket" else ["page", "socket"]
    last: Optional[BookUnavailable] = None
    for src in sources:
        try:
            if src == "page":
                games = parse_winamax_listing(winamax_state(client.get(WINAMAX_LIST, LIST_TTL)))
                return games, lambda g: parse_winamax_match(
                    winamax_state(client.get(WINAMAX_MATCH.format(g.ref), MATCH_TTL)), g.ref)
            chan = _WinamaxChannel(client)
            games = parse_winamax_listing(chan.ask(f"tournament:{WINAMAX_NHL}"))
            return games, lambda g: parse_winamax_match(chan.ask(f"match:{g.ref}"), g.ref)
        except BookUnavailable as e:
            logger.warning(f"[FR] Winamax via {src} : {e}")
            last = e
    raise last or BookUnavailable("winamax : aucune source")


def _unibet(client: _Client, conf: FrConfig) -> Tuple[List[BookGame], Fetcher]:
    games = parse_unibet_listing(client.get(UNIBET_LIST, LIST_TTL))
    return games, lambda g: parse_unibet_match(client.get(UNIBET + g.ref, MATCH_TTL))


def _betclic(client: _Client, conf: FrConfig) -> Tuple[List[BookGame], Fetcher]:
    games = parse_betclic_listing(client.get(BETCLIC_LIST, LIST_TTL))
    return games, lambda g: parse_betclic_match(client.get(BETCLIC + g.ref, MATCH_TTL))


_ADAPTERS: Dict[str, Callable[[_Client, FrConfig], Tuple[List[BookGame], Fetcher]]] = {
    "winamax": _winamax, "unibet": _unibet, "betclic": _betclic}


def _book_props(book: str, wanted: Iterable[frozenset], conf: FrConfig
                ) -> Tuple[List[Tuple[BookGame, List[PropRow]]], Dict[str, Any]]:
    """Matchs demandés trouvés chez un book et leurs cotes joueurs.

    Raises:
        BookUnavailable: le book ne liste aucun match NHL ou ne renvoie aucune cote.
    """
    client = _Client(book, conf.timeout_s, conf.min_delay_s, conf.proxy_winamax if book == "winamax" else "")
    listing, fetch = _ADAPTERS[book](client, conf)
    if not listing:
        raise BookUnavailable(f"{book} : aucun match NHL listé")
    wanted = set(wanted)
    found: List[Tuple[BookGame, List[PropRow]]] = []
    for game in listing:  # du plus proche au plus lointain : le match du soir passe en premier
        if game.pair in wanted:
            wanted.discard(game.pair)
            found.append((game, fetch(game)))
    empty = [f"{g.home}-{g.away}" for g, rows in found if not rows]
    if found and len(empty) == len(found):
        raise BookUnavailable(f"{book} : aucune cote joueur sur {', '.join(empty)}")
    if empty:
        logger.error(f"[FR] {book} : aucune cote joueur sur {', '.join(empty)}")
    return found, {"listed": len(listing), "games": len(found), "empty": empty}


# ─────────────────────────────────────────────────────────────────────────────
# Alertes et API publique
# ─────────────────────────────────────────────────────────────────────────────
_ALERTED: Dict[str, str] = {}


def _alert(book: str, reason: str) -> None:
    """Erreur dans les logs ; alerte Telegram admin une seule fois par jour et par book."""
    from shared.telegram_hub import send_telegram
    from shared.utils import paris_now
    logger.error(f"[FR] {BOOK_LABELS.get(book, book)} indisponible : {reason}")
    day = paris_now().strftime("%Y-%m-%d")
    if _ALERTED.get(book) == day:
        return
    _ALERTED[book] = day
    send_telegram(f"⚠️ <b>Cotes {BOOK_LABELS.get(book, book)} indisponibles</b>\n{html_lib.escape(reason)}\n"
                  "Le bot garde la cote estimée pour ce site.", recipient="admin")


def fetch_fr_odds(games: Iterable[Tuple[str, str]], players_map: Optional[Dict[str, str]] = None,
                  books: Optional[Sequence[str]] = None, conf: Optional[FrConfig] = None) -> FrOdds:
    """Cotes buteur et passeur des books français pour les matchs demandés.

    Args:
        games: affiches [(domicile, extérieur)], noms complets ou abréviations.
        players_map: {nom_joueur: abréviation_équipe} des joueurs à rapprocher. Sans lui,
            les cotes sont rendues sous le nom publié par le book.
        books: books à lire (défaut : [fr_odds] books).
        conf: configuration (défaut : settings()).

    Returns:
        FrOdds. Un book indisponible n'interrompt rien : il figure dans `status` avec son erreur.
    """
    conf = conf or settings()
    books = [b for b in (books or conf.books) if b in _ADAPTERS]
    pairs: Dict[frozenset, Tuple[str, str]] = {}
    for h, a in games:
        ha, aa = team_abbr(h), team_abbr(a)
        if ha and aa:
            pairs[frozenset((ha, aa))] = (ha, aa)
        else:
            logger.warning(f"[FR] Affiche non reconnue : {h} - {a}")
    res = FrOdds()
    if not pairs or not books:
        return res
    with ThreadPoolExecutor(max_workers=len(books)) as ex:
        futures = {b: ex.submit(_book_props, b, list(pairs), conf) for b in books}
    for book, fut in futures.items():
        try:
            found, status = fut.result()
        except BookUnavailable as e:
            res.status[book] = {"listed": 0, "games": 0, "rows": 0, "matched": 0, "error": str(e)}
            _alert(book, str(e))
            continue
        except Exception as e:  # format inattendu : on le signale, la vague continue
            logger.error(f"[FR] {book} : erreur inattendue", exc_info=True)
            res.status[book] = {"listed": 0, "games": 0, "rows": 0, "matched": 0,
                                "error": f"{type(e).__name__}: {e}"}
            _alert(book, f"erreur inattendue {type(e).__name__}: {e}")
            continue
        n_rows = n_matched = 0
        for game, rows in found:
            home, away = pairs[game.pair]
            cands = [n for n, t in (players_map or {}).items() if t in (home, away)]
            for r in rows:
                name = match_player(r.player, cands) if players_map is not None else r.player
                n_rows += 1
                res.rows.append({"book": book, "home": home, "away": away, "market": r.market,
                                 "joueur": name or r.player, "matched": name is not None, "price": r.price})
                if name is None:
                    continue
                n_matched += 1
                res.prices.setdefault(name, {}).setdefault(MARKET_KEYS[r.market], {})[book] = r.price
        res.status[book] = {**status, "rows": n_rows, "matched": n_matched, "error": None}
    return res


def apply_fr_prices(results: Dict[str, Dict[str, Any]], fr: FrOdds, conf: Optional[FrConfig] = None) -> int:
    """Ajoute les cotes françaises aux résultats de nhl.core.odds.fetch_nhl_odds (modifiés en place).

    Chaque marché reçoit `fr_prices = {book: cote}`. Si `use_as_exec`, la meilleure cote parmi
    `exec_books` devient la cote d'exécution (`price`, `bookmaker`, `price_source = "fr"`) ;
    la cote estimée est conservée dans `proxy_price`.

    Returns:
        Nombre de marchés dont la cote d'exécution est une cote française.
    """
    conf = conf or settings()
    n_exec = 0
    for player, markets in fr.prices.items():
        entry = results.setdefault(player, {})
        for key, by_book in markets.items():
            d = entry.get(key)
            if not isinstance(d, dict):
                d = {}
                entry[key] = d
                entry[_KEY_ALIASES[key]] = d
            d["fr_prices"] = dict(by_book)
            playable = {b: p for b, p in by_book.items() if b in conf.exec_books}
            if not conf.use_as_exec or not playable:
                continue
            best = max(playable, key=playable.get)
            if d.get("price") and d.get("price_source") != "fr":
                d["proxy_price"] = d["price"]
            d.update(price=playable[best], bookmaker=BOOK_LABELS[best], price_source="fr",
                     is_winamax=(best == "winamax"))
            n_exec += 1
    return n_exec


def status_line(fr: FrOdds) -> str:
    """Résumé d'une lecture pour les logs : « unibet 72/80, betclic ✗ (HTTP 403) »."""
    parts = []
    for book, s in fr.status.items():
        parts.append(f"{book} ✗ ({s['error']})" if s.get("error") else f"{book} {s['matched']}/{s['rows']}")
    return ", ".join(parts) or "aucun book"


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic : python -m nhl.core.fr_odds --probe
# ─────────────────────────────────────────────────────────────────────────────
def probe(books: Sequence[str], conf: Optional[FrConfig] = None) -> int:
    """Teste l'accès à chaque book : matchs listés, équipes reconnues, cotes du premier match coté.

    Returns:
        Nombre de books en échec (0 = tout fonctionne).
    """
    conf = conf or settings()
    failures = 0
    for book in books:
        try:
            client = _Client(book, conf.timeout_s, conf.min_delay_s,
                             conf.proxy_winamax if book == "winamax" else "")
            listing, fetch = _ADAPTERS[book](client, conf)
            unknown = sorted({lab for g in listing for lab in (g.home, g.away) if not team_abbr(lab)})
            sample, rows = None, []
            for game in listing[:3]:  # les matchs lointains n'ont pas encore leurs cotes joueurs
                rows = fetch(game)
                sample = game
                if rows:
                    break
            n_but = sum(r.market == "but" for r in rows)
            n_ast = sum(r.market == "ast" for r in rows)
            ok = bool(listing) and n_but > 0
            failures += not ok
            print(f"{'OK ' if ok else 'NON'}  {book:8s} {len(listing)} matchs NHL"
                  + (f" | {sample.home} - {sample.away} : buteur {n_but}, passes {n_ast}" if sample else "")
                  + (f" | équipes non reconnues : {unknown}" if unknown else ""))
            for r in sorted((r for r in rows if r.market == "but"), key=lambda r: r.price)[:3]:
                print(f"       {r.player} {r.price:.2f}")
        except BookUnavailable as e:
            failures += 1
            print(f"NON  {book:8s} {e}")
    return failures


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Cotes joueurs NHL des books français")
    ap.add_argument("--probe", action="store_true", help="teste l'accès et la lecture de chaque book")
    ap.add_argument("--books", default="", help="books à tester, séparés par des virgules (défaut : config)")
    a = ap.parse_args()
    if not a.probe:
        ap.print_help()
        return
    books = [b.strip() for b in a.books.split(",") if b.strip()] or list(settings().books)
    sys.exit(1 if probe(books) else 0)


if __name__ == "__main__":
    main()
