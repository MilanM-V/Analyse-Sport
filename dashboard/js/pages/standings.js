// Classement NHL : ligue, conférences, divisions ; graphiques des points et attaque / défense.
import { nhl, standings, teamLogo, today } from '../api.js';
import { COLORS, canvas, chart, esc, header, img, loading, onSegment, section, segmented, table, tone } from '../ui.js';

let view = 'Ligue';

const COLS = [
  { key: 'n', label: '#', align: 'left', sort: (r) => r.n },
  { key: 'equipe', label: 'Équipe', align: 'left', html: (r) => `<span class="inline-flex items-center gap-2">${img(teamLogo(r.abbr), 'w-7 h-7')}<span class="font-medium text-white">${esc(r.equipe)}</span></span>` },
  { key: 'mj', label: 'MJ' }, { key: 'v', label: 'V' }, { key: 'd', label: 'D' }, { key: 'dp', label: 'DP' },
  { key: 'pts', label: 'Pts', html: (r) => `<b class="text-white">${r.pts}</b>`, sort: (r) => r.pts },
  { key: 'pct', label: '% Pts', html: (r) => `<div class="flex items-center justify-end gap-2"><div class="w-16 h-1.5 rounded bg-white/10"><div class="h-full rounded bg-accent" style="width:${Math.round((r.pct || 0) * 100)}%"></div></div>${(r.pct ?? 0).toFixed(3)}</div>`, sort: (r) => r.pct },
  { key: 'bp', label: 'BP' }, { key: 'bc', label: 'BC' },
  { key: 'diff', label: 'Diff', html: (r) => `<span class="${tone(r.diff)}">${r.diff > 0 ? '+' : ''}${r.diff}</span>`, sort: (r) => r.diff },
  { key: 'l10', label: '10 derniers' }, { key: 'serie', label: 'Série' }, { key: 'dom', label: 'Domicile' }, { key: 'ext', label: 'Extérieur' },
];

const rank = (rows) => [...rows].sort((a, b) => (b.pts - a.pts) || (b.pct - a.pct)).map((r, i) => ({ ...r, n: i + 1 }));

export async function render(el, _p, alive) {
  el.innerHTML = header('Classement NHL', 'Cliquez sur une équipe pour ouvrir sa fiche.') + loading('h-96');
  const df = standings(await nhl(`standings/${today()}`));
  if (!alive()) return;
  if (!df.length) { el.innerHTML = header('Classement NHL') + section('', '<p class="text-slate-400">Classement indisponible.</p>'); return; }

  el.innerHTML = header('Classement NHL', 'Cliquez sur une équipe pour ouvrir sa fiche.')
    + `<div class="mb-4" id="seg"></div><div id="groups"></div>
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">${section('Points par équipe', canvas('pts-chart', 'h-[720px]'))}
    ${section('Attaque contre défense', `<p class="text-xs text-slate-400 mb-2">En haut à droite : beaucoup de buts marqués, peu encaissés.</p>${canvas('ad-chart', 'h-[660px]')}`)}</div>`;

  const draw = () => {
    el.querySelector('#seg').innerHTML = segmented('std', ['Ligue', 'Conférences', 'Divisions'].map((v) => ({ value: v, label: v })), view);
    onSegment(el, 'std', (v) => { view = v; draw(); });
    const groups = view === 'Ligue' ? [['NHL', df]]
      : Object.entries(df.reduce((acc, r) => { const k = view === 'Conférences' ? r.conf : r.div; (acc[k] ||= []).push(r); return acc; }, {}));
    const box = el.querySelector('#groups'); box.innerHTML = '';
    for (const [name, rows] of groups) {
      const s = document.createElement('div');
      s.innerHTML = section(esc(name), '<div class="t"></div>');
      s.querySelector('.t').append(table(COLS, rank(rows), { href: (r) => `#/equipe/${r.abbr}`, sortKey: 'n', desc: false }));
      box.append(s.firstElementChild);
    }
  };
  draw();

  const sorted = [...df].sort((a, b) => b.pts - a.pts);
  const confColor = (c) => (c === 'Eastern' ? COLORS.accent : COLORS.violet);
  chart('pts-chart', { type: 'bar', data: { labels: sorted.map((r) => r.abbr), datasets: [{ label: 'Points', data: sorted.map((r) => r.pts),
    backgroundColor: sorted.map((r) => confColor(r.conf)), borderRadius: 4 }] },
  options: { indexAxis: 'y', plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => sorted[i[0].dataIndex].equipe } } },
    scales: { y: { grid: { display: false } } }, onClick: (_e, els) => { if (els[0]) location.hash = `#/equipe/${sorted[els[0].index].abbr}`; } } });

  const logos = df.map((r) => { const im = new Image(30, 30); im.src = teamLogo(r.abbr); return im; });
  chart('ad-chart', { type: 'scatter', data: { datasets: [{ label: 'Équipes', data: df.map((r) => ({ x: r.bp, y: r.bc, r })), pointStyle: logos, radius: 15, hoverRadius: 18 }] },
    options: { interaction: { mode: 'nearest', intersect: true }, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (c) => `${c.raw.r.equipe} : ${c.raw.x} pour, ${c.raw.y} contre` } } },
    scales: { x: { title: { display: true, text: 'Buts pour' } }, y: { reverse: true, title: { display: true, text: 'Buts contre' } } },
    onClick: (_e, els) => { if (els[0]) location.hash = `#/equipe/${df[els[0].index].abbr}`; } } });
}

