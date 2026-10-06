// Bankroll : évolution du solde avec les paris réellement posés (/pris), leurs résultats, dépôts et retraits.
import { botFile } from '../api.js';
import { COLORS, canvas, chart, chip, esc, fmtNum, fmtPct, fmtU, frDate, header, kpi, section, table, tone } from '../ui.js';

const STATUT = { 'gagné': 'bg-emerald-500/15 text-emerald-300', 'perdu': 'bg-rose-500/15 text-rose-300',
  'en attente': 'bg-amber-500/15 text-amber-300', 'annulé': 'bg-slate-500/20 text-slate-300',
  'remboursé': 'bg-slate-500/20 text-slate-300', 'dépôt': 'bg-blue-500/15 text-blue-300', 'retrait': 'bg-violet-500/15 text-violet-300' };

export async function render(el) {
  const b = await botFile('bot.json');
  const k = b.bankroll;
  let html = header('Bankroll', 'Les paris réellement posés (bouton ✅ Pris ou <code>/pris</code>), leurs résultats et les mouvements de fonds. 1 U = 1 unité de mise.');
  if (!k || !k.events.length) {
    el.innerHTML = `${html}<div class="card p-5 text-slate-300">Aucun pari posé pour l'instant. Le solde démarre à
      ${fmtNum(k ? k.initial : 100, 0)} U et bougera dès le premier pari résolu.</div>`;
    return;
  }
  const s = k.stats;
  const perf = k.balance - k.initial - (s.depots - s.retraits);
  html += '<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">';
  html += kpi('Bankroll actuelle', `${fmtNum(k.balance, 1)} U`, `départ ${fmtNum(k.initial, 0)} U`, tone(k.balance - k.initial));
  html += kpi('Gain des paris', fmtU(s.gain_paris), `${s.n_joues} paris résolus · ROI ${fmtPct(s.roi)}`, tone(s.gain_paris));
  html += kpi('Réussite', s.reussite == null ? '–' : `${Math.round(s.reussite * 100)} %`, `cote moyenne ${fmtNum(s.cote_moyenne)}`);
  html += kpi('En jeu', `${fmtNum(k.pending.stake, 1)} U`, `${k.pending.n} pari${k.pending.n > 1 ? 's' : ''} en attente`);
  html += kpi('Plus haut', `${fmtNum(s.plus_haut, 1)} U`, 'solde maximal atteint');
  html += kpi('Pire baisse', `${fmtNum(s.drawdown_max, 1)} U`, 'depuis un plus haut', s.drawdown_max > 0 ? 'text-rose-400' : '');
  html += kpi('Mises totales', `${fmtNum(s.mise, 1)} U`, `${s.n_paris} paris posés`);
  html += kpi('Dépôts / retraits', `${fmtNum(s.depots, 1)} / ${fmtNum(s.retraits, 1)} U`, `perf. hors mouvements ${fmtU(perf)}`);
  html += '</div>';
  html += section('Évolution de la bankroll', canvas('bk-curve', 'h-80'),
    '<span class="text-xs text-slate-400">solde en fin de journée · chaque résultat compté au jour du pari</span>');
  html += section('Gain par jour', canvas('bk-daily', 'h-56'));
  html += '<div id="bk-bets"></div>';
  el.innerHTML = html;

  const days = k.daily;
  const labels = days.map((d) => frDate(d.date, { day: 'numeric', month: 'short' }));
  chart('bk-curve', { type: 'line', data: { labels, datasets: [
    { label: 'Bankroll', data: days.map((d) => d.solde), borderColor: COLORS.accent, backgroundColor: 'rgba(59,130,246,.15)',
      fill: true, tension: 0.2, pointRadius: days.length > 60 ? 0 : 3, borderWidth: 2.5 },
    { label: 'Départ', data: days.map(() => k.initial), borderColor: COLORS.slate, borderDash: [6, 6], pointRadius: 0, borderWidth: 1 },
  ] }, options: { scales: { y: { title: { display: true, text: 'U' } } },
    plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${fmtNum(c.parsed.y, 1)} U` } } } } });
  chart('bk-daily', { type: 'bar', data: { labels, datasets: [{ label: 'Gain du jour', data: days.map((d) => d.gain),
    backgroundColor: days.map((d) => (d.gain >= 0 ? COLORS.green : COLORS.red)), borderRadius: 4 }] },
  options: { plugins: { legend: { display: false }, tooltip: { callbacks: {
    label: (c) => `${fmtU(c.parsed.y)} · ${days[c.dataIndex].paris} pari(s), mise ${fmtNum(days[c.dataIndex].mise, 1)} U` } } },
  scales: { y: { title: { display: true, text: 'U' } } } } });

  const box = document.getElementById('bk-bets');
  box.outerHTML = section('Historique', `<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
    <select id="bk-st" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"><option value="">Tous les statuts</option>
      ${Object.keys(STATUT).map((x) => `<option>${x}</option>`).join('')}</select>
    <select id="bk-mk" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"><option value="">Tous les marchés</option>
      ${[...new Set(k.events.map((e) => e.marche))].map((x) => `<option>${esc(x)}</option>`).join('')}</select>
    <input id="bk-q" placeholder="Joueur…" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"></div><div id="bk-tbl"></div>`);
  const cols = [
    { key: 'date', label: 'Date', align: 'left' },
    { key: 'player', label: 'Joueur', align: 'left', html: (r) => `<span class="font-medium text-white">${esc(r.player)}</span>` },
    { key: 'marche', label: 'Marché', align: 'left' },
    { key: 'cote', label: 'Cote', fmt: (v, r) => (r.statut === 'dépôt' || r.statut === 'retrait' ? '–' : fmtNum(v)) },
    { key: 'mise', label: 'Mise', fmt: (v) => (v ? `${fmtNum(v, 1)} U` : '–') },
    { key: 'statut', label: 'Statut', html: (r) => chip(r.statut, STATUT[r.statut]) },
    { key: 'gain', label: 'Gain', html: (r) => `<span class="${tone(r.gain)}">${r.gain == null ? '–' : fmtU(r.gain)}</span>`, sort: (r) => r.gain },
    { key: 'solde', label: 'Solde', fmt: (v) => `${fmtNum(v, 1)} U` },
  ];
  const draw = () => {
    const st = document.getElementById('bk-st').value; const mk = document.getElementById('bk-mk').value;
    const q = document.getElementById('bk-q').value.toLowerCase();
    const rows = k.events.filter((e) => (!st || e.statut === st) && (!mk || e.marche === mk)
      && (!q || String(e.player).toLowerCase().includes(q)));
    const t = document.getElementById('bk-tbl'); t.innerHTML = '';
    t.append(table(cols, rows, { maxH: 'max-h-[560px]' }));
  };
  ['bk-st', 'bk-mk', 'bk-q'].forEach((id) => document.getElementById(id).addEventListener('input', draw));
  draw();
}
