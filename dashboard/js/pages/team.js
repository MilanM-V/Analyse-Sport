// Fiche équipe : bilan, effectif par poste, statistiques des joueurs, matchs et évolution des points.
import { PLURAL, TEAMS, fullName, mmss, nhl, roster, seasonId, standings, teamLogo, today } from '../api.js';
import { COLORS, canvas, chart, chip, destroyCharts, esc, fmtNum, frDate, header, img, kpi, loading, ord, section, segmented, onSegment, table, tone } from '../ui.js';

let tab = 'effectif';

function picker() {
  return header('Équipes', 'Choisissez une équipe.') + `<div class="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">${TEAMS.map((t) =>
    `<a href="#/equipe/${t}" class="card p-3 flex flex-col items-center gap-2 hover:border-accent/60 hover:-translate-y-0.5 transition">
      <img src="${teamLogo(t)}" alt="" class="w-14 h-14" loading="lazy"><span class="text-sm font-semibold">${t}</span></a>`).join('')}</div>`;
}

export async function render(el, [abbr], alive) {
  if (!abbr || !TEAMS.includes(abbr.toUpperCase())) { el.innerHTML = picker(); return; }
  const team = abbr.toUpperCase();
  const season = seasonId();
  el.innerHTML = loading('h-40') + '<div class="mt-6"></div>' + loading('h-96');
  const [std, ros, stats, sched] = await Promise.all([
    nhl(`standings/${today()}`).then(standings).catch(() => []),
    nhl(`roster/${team}/${season}`).then(roster),
    nhl(`club-stats/${team}/${season}/2`).catch(() => ({ skaters: [], goalies: [] })),
    nhl(`club-schedule-season/${team}/${season}`).catch(() => ({ games: [] })),
  ]);
  if (!alive()) return;
  const r = std.find((x) => x.abbr === team);

  const select = `<select id="t-sel" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm">${TEAMS.map((t) => `<option ${t === team ? 'selected' : ''}>${t}</option>`).join('')}</select>`;
  let html = `<div class="flex flex-wrap items-center gap-5 mb-6 fade-in"><img src="${teamLogo(team)}" alt="" class="w-24 h-24 sm:w-28 sm:h-28">
    <div class="flex-1 min-w-[200px]"><h1 class="text-2xl sm:text-3xl font-extrabold">${esc(r?.equipe || team)}</h1>
    <div class="mt-2 flex flex-wrap gap-2">${r ? `${chip(`Conférence ${r.conf === 'Eastern' ? 'Est' : 'Ouest'}`)}${chip(`Division ${esc(r.div)}`)}${chip(`${ord(r.rang)} de la ligue`, 'bg-amber-500/15 text-amber-300')}` : ''}</div></div>${select}</div>`;
  if (r) {
    const mj = Math.max(r.mj, 1);
    html += `<div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 sm:gap-4 mb-6">
      ${kpi('Bilan', `${r.v}-${r.d}-${r.dp}`, `${r.mj} matchs`)}${kpi('Points', r.pts, `${((r.pct ?? 0) * 100).toFixed(1)} % des points possibles`)}
      ${kpi('Buts pour', r.bp, `${fmtNum(r.bp / mj)} / match`)}${kpi('Buts contre', r.bc, `${fmtNum(r.bc / mj)} / match`)}
      ${kpi('Différentiel', `${r.diff > 0 ? '+' : ''}${r.diff}`, '', tone(r.diff))}${kpi('10 derniers', r.l10, `série ${esc(r.serie)}`)}</div>`;
  }
  html += `<div class="mb-4" id="tabs"></div><div id="tab-body"></div>`;
  el.innerHTML = html;
  el.querySelector('#t-sel').addEventListener('change', (e) => { location.hash = `#/equipe/${e.target.value}`; });

  const draw = () => {
    destroyCharts();
    el.querySelector('#tabs').innerHTML = segmented('tab', [{ value: 'effectif', label: '📋 Effectif' }, { value: 'stats', label: '📊 Statistiques' }, { value: 'matchs', label: '🗓️ Matchs' }], tab);
    onSegment(el, 'tab', (v) => { tab = v; draw(); });
    const body = el.querySelector('#tab-body');
    if (tab === 'effectif') body.innerHTML = rosterView(ros, stats);
    if (tab === 'stats') statsView(body, stats);
    if (tab === 'matchs') gamesView(body, sched, team);
  };
  draw();
}

function rosterView(ros, stats) {
  const st = new Map((stats.skaters || []).map((s) => [s.playerId, s]));
  const gs = new Map((stats.goalies || []).map((s) => [s.playerId, s]));
  return ['C', 'L', 'R', 'D', 'G'].map((code) => {
    const g = ros.filter((p) => p.code === code);
    if (!g.length) return '';
    const cards = g.map((p) => {
      const s = st.get(p.id); const k = gs.get(p.id);
      const line = code === 'G' ? (k ? `${k.wins ?? 0} V · ${(k.savePercentage ?? 0).toFixed(3)} % arr.` : '')
        : (s ? `${s.goals} B · ${s.assists} A · ${s.points} Pts` : '');
      return `<a href="#/joueur/${p.id}" class="card p-3 flex items-center gap-3 hover:border-accent/60 hover:-translate-y-0.5 transition">
        <img src="${esc(p.photo)}" alt="" loading="lazy" class="w-14 h-14 rounded-full bg-white/5 object-cover">
        <div class="min-w-0"><div class="font-semibold text-white truncate"><span class="text-slate-500">#${p.num ?? ''}</span> ${esc(p.nom)}</div>
        <div class="text-xs text-slate-400">${p.tir ? `tir ${p.tir} · ` : ''}${p.taille ?? '?'} cm · ${p.poids ?? '?'} kg · ${esc(p.pays || '')}</div>
        ${line ? `<div class="text-xs text-blue-300 mt-0.5">${line}</div>` : ''}</div></a>`;
    }).join('');
    return section(`${PLURAL[code]} <span class="text-slate-400 font-normal text-sm">(${g.length})</span>`,
      `<div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">${cards}</div>`);
  }).join('');
}

function statsView(body, stats) {
  const sk = [...(stats.skaters || [])].sort((a, b) => b.points - a.points);
  if (!sk.length) { body.innerHTML = section('', '<p class="text-slate-400">Pas encore de statistiques cette saison.</p>'); return; }
  body.innerHTML = section('Production offensive (top 15)', canvas('t-off', 'h-[460px]'))
    + section('Joueurs', '<div id="t-sk"></div>') + ((stats.goalies || []).length ? section('Gardiens', '<div id="t-gk"></div>') : '');
  const top = sk.slice(0, 15);
  chart('t-off', { type: 'bar', data: { labels: top.map(fullName), datasets: [
    { label: 'Buts', data: top.map((p) => p.goals), backgroundColor: COLORS.amber, borderRadius: 3 },
    { label: 'Passes', data: top.map((p) => p.assists), backgroundColor: COLORS.accent, borderRadius: 3 }] },
  options: { indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true, grid: { display: false } } },
    onClick: (_e, els) => { if (els[0]) location.hash = `#/joueur/${top[els[0].index].playerId}`; } } });
  const rows = sk.map((p) => ({ ...p, nom: fullName(p) }));
  body.querySelector('#t-sk').append(table([
    { key: 'nom', label: 'Joueur', align: 'left', html: (p) => `<span class="inline-flex items-center gap-2">${img(p.headshot, 'w-7 h-7 rounded-full bg-white/5')}<span class="font-medium text-white">${esc(p.nom)}</span></span>` },
    { key: 'positionCode', label: 'Poste' }, { key: 'gamesPlayed', label: 'MJ' }, { key: 'goals', label: 'B' }, { key: 'assists', label: 'A' },
    { key: 'points', label: 'Pts', html: (p) => `<b class="text-white">${p.points}</b>`, sort: (p) => p.points },
    { key: 'plusMinus', label: '+/-', html: (p) => `<span class="${tone(p.plusMinus)}">${p.plusMinus > 0 ? '+' : ''}${p.plusMinus}</span>`, sort: (p) => p.plusMinus },
    { key: 'shots', label: 'Tirs' }, { key: 'shootingPctg', label: '% tir', fmt: (v) => (v == null ? '–' : (100 * v).toFixed(1)) },
    { key: 'powerPlayGoals', label: 'BAN' }, { key: 'avgTimeOnIcePerGame', label: 'TG moy.', fmt: (v) => mmss(v) },
  ], rows, { href: (p) => `#/joueur/${p.playerId}`, sortKey: 'points', maxH: 'max-h-[620px]' }));
  if ((stats.goalies || []).length) {
    body.querySelector('#t-gk').append(table([
      { key: 'nom', label: 'Gardien', align: 'left', html: (p) => `<span class="font-medium text-white">${esc(fullName(p))}</span>`, sort: (p) => fullName(p) },
      { key: 'gamesPlayed', label: 'MJ' }, { key: 'wins', label: 'V' }, { key: 'losses', label: 'D' }, { key: 'overtimeLosses', label: 'DP' },
      { key: 'savePercentage', label: '% arrêts', fmt: (v) => fmtNum(v, 3) }, { key: 'goalsAgainstAverage', label: 'Moy. contre', fmt: (v) => fmtNum(v) },
      { key: 'shutouts', label: 'Blanch.' },
    ], stats.goalies, { href: (p) => `#/joueur/${p.playerId}`, sortKey: 'gamesPlayed' }));
  }
}

function gamesView(body, sched, team) {
  const games = (sched.games || []).filter((g) => g.gameType === 2).map((g) => {
    const home = g.homeTeam.abbrev === team;
    const me = home ? g.homeTeam : g.awayTeam; const op = home ? g.awayTeam : g.homeTeam;
    const done = ['OFF', 'FINAL'].includes(g.gameState) && me.score != null;
    const ot = ['OT', 'SO'].includes(g.gameOutcome?.lastPeriodType);
    const res = !done ? '' : me.score > op.score ? 'V' : ot ? 'DP' : 'D';
    return { date: g.gameDate, opp: op.abbrev, lieu: home ? 'Domicile' : 'Extérieur', bp: me.score, bc: op.score, res, ot, utc: g.startTimeUTC };
  });
  const done = games.filter((g) => g.res);
  let cum = 0;
  const pts = done.map((g) => (cum += g.res === 'V' ? 2 : g.res === 'DP' ? 1 : 0));
  const RES = { V: 'bg-emerald-500/15 text-emerald-300', D: 'bg-rose-500/15 text-rose-300', DP: 'bg-amber-500/15 text-amber-300' };
  body.innerHTML = (done.length ? `<div class="grid grid-cols-1 xl:grid-cols-2 gap-6">${section('Évolution des points', canvas('t-pts', 'h-64'))}${section('Écart de buts par match', canvas('t-diff', 'h-64'))}</div>` : '')
    + section(`Calendrier ${done.length ? `<span class="text-sm font-normal text-slate-400">· ${done.length} joués sur ${games.length}</span>` : ''}`, '<div id="t-games"></div>');
  if (done.length) {
    chart('t-pts', { type: 'line', data: { labels: done.map((g) => g.date.slice(5)), datasets: [{ label: 'Points cumulés', data: pts,
      borderColor: COLORS.accent, backgroundColor: 'rgba(59,130,246,.15)', fill: true, tension: 0.3, pointRadius: 2 }] },
    options: { plugins: { legend: { display: false } } } });
    chart('t-diff', { type: 'bar', data: { labels: done.map((g) => `${g.date.slice(5)} ${g.opp}`), datasets: [{ label: 'Écart', data: done.map((g) => g.bp - g.bc),
      backgroundColor: done.map((g) => (g.bp > g.bc ? COLORS.green : COLORS.red)), borderRadius: 3 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { display: false } } } });
  }
  body.querySelector('#t-games').append(table([
    { key: 'date', label: 'Date', align: 'left', fmt: (v) => frDate(v, { day: '2-digit', month: 'short' }) , sort: (g) => g.date },
    { key: 'opp', label: 'Adversaire', align: 'left', html: (g) => `<span class="inline-flex items-center gap-2">${img(teamLogo(g.opp), 'w-6 h-6')}${g.lieu === 'Domicile' ? 'vs' : '@'} ${esc(g.opp)}</span>` },
    { key: 'lieu', label: 'Lieu', align: 'left' },
    { key: 'score', label: 'Score', html: (g) => (g.res ? `${g.bp} – ${g.bc}${g.ot ? ' (prol.)' : ''}` : '–'), sort: (g) => g.bp },
    { key: 'res', label: 'Résultat', html: (g) => (g.res ? chip(g.res, RES[g.res]) : '<span class="text-slate-500">à venir</span>') },
  ], games, { href: (g) => `#/resultats/${g.date}`, sortKey: 'date', desc: false, maxH: 'max-h-[560px]' }));
}
