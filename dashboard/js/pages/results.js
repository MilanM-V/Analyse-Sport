// Résultats par soirée : score, tirs, buteurs (avec passeurs) et picks du bot sur chaque match.
import { addDays, botFile, fullName, name, nhl, teamLogo, today } from '../api.js';
import { chip, empty, esc, frDate, frTime, header, loading } from '../ui.js';

const STATE = { FUT: 'À venir', PRE: 'Avant-match', LIVE: 'En direct', CRIT: 'En direct', OFF: 'Terminé', FINAL: 'Terminé' };
const PICK_CLS = { 'gagné': 'bg-emerald-500/15 text-emerald-300', 'perdu': 'bg-rose-500/15 text-rose-300' };

export async function render(el, [date], alive) {
  const d = date || addDays(today(), -1);
  const nav = `<div class="flex flex-wrap items-center gap-2 mb-6">
    <a href="#/resultats/${addDays(d, -1)}" class="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10">←</a>
    <input id="r-date" type="date" value="${d}" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm">
    <a href="#/resultats/${addDays(d, 1)}" class="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10">→</a>
    <span class="ml-2 text-slate-300 capitalize">${frDate(d)}</span></div>`;
  const head = header('Résultats par soirée', 'Date NHL (heure de l\'Est). Les picks du bot du jour sont affichés sous chaque match.');
  el.innerHTML = head + nav + loading('h-64');
  const bind = () => el.querySelector('#r-date')?.addEventListener('change', (e) => { location.hash = `#/resultats/${e.target.value}`; });
  bind();

  const [data, bot] = await Promise.all([nhl(`score/${d}`), botFile('bot.json').catch(() => null)]);
  if (!alive()) return;
  const games = data.games || [];
  const picks = (bot?.picks || []).filter((p) => p.date === d);

  if (!games.length) { el.innerHTML = head + nav + empty('Aucun match ce jour-là.'); bind(); return; }

  const cards = games.map((g) => {
    const a = g.awayTeam; const h = g.homeTeam;
    const done = ['OFF', 'FINAL'].includes(g.gameState);
    const live = ['LIVE', 'CRIT'].includes(g.gameState);
    const end = g.gameOutcome?.lastPeriodType;
    const score = a.score != null ? `${a.score} <span class="text-slate-500">–</span> ${h.score}` : frTime(g.startTimeUTC);
    const win = (t, o) => (done && t.score > o.score ? 'text-white' : 'text-slate-400');
    const team = (t, o) => `<a href="#/equipe/${t.abbrev}" class="flex flex-col items-center gap-1 w-24 group">
      <img src="${teamLogo(t.abbrev)}" alt="" class="w-14 h-14 group-hover:scale-110 transition"><span class="font-bold ${win(t, o)}">${esc(t.abbrev)}</span></a>`;
    const goals = (g.goals || []).map((x) => {
      const ast = (x.assists || []).map((y) => name(y.name)).join(', ');
      return `<li class="flex gap-2"><span class="text-slate-500 w-16 shrink-0 whitespace-nowrap">P${x.period} ${esc(x.timeInPeriod || '')}</span>
        <img src="${teamLogo(x.teamAbbrev)}" class="w-4 h-4 mt-0.5" alt=""><span><a href="#/joueur/${x.playerId}" class="text-white hover:text-accent">${esc(fullName(x) || name(x.name))}</a>
        ${x.strength === 'pp' ? chip('AN', 'bg-amber-500/15 text-amber-300') : ''}${ast ? `<span class="text-slate-500"> · ${esc(ast)}</span>` : ''}</span></li>`;
    }).join('');
    const mine = picks.filter((p) => [a.abbrev, h.abbrev].includes(p.equipe));
    const bets = mine.length ? `<div class="mt-3 pt-3 border-t border-line flex flex-wrap gap-2">${mine.map((p) =>
      chip(`🎯 ${esc(p.joueur)} · ${p.marche}${p.phase === 'early' ? ' 🧪' : ''} · ${p.statut}`, PICK_CLS[p.statut] || 'bg-slate-500/20 text-slate-300')).join('')}</div>` : '';
    return `<div class="card p-4 sm:p-5 fade-in">
      <div class="flex items-center justify-between text-xs text-slate-400 mb-3"><span>${esc(name(g.venue))}</span>
        <span>${live ? chip('● En direct', 'bg-rose-500/20 text-rose-300') : STATE[g.gameState] || g.gameState}${end && end !== 'REG' ? ` (${end === 'OT' ? 'prol.' : 'tirs au but'})` : ''}</span></div>
      <div class="flex items-center justify-between">${team(a, h)}
        <div class="text-center"><div class="text-3xl sm:text-4xl font-extrabold tabular-nums text-white">${score}</div>
        ${a.sog != null ? `<div class="text-xs text-slate-400 mt-1">Tirs ${a.sog} – ${h.sog}</div>` : ''}</div>${team(h, a)}</div>
      ${goals ? `<ul class="mt-4 space-y-1.5 text-sm">${goals}</ul>` : ''}${bets}</div>`;
  }).join('');

  el.innerHTML = head + nav + `<p class="text-sm text-slate-400 mb-4">${games.length} match(s)${picks.length ? ` · ${picks.length} pick(s) du bot` : ''}</p>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">${cards}</div>`;
  bind();
}
