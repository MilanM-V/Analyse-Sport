// Fiche joueur : recherche, identité, carrière, saison match par match, historique par saison, vu par le bot.
import { POSITIONS, allPlayers, botFile, name, nhl, seasonHistory, seasonId, seasonLabel, teamLogo } from '../api.js';
import { COLORS, canvas, chart, chip, destroyCharts, esc, fmtNum, fmtPct, fmtU, frDate, header, img, kpi, loading, onSegment, ord, section, segmented, table, tone } from '../ui.js';

let tab = 'saison';

async function searchBox(el) {
  el.insertAdjacentHTML('afterbegin', `<div class="relative mb-6 max-w-xl"><input id="p-q" autocomplete="off" placeholder="🔎 Rechercher un joueur (nom ou équipe)…"
    class="w-full bg-white/5 border border-line rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-accent">
    <div id="p-res" class="hidden absolute z-20 mt-1 w-full card max-h-96 overflow-auto scroll-thin p-1"></div></div>`);
  const q = el.querySelector('#p-q'); const res = el.querySelector('#p-res');
  let players = null;
  q.addEventListener('focus', async () => {
    if (players) return;
    res.classList.remove('hidden'); res.innerHTML = '<div class="p-3 text-sm text-slate-400">Chargement des 32 effectifs…</div>';
    players = await allPlayers();
    q.dispatchEvent(new Event('input'));
  });
  q.addEventListener('input', () => {
    if (!players) return;
    const s = q.value.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    if (!s) { res.classList.add('hidden'); return; }
    const hits = players.filter((p) => `${p.nom} ${p.equipe}`.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(s)).slice(0, 30);
    res.classList.remove('hidden');
    res.innerHTML = hits.length ? hits.map((p) => `<a href="#/joueur/${p.id}" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/5">
      ${img(p.photo, 'w-8 h-8 rounded-full bg-white/5')}<span class="flex-1 text-sm text-white">${esc(p.nom)}</span>
      <span class="text-xs text-slate-400">${esc(p.poste)}</span>${img(teamLogo(p.equipe), 'w-6 h-6')}</a>`).join('')
      : '<div class="p-3 text-sm text-slate-400">Aucun joueur trouvé.</div>';
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('#p-q, #p-res')) res.classList.add('hidden'); });
}

export async function render(el, [id], alive) {
  if (!id) {
    el.innerHTML = header('Joueurs', 'Recherchez un joueur, ou ouvrez-le depuis une équipe, le classement des meilleurs ou les résultats.');
    await searchBox(el);
    return;
  }
  el.innerHTML = loading('h-48') + '<div class="mt-6"></div>' + loading('h-80');
  const season = seasonId();
  const [p, log, bot, db] = await Promise.all([
    nhl(`player/${id}/landing`),
    nhl(`player/${id}/game-log/${season}/2`).catch(() => ({ gameLog: [] })),
    botFile('bot.json').catch(() => null),
    botFile('db.json').catch(() => null),
  ]);
  if (!alive()) return;
  const goalie = p.position === 'G';
  const nom = `${name(p.firstName)} ${name(p.lastName)}`.trim();
  const car = p.careerTotals?.regularSeason || {};
  const d = p.draftDetails;

  el.innerHTML = `<div class="card p-5 sm:p-6 mb-6 fade-in overflow-hidden relative">
    <img src="${teamLogo(p.currentTeamAbbrev || 'NHL')}" alt="" class="absolute -right-10 -top-10 w-64 h-64 opacity-[.06] pointer-events-none">
    <div class="flex flex-wrap items-center gap-5 relative">
      <img src="${esc(p.headshot)}" alt="" class="w-28 h-28 sm:w-32 sm:h-32 rounded-2xl bg-white/5 object-cover">
      <div class="flex-1 min-w-[220px]"><h1 class="text-2xl sm:text-4xl font-extrabold">${esc(nom)} <span class="text-slate-500 text-2xl">#${p.sweaterNumber ?? ''}</span></h1>
        <div class="mt-2 flex flex-wrap gap-2">${chip(POSITIONS[p.position] || p.position)}
          ${p.currentTeamAbbrev ? `<a href="#/equipe/${p.currentTeamAbbrev}" class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs bg-white/5 hover:bg-white/10">${img(teamLogo(p.currentTeamAbbrev), 'w-4 h-4')}${esc(name(p.fullTeamName) || p.currentTeamAbbrev)}</a>` : ''}</div>
        <div class="mt-3 text-sm text-slate-400 leading-relaxed">Né le ${frDate(p.birthDate, { day: 'numeric', month: 'long', year: 'numeric' })} à ${esc(name(p.birthCity))} (${esc(p.birthCountry || '')})
          · ${p.heightInCentimeters ?? '?'} cm · ${p.weightInKilograms ?? '?'} kg · ${goalie ? 'attrape' : 'tire'} ${esc(p.shootsCatches || '?')}
          <br>${d ? `Repêché en ${d.year} par ${esc(d.teamAbbrev)}, ${ord(d.round)} tour, ${ord(d.overallPick)} au total` : 'Non repêché'}</div></div></div></div>`;
  el.insertAdjacentHTML('beforeend', `<div class="grid grid-cols-2 md:grid-cols-5 gap-3 sm:gap-4 mb-6">${goalie
    ? `${kpi('Matchs (carrière)', car.gamesPlayed ?? '–')}${kpi('Victoires', car.wins ?? '–')}${kpi('% arrêts', fmtNum(car.savePctg, 3))}${kpi('Moy. buts contre', fmtNum(car.goalsAgainstAvg))}${kpi('Blanchissages', car.shutouts ?? '–')}`
    : `${kpi('Matchs (carrière)', car.gamesPlayed ?? '–')}${kpi('Buts', car.goals ?? '–')}${kpi('Passes', car.assists ?? '–')}${kpi('Points', car.points ?? '–')}${kpi('Points / match', car.gamesPlayed ? fmtNum(car.points / car.gamesPlayed) : '–')}`}</div>
    <div id="tabs" class="mb-4"></div><div id="tab-body"></div>`);
  await searchBox(el);

  const hist = seasonHistory(p);
  const games = [...(log.gameLog || [])].sort((a, b) => a.gameDate.localeCompare(b.gameDate));
  const picks = (bot?.picks || []).filter((x) => x.joueur === nom);
  const evals = evalRows(db, nom);

  const draw = () => {
    destroyCharts();
    el.querySelector('#tabs').innerHTML = segmented('ptab', [{ value: 'saison', label: `📈 Saison ${seasonLabel(season)}` },
      { value: 'historique', label: '🗂️ Historique par saison' }, { value: 'bot', label: `🤖 Vu par le bot${picks.length ? ` (${picks.length})` : ''}` }], tab);
    onSegment(el, 'ptab', (v) => { tab = v; draw(); });
    const body = el.querySelector('#tab-body');
    if (tab === 'saison') seasonView(body, games, goalie);
    if (tab === 'historique') historyView(body, hist, goalie);
    if (tab === 'bot') botView(body, picks, evals);
  };
  draw();
}

function seasonView(body, games, goalie) {
  if (!games.length) { body.innerHTML = section('', '<p class="text-slate-400">Aucun match joué cette saison. L\'historique par saison est dans l\'onglet suivant.</p>'); return; }
  if (goalie) {
    body.innerHTML = section('Match par match', '<div id="g-tbl"></div>');
    body.querySelector('#g-tbl').append(table([
      { key: 'gameDate', label: 'Date', align: 'left' }, { key: 'opponentAbbrev', label: 'Adversaire', align: 'left' },
      { key: 'decision', label: 'Décision' }, { key: 'shotsAgainst', label: 'Tirs contre' }, { key: 'goalsAgainst', label: 'Buts contre' },
      { key: 'savePctg', label: '% arrêts', fmt: (v) => fmtNum(v, 3) }, { key: 'toi', label: 'TG' },
    ], games, { sortKey: 'gameDate' }));
    return;
  }
  let cum = 0;
  const tot = games.reduce((a, g) => ({ b: a.b + g.goals, a: a.a + g.assists, t: a.t + (g.shots || 0) }), { b: 0, a: 0, t: 0 });
  body.innerHTML = `<div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6">${kpi('Matchs', games.length)}${kpi('Buts', tot.b, `${fmtNum(tot.b / games.length)} / match`)}
    ${kpi('Passes', tot.a, `${fmtNum(tot.a / games.length)} / match`)}${kpi('Tirs', tot.t, tot.t ? `${((100 * tot.b) / tot.t).toFixed(1)} % de réussite` : '')}</div>`
    + section('Match par match', canvas('p-season', 'h-72')) + section('Détail', '<div id="p-games"></div>');
  chart('p-season', { data: { labels: games.map((g) => `${g.gameDate.slice(5)} ${g.opponentAbbrev}`), datasets: [
    { type: 'bar', label: 'Buts', data: games.map((g) => g.goals), backgroundColor: COLORS.amber, stack: 's', borderRadius: 3, order: 1, maxBarThickness: 42 },
    { type: 'bar', label: 'Passes', data: games.map((g) => g.assists), backgroundColor: COLORS.accent, stack: 's', borderRadius: 3, order: 1, maxBarThickness: 42 },
    { type: 'line', label: 'Points cumulés', data: games.map((g) => (cum += g.points)), borderColor: COLORS.violet, yAxisID: 'y2', tension: 0.3, pointRadius: 2, order: 0 }] },
  options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { precision: 0 } }, y2: { position: 'right', grid: { display: false } } } } });
  body.querySelector('#p-games').append(table([
    { key: 'gameDate', label: 'Date', align: 'left' },
    { key: 'opponentAbbrev', label: 'Adversaire', align: 'left', html: (g) => `<span class="inline-flex items-center gap-2">${img(teamLogo(g.opponentAbbrev), 'w-5 h-5')}${g.homeRoadFlag === 'H' ? 'vs' : '@'} ${esc(g.opponentAbbrev)}</span>` },
    { key: 'goals', label: 'B' }, { key: 'assists', label: 'A' }, { key: 'points', label: 'Pts', html: (g) => `<b class="text-white">${g.points}</b>`, sort: (g) => g.points },
    { key: 'plusMinus', label: '+/-', html: (g) => `<span class="${tone(g.plusMinus)}">${g.plusMinus > 0 ? '+' : ''}${g.plusMinus}</span>`, sort: (g) => g.plusMinus },
    { key: 'shots', label: 'Tirs' }, { key: 'powerPlayGoals', label: 'BAN' }, { key: 'toi', label: 'TG' },
  ], games, { href: (g) => `#/resultats/${g.gameDate}`, sortKey: 'gameDate' }));
}

function historyView(body, hist, goalie) {
  if (!hist.length) { body.innerHTML = section('', '<p class="text-slate-400">Pas d\'historique NHL.</p>'); return; }
  body.innerHTML = section('Saison régulière NHL, saison par saison', canvas('p-hist', 'h-80')) + section('Détail', '<div id="p-hist-tbl"></div>');
  if (goalie) {
    chart('p-hist', { data: { labels: hist.map((h) => h.saison), datasets: [
      { type: 'bar', label: 'Matchs', data: hist.map((h) => h.mj), backgroundColor: COLORS.accent, borderRadius: 3, order: 1, maxBarThickness: 42 },
      { type: 'line', label: '% arrêts', data: hist.map((h) => h.svp), borderColor: COLORS.amber, yAxisID: 'y2', tension: 0.3, order: 0 }] },
    options: { scales: { y2: { position: 'right', grid: { display: false } } } } });
  } else {
    chart('p-hist', { data: { labels: hist.map((h) => h.saison), datasets: [
      { type: 'bar', label: 'Buts', data: hist.map((h) => h.b), backgroundColor: COLORS.amber, stack: 's', borderRadius: 3, order: 1, maxBarThickness: 42 },
      { type: 'bar', label: 'Passes', data: hist.map((h) => h.a), backgroundColor: COLORS.accent, stack: 's', borderRadius: 3, order: 1, maxBarThickness: 42 },
      { type: 'line', label: 'Points / match', data: hist.map((h) => h.ppm), borderColor: COLORS.violet, yAxisID: 'y2', tension: 0.3, pointRadius: 3, order: 0 }] },
    options: { scales: { x: { stacked: true }, y: { stacked: true }, y2: { position: 'right', grid: { display: false }, beginAtZero: true } } } });
  }
  const cols = goalie
    ? [{ key: 'saison', label: 'Saison', align: 'left' }, { key: 'equipe', label: 'Équipe', align: 'left' }, { key: 'mj', label: 'MJ' }, { key: 'w', label: 'V' },
      { key: 'svp', label: '% arrêts', fmt: (v) => fmtNum(v, 3) }, { key: 'gaa', label: 'Moy. contre', fmt: (v) => fmtNum(v) }]
    : [{ key: 'saison', label: 'Saison', align: 'left' }, { key: 'equipe', label: 'Équipe', align: 'left' }, { key: 'mj', label: 'MJ' },
      { key: 'b', label: 'B' }, { key: 'a', label: 'A' }, { key: 'pts', label: 'Pts', html: (h) => `<b class="text-white">${h.pts}</b>`, sort: (h) => h.pts },
      { key: 'ppm', label: 'Pts / match', fmt: (v) => fmtNum(v) }, { key: 'pm', label: '+/-' }, { key: 'tirs', label: 'Tirs' },
      { key: 'pctTir', label: '% tir', fmt: (v) => fmtNum(v, 1) }, { key: 'ban', label: 'BAN' }, { key: 'toi', label: 'TG moy.' }];
  body.querySelector('#p-hist-tbl').append(table(cols, hist, { sortKey: 'saison' }));
}

function evalRows(db, nom) {
  const t = db?.['bot_database.db']?.players;
  if (!t) return [];
  const i = t.columns.indexOf('joueur');
  return t.rows.filter((r) => r[i] === nom).map((r) => Object.fromEntries(t.columns.map((c, k) => [c, r[k]])));
}

function botView(body, picks, evals) {
  const STATUT = { 'gagné': 'bg-emerald-500/15 text-emerald-300', 'perdu': 'bg-rose-500/15 text-rose-300', 'en attente': 'bg-amber-500/15 text-amber-300' };
  if (!picks.length && !evals.length) { body.innerHTML = section('', '<p class="text-slate-400">Le bot n\'a encore jamais évalué ce joueur.</p>'); return; }
  const gain = picks.reduce((s, x) => s + (x.profit || 0), 0);
  body.innerHTML = (picks.length ? section(`Picks du bot <span class="text-sm font-normal ${tone(gain)}">· ${fmtU(gain)}</span>`, '<div id="b-picks"></div>') : '')
    + (evals.length ? section('Évaluations du bot (probabilités du modèle)', '<div id="b-evals"></div>') : '');
  if (picks.length) {
    body.querySelector('#b-picks').append(table([
      { key: 'ref', label: 'Réf.', align: 'left' }, { key: 'date', label: 'Date', align: 'left' }, { key: 'marche', label: 'Marché', align: 'left', html: (x) => `${x.marche}${x.phase === 'early' ? ' 🧪' : ''}` },
      { key: 'cote_seuil', label: 'Cote seuil', fmt: (v) => fmtNum(v) }, { key: 'cote', label: 'Cote', fmt: (v) => fmtNum(v) },
      { key: 'p_final', label: 'Proba', fmt: (v) => (v == null ? '–' : `${Math.round(v * 100)} %`) },
      { key: 'statut', label: 'Statut', html: (x) => chip(x.statut, STATUT[x.statut] || 'bg-slate-500/20 text-slate-300') },
      { key: 'profit', label: 'Gain', html: (x) => `<span class="${tone(x.profit)}">${x.profit == null ? '–' : fmtU(x.profit)}</span>`, sort: (x) => x.profit },
      { key: 'ev_cloture', label: 'EV clôture', fmt: (v) => fmtPct(v) },
    ], picks, { sortKey: 'date' }));
  }
  if (evals.length) {
    const pct = (v) => (v == null ? '–' : `${Math.round(v * 100)} %`);
    body.querySelector('#b-evals').append(table([
      { key: 'date', label: 'Date', align: 'left' }, { key: 'adversaire', label: 'Adversaire', align: 'left' },
      { key: 'score_but', label: 'P(but)', fmt: pct }, { key: 'score_assist', label: 'P(passe)', fmt: pct },
      { key: 'picked_but', label: 'Retenu but', fmt: (v) => (v ? '✅' : '') }, { key: 'picked_assist', label: 'Retenu passe', fmt: (v) => (v ? '✅' : '') },
      { key: 'cote', label: 'Cote', fmt: (v) => fmtNum(v) },
    ], evals, { sortKey: 'date', maxH: 'max-h-[480px]' }));
  }
}
