// Meilleurs joueurs : buteurs, passeurs, pointeurs, gardiens ; podium, graphique, tableau cliquable.
import { POSITIONS, fullName, nhl, prevSeason, seasonId, seasonLabel, teamLogo } from '../api.js';
import { COLORS, canvas, chart, destroyCharts, esc, header, img, loading, onSegment, section, segmented, table } from '../ui.js';

const CATS = {
  goals: { label: 'Buteurs', unit: 'buts', kind: 'skater' },
  assists: { label: 'Passeurs', unit: 'passes', kind: 'skater' },
  points: { label: 'Pointeurs', unit: 'points', kind: 'skater' },
  wins: { label: 'Gardiens (victoires)', unit: 'victoires', kind: 'goalie' },
  savePctg: { label: 'Gardiens (% arrêts)', unit: '% arrêts', kind: 'goalie', fmt: (v) => v.toFixed(3) },
};
const state = { cat: 'goals', season: null, n: 20 };

export async function render(el, _p, alive) {
  const cur = seasonId();
  state.season ||= cur;
  const head = header('Meilleurs joueurs', 'Saison régulière. Cliquez sur un joueur pour ouvrir sa fiche.');
  el.innerHTML = head + loading('h-96');
  const c = CATS[state.cat];
  const path = c.kind === 'skater' ? 'skater-stats-leaders' : 'goalie-stats-leaders';
  const data = await nhl(`${path}/${state.season}/2?categories=${state.cat}&limit=${state.n}`);
  if (!alive()) return;
  const rows = (data[state.cat] || []).map((p, i) => ({ rang: i + 1, id: p.id, nom: fullName(p), equipe: p.teamAbbrev,
    poste: POSITIONS[p.position] || p.position, val: p.value, photo: p.headshot }));
  const fmt = c.fmt || ((v) => v);

  const seasons = [{ value: cur, label: seasonLabel(cur) }, { value: prevSeason(cur), label: seasonLabel(prevSeason(cur)) }];
  el.innerHTML = head + `<div class="flex flex-wrap gap-3 mb-6"><div id="s-cat"></div><div id="s-season"></div>
    <select id="s-n" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm">${[10, 20, 30, 50].map((n) => `<option ${n === state.n ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
    <div id="body"></div>`;
  el.querySelector('#s-cat').innerHTML = segmented('cat', Object.entries(CATS).map(([v, x]) => ({ value: v, label: x.label })), state.cat);
  el.querySelector('#s-season').innerHTML = segmented('season', seasons, state.season);
  const again = () => { destroyCharts(); render(el, _p, alive); };
  onSegment(el, 'cat', (v) => { state.cat = v; again(); });
  onSegment(el, 'season', (v) => { state.season = v; again(); });
  el.querySelector('#s-n').addEventListener('change', (e) => { state.n = +e.target.value; again(); });

  const body = el.querySelector('#body');
  if (!rows.length) {
    body.innerHTML = section('', `<p class="text-slate-400">Pas encore de données pour ${seasonLabel(state.season)}. Essayez la saison ${seasonLabel(prevSeason(cur))}.</p>`);
    return;
  }

  const medal = ['🥇', '🥈', '🥉'];
  const podium = rows.slice(0, 3).map((r, i) => `<a href="#/joueur/${r.id}" class="card p-5 flex items-center gap-4 hover:border-accent/60 transition ${i === 0 ? 'ring-1 ring-amber-400/40' : ''}">
    <div class="relative shrink-0"><img src="${esc(r.photo)}" alt="" class="w-20 h-20 rounded-full bg-white/5 object-cover">
    <img src="${teamLogo(r.equipe)}" alt="" class="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-ink p-0.5"></div>
    <div class="min-w-0"><div class="text-2xl">${medal[i]}</div><div class="font-bold text-white truncate">${esc(r.nom)}</div>
    <div class="text-xs text-slate-400">${esc(r.equipe)} · ${esc(r.poste)}</div>
    <div class="mt-1 text-2xl font-extrabold text-accent">${fmt(r.val)} <span class="text-sm font-medium text-slate-400">${c.unit}</span></div></div></a>`).join('');

  body.innerHTML = `<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">${podium}</div>
    <div class="grid grid-cols-1 xl:grid-cols-5 gap-6"><div class="xl:col-span-3">${section(`Top ${rows.length} — ${c.label.toLowerCase()}`, canvas('lead-chart', 'h-[640px]'))}</div>
    <div class="xl:col-span-2">${section('Classement', '<div id="lead-tbl"></div>')}</div></div>`;

  chart('lead-chart', { type: 'bar', data: { labels: rows.map((r) => `${r.nom} (${r.equipe})`),
    datasets: [{ label: c.unit, data: rows.map((r) => r.val), borderRadius: 4,
      backgroundColor: rows.map((_, i) => (i < 3 ? COLORS.amber : COLORS.accent)) }] },
  options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { y: { grid: { display: false } },
    x: c.fmt ? { min: Math.max(0, Math.min(...rows.map((r) => r.val)) - 0.01) } : {} },
  onClick: (_e, els) => { if (els[0]) location.hash = `#/joueur/${rows[els[0].index].id}`; } } });

  el.querySelector('#lead-tbl').append(table([
    { key: 'rang', label: '#', align: 'left' },
    { key: 'nom', label: 'Joueur', align: 'left', html: (r) => `<span class="inline-flex items-center gap-2">${img(r.photo, 'w-8 h-8 rounded-full bg-white/5')}<span class="font-medium text-white">${esc(r.nom)}</span></span>` },
    { key: 'equipe', label: 'Équipe', align: 'left', html: (r) => `<span class="inline-flex items-center gap-1.5">${img(teamLogo(r.equipe), 'w-5 h-5')}${esc(r.equipe)}</span>` },
    { key: 'val', label: c.unit, html: (r) => `<b class="text-white">${fmt(r.val)}</b>`, sort: (r) => r.val },
  ], rows, { href: (r) => `#/joueur/${r.id}`, maxH: 'max-h-[640px]' }));
}
