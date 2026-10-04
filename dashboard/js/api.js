// Accès aux données : API NHL (via le relais /nhl/ de vercel.json) et fichiers du bot (branche dashboard-data).

const RAW = 'https://raw.githubusercontent.com/MilanM-V/Analyse-Nhl/dashboard-data/';
const LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
// En local : fichiers générés par exporter.py d'abord ; en ligne : branche dashboard-data d'abord
const DATA_BASES = LOCAL ? ['', RAW, RAW + 'dashboard/'] : [RAW, RAW + 'dashboard/', ''];
const cache = new Map();

export const POSITIONS = { C: 'Centre', L: 'Ailier gauche', R: 'Ailier droit', D: 'Défenseur', G: 'Gardien' };
export const PLURAL = { C: 'Centres', L: 'Ailiers gauches', R: 'Ailiers droits', D: 'Défenseurs', G: 'Gardiens' };
export const TEAMS = ['ANA', 'BOS', 'BUF', 'CAR', 'CBJ', 'CGY', 'CHI', 'COL', 'DAL', 'DET', 'EDM', 'FLA', 'LAK', 'MIN',
  'MTL', 'NJD', 'NSH', 'NYI', 'NYR', 'OTT', 'PHI', 'PIT', 'SEA', 'SJS', 'STL', 'TBL', 'TOR', 'UTA', 'VAN', 'VGK', 'WPG', 'WSH'];

/** GET /nhl/{path} (relayé vers api-web.nhle.com/v1), mis en cache pour la session. */
export async function nhl(path) {
  if (cache.has(path)) return cache.get(path);
  const p = fetch(`/nhl/${path}`).then(async (r) => {
    if (!r.ok) throw new Error(`API NHL indisponible (${r.status}) pour ${path}`);
    return r.json();
  });
  cache.set(path, p);
  p.catch(() => cache.delete(path));
  return p;
}

/** Fichier JSON exporté par le bot (bot.json, db.json, data.json). */
export async function botFile(name) {
  const key = `bot:${name}`;
  if (cache.has(key)) return cache.get(key);
  const p = (async () => {
    const errors = [];
    for (const base of DATA_BASES) {
      try {
        const r = await fetch(`${base}${name}?t=${Date.now()}`, { cache: 'no-store' });
        if (r.ok) return await r.json();
        errors.push(`${base || './'} : ${r.status}`);
      } catch (e) {
        errors.push(`${base || './'} : ${e.message}`);
      }
    }
    throw new Error(`${name} introuvable (${errors.join(' · ')})`);
  })();
  cache.set(key, p);
  p.catch(() => cache.delete(key));
  return p;
}

// ── Dates et saisons ────────────────────────────────────────────────────────
export const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export const today = () => iso(new Date());
export function addDays(s, n) { const d = new Date(`${s}T12:00:00`); d.setDate(d.getDate() + n); return iso(d); }
export function weekStart(s) { const d = new Date(`${s}T12:00:00`); const w = (d.getDay() + 6) % 7; d.setDate(d.getDate() - w); return iso(d); }
/** Saison NHL en cours, ex. '20262027' (bascule au 1er août). */
export function seasonId(s = today()) { const [y, m] = s.split('-').map(Number); const a = m >= 8 ? y : y - 1; return `${a}${a + 1}`; }
export const prevSeason = (id) => `${+id.slice(0, 4) - 1}${id.slice(0, 4)}`;
export const seasonLabel = (id) => `${id.slice(0, 4)}-${id.slice(6)}`;

export const teamLogo = (abbr) => `https://assets.nhle.com/logos/nhl/svg/${abbr}_dark.svg`;
export const name = (x) => (x && typeof x === 'object' ? x.default ?? '' : x ?? '');
export const fullName = (p) => `${name(p.firstName)} ${name(p.lastName)}`.trim();
export const mmss = (sec) => (sec == null ? '' : `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`);

// ── Transformations (mêmes règles que l'ancien dashboard Streamlit) ─────────
export function standings(data) {
  return (data.standings || []).map((t) => ({
    rang: t.leagueSequence, equipe: name(t.teamName), abbr: name(t.teamAbbrev), conf: t.conferenceName,
    div: t.divisionName, mj: t.gamesPlayed, v: t.wins, d: t.losses, dp: t.otLosses, pts: t.points,
    pct: t.pointPctg, bp: t.goalFor, bc: t.goalAgainst, diff: t.goalDifferential,
    serie: `${t.streakCode || ''}${t.streakCount || ''}`,
    l10: `${t.l10Wins ?? 0}-${t.l10Losses ?? 0}-${t.l10OtLosses ?? 0}`,
    dom: `${t.homeWins ?? 0}-${t.homeLosses ?? 0}-${t.homeOtLosses ?? 0}`,
    ext: `${t.roadWins ?? 0}-${t.roadLosses ?? 0}-${t.roadOtLosses ?? 0}`,
  })).sort((a, b) => a.rang - b.rang);
}

export function roster(data) {
  const order = { C: 0, L: 1, R: 2, D: 3, G: 4 };
  const rows = [];
  for (const g of ['forwards', 'defensemen', 'goalies']) {
    for (const p of data[g] || []) {
      rows.push({ id: p.id, num: p.sweaterNumber, nom: fullName(p), code: p.positionCode,
        poste: POSITIONS[p.positionCode] || p.positionCode, tir: p.shootsCatches, taille: p.heightInCentimeters,
        poids: p.weightInKilograms, naissance: p.birthDate, pays: p.birthCountry, photo: p.headshot });
    }
  }
  return rows.sort((a, b) => (order[a.code] - order[b.code]) || ((a.num ?? 99) - (b.num ?? 99)));
}

/** Historique NHL saison régulière, une ligne par saison (équipes multiples fusionnées). */
export function seasonHistory(landing) {
  const by = new Map();
  for (const s of landing.seasonTotals || []) {
    if (s.leagueAbbrev !== 'NHL' || s.gameTypeId !== 2) continue;
    const k = String(s.season);
    const cur = by.get(k) || { saison: seasonLabel(k), equipes: [], mj: 0, b: 0, a: 0, pts: 0, pm: 0, tirs: 0, ban: 0,
      toi: s.avgToi, svp: s.savePctg, gaa: s.goalsAgainstAvg, w: 0 };
    const team = name(s.teamName);
    if (team && !cur.equipes.includes(team)) cur.equipes.push(team);
    cur.mj += s.gamesPlayed || 0; cur.b += s.goals || 0; cur.a += s.assists || 0; cur.pts += s.points || 0;
    cur.pm += s.plusMinus || 0; cur.tirs += s.shots || 0; cur.ban += s.powerPlayGoals || 0; cur.w += s.wins || 0;
    cur.toi = s.avgToi ?? cur.toi;
    by.set(k, cur);
  }
  return [...by.values()].map((r) => ({ ...r, equipe: r.equipes.join(' / '), ppm: r.mj ? r.pts / r.mj : null,
    pctTir: r.tirs ? (100 * r.b) / r.tirs : null }));
}

/** Tous les joueurs des 32 effectifs (recherche de joueur), gardés en sessionStorage. */
export async function allPlayers() {
  const key = `players:${seasonId()}`;
  try { const c = sessionStorage.getItem(key); if (c) return JSON.parse(c); } catch (e) { /* stockage indisponible */ }
  const lists = await Promise.all(TEAMS.map((t) => nhl(`roster/${t}/${seasonId()}`)
    .then((d) => roster(d).map((p) => ({ ...p, equipe: t })))
    .catch((e) => { console.warn(`Effectif ${t} indisponible : ${e.message}`); return []; })));
  const all = lists.flat();
  try { sessionStorage.setItem(key, JSON.stringify(all)); } catch (e) { /* stockage plein : pas de cache */ }
  return all;
}
