// Calendrier : matchs de la semaine, jour par jour (heure de Paris), résultats des matchs joués.
import { addDays, nhl, teamLogo, today, weekStart } from '../api.js';
import { COLORS, canvas, chart, chip, empty, esc, frDate, frTime, header, loading, section } from '../ui.js';

const TYPE = { 1: 'Présaison', 2: '', 3: 'Séries' };

export async function render(el, [date], alive) {
  const w = weekStart(date || today());
  const nav = `<div class="flex flex-wrap items-center gap-2 mb-6">
    <a href="#/calendrier/${addDays(w, -7)}" class="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10">← Semaine précédente</a>
    <input id="c-date" type="date" value="${w}" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm">
    <a href="#/calendrier/${addDays(w, 7)}" class="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10">Semaine suivante →</a>
    <a href="#/calendrier" class="px-3 py-2 rounded-lg text-accent hover:bg-white/5">Cette semaine</a></div>`;
  const head = header('Calendrier', `Semaine du ${frDate(w, { day: 'numeric', month: 'long', year: 'numeric' })} · heures de Paris`);
  el.innerHTML = head + nav + loading('h-64');
  const bind = () => el.querySelector('#c-date')?.addEventListener('change', (e) => { location.hash = `#/calendrier/${e.target.value}`; });
  bind();

  const data = await nhl(`schedule/${w}`);
  if (!alive()) return;
  const days = (data.gameWeek || []).filter((d) => d.date >= w && d.date <= addDays(w, 6));
  const total = days.reduce((n, d) => n + (d.games || []).length, 0);
  if (!total) { el.innerHTML = head + nav + empty('Aucun match cette semaine.'); bind(); return; }

  const list = days.filter((d) => (d.games || []).length).map((d) => {
    const rows = d.games.map((g) => {
      const a = g.awayTeam; const h = g.homeTeam;
      const done = ['OFF', 'FINAL'].includes(g.gameState);
      const mid = done || a.score != null ? `<span class="font-extrabold text-white tabular-nums">${a.score} – ${h.score}</span>` : `<span class="text-slate-300">${frTime(g.startTimeUTC)}</span>`;
      return `<a href="#/resultats/${d.date}" class="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 transition">
        <span class="flex items-center gap-2 w-28"><img src="${teamLogo(a.abbrev)}" class="w-7 h-7" alt="">${esc(a.abbrev)}</span>
        <span class="text-center min-w-[90px]">${mid}${TYPE[g.gameType] ? `<div>${chip(TYPE[g.gameType], 'bg-slate-500/20 text-slate-300')}</div>` : ''}</span>
        <span class="flex items-center gap-2 w-28 justify-end">${esc(h.abbrev)}<img src="${teamLogo(h.abbrev)}" class="w-7 h-7" alt=""></span></a>`;
    }).join('');
    return section(`<span class="capitalize">${frDate(d.date)}</span> <span class="text-sm font-normal text-slate-400">· ${d.games.length} match(s)</span>`,
      `<div class="grid grid-cols-1 md:grid-cols-2 gap-x-6">${rows}</div>`);
  }).join('');

  el.innerHTML = head + nav + section('Matchs par jour', canvas('cal-chart', 'h-48')) + list;
  bind();
  chart('cal-chart', { type: 'bar', data: { labels: days.map((d) => frDate(d.date, { weekday: 'short', day: 'numeric' })),
    datasets: [{ label: 'Matchs', data: days.map((d) => (d.games || []).length), backgroundColor: COLORS.accent, borderRadius: 6 }] },
  options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } } });
}
