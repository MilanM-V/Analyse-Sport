// Le bot : KPIs, mode découverte, projection simulée, gain cumulé, picks filtrables.
import { botFile } from '../api.js';
import { COLORS, canvas, chart, chip, esc, fmtNum, fmtPct, fmtU, header, kpi, section, table, tone } from '../ui.js';

const STATUT = { 'gagné': 'bg-emerald-500/15 text-emerald-300', 'perdu': 'bg-rose-500/15 text-rose-300',
  'en attente': 'bg-amber-500/15 text-amber-300', 'annulé': 'bg-slate-500/20 text-slate-300', 'non pris': 'bg-slate-500/20 text-slate-400' };

export async function render(el) {
  const b = await botFile('bot.json');
  const s = b.summary;
  const mode = b.mode.paper ? chip('PAPER · aucun argent réel', 'bg-amber-500/15 text-amber-300') : chip('RÉEL', 'bg-emerald-500/15 text-emerald-300');
  let html = header('Performances du bot', `${mode} <span class="ml-2">Stratégie « ${esc(b.mode.strategy)} »</span>`);

  html += '<div class="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4 mb-6">';
  if (s) {
    html += kpi('Gain net', fmtU(s.gain), `${s.n_joues} paris résolus`, tone(s.gain));
    html += kpi('ROI', fmtPct(s.roi), `mise totale ${fmtNum(s.mise, 1)} U`, tone(s.roi));
    html += kpi('Réussite', s.reussite == null ? '–' : `${Math.round(s.reussite * 100)} %`, `${s.en_attente} en attente`);
    html += kpi('EV de clôture', fmtPct(s.ev_cloture), `${s.n_ev_cloture} / ${b.mode.go_live_min_bets} paris requis`, tone(s.ev_cloture));
    html += kpi('Picks envoyés', s.n_picks, 'buteur + passeur');
  } else {
    html += `<div class="col-span-2 lg:col-span-5 card p-5 text-slate-300">Aucun pick pour l'instant.</div>`;
  }
  html += '</div>';

  // Progression vers le critère de passage en réel
  if (s) {
    const pct = Math.min(100, (100 * s.n_ev_cloture) / b.mode.go_live_min_bets);
    html += section('Vers le passage en réel', `<div class="text-sm text-slate-300 mb-2">${s.n_ev_cloture} paris avec cote de clôture sur ${b.mode.go_live_min_bets}.
      Le passage en réel est validé si l'EV de clôture reste positive (borne basse de l'IC 95 % &gt; 0).</div>
      <div class="h-3 rounded-full bg-white/5 overflow-hidden"><div class="h-full bg-gradient-to-r from-blue-500 to-violet-500" style="width:${pct}%"></div></div>`);
  }

  // Mode découverte
  if (b.early) {
    const e = b.summary_early;
    const body = e
      ? `<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">${kpi('Gain', fmtU(e.gain), `${e.n_joues} paris résolus`, tone(e.gain))}
         ${kpi('ROI', fmtPct(e.roi), `mise ${fmtNum(e.mise, 1)} U`, tone(e.roi))}${kpi('Picks', e.n_picks, `${e.en_attente} en attente`)}
         ${kpi('EV de clôture', fmtPct(e.ev_cloture), 'hors critère réel', tone(e.ev_cloture))}</div>`
      : '<p class="text-sm text-slate-400">Aucun pick découverte pour l\'instant.</p>';
    html += section(`🧪 Mode découverte ${b.early.enabled ? chip('actif') : chip('désactivé', 'bg-slate-500/20 text-slate-300')}`,
      `<p class="text-sm text-slate-400 mb-4">Joueurs à moins de 10 matchs cette saison, estimés aussi avec la saison passée.
       EV ≥ ${Math.round(b.early.ev_min * 100)} %, mise × ${b.early.stake_mult}. Suivi à part, il ne compte pas pour le passage en réel.</p>${body}`);
  }

  // Projection simulée
  if (b.projection) {
    const v = b.projection.val; const c = b.projection.ctl;
    html += section('📈 Ce que la simulation prévoit pour une saison',
      `<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">${kpi('Saison 2023-24', fmtU(v.profit_season), `ROI ${fmtPct(v.roi)}`, tone(v.profit_season))}
       ${kpi('Début 2024-25', fmtU(c.profit_season), `ROI ${fmtPct(c.roi)} · ramené à une saison`, tone(c.profit_season))}
       ${kpi('Pire série de pertes', `${fmtNum(Math.max(v.max_dd, c.max_dd), 1)} U`, 'drawdown maximal')}
       ${kpi('Paris par match', fmtNum(v.per_game), '≈ 1 match sur 2')}</div>
       <p class="mt-3 text-xs text-slate-400">Backtest au prix Winamax calibré, Kelly 1/6, bankroll 100 U. Ce n'est pas une garantie :
       face à Pinnacle, ces paris valaient ${fmtPct(v.ev_pin)} en 2023-24. Seule l'EV de clôture des vrais paris tranchera.</p>`);
  }

  html += '<div id="cum"></div><div id="picks"></div><div id="markets"></div>';
  el.innerHTML = html;

  // Gain cumulé
  const dates = [...new Set(b.cumulative.map((r) => r.date))].sort();
  if (dates.length >= 2) {
    document.getElementById('cum').outerHTML = section('Gain cumulé', canvas('cum-chart', 'h-72'));
    const series = [...new Set(b.cumulative.map((r) => r.marche))];
    const col = { Total: COLORS.accent, Buteur: COLORS.amber, Passeur: COLORS.violet };
    chart('cum-chart', { type: 'line', data: { labels: dates, datasets: series.map((m) => {
      let last = null;
      return { label: m, borderColor: col[m] || COLORS.cyan, backgroundColor: col[m] || COLORS.cyan, tension: 0.25, pointRadius: 2,
        borderWidth: m === 'Total' ? 3 : 2,
        data: dates.map((d) => { const r = b.cumulative.find((x) => x.date === d && x.marche === m); if (r) last = r.gain_cumule; return last; }) };
    }) }, options: { scales: { y: { title: { display: true, text: 'U' } } } } });
  }

  // Picks
  if (b.picks.length) {
    const box = document.getElementById('picks');
    box.outerHTML = section('Picks', `<div class="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
      <select id="f-mk" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"><option value="">Tous les marchés</option><option>Buteur</option><option>Passeur</option></select>
      <select id="f-st" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"><option value="">Tous les statuts</option>${Object.keys(STATUT).map((x) => `<option>${x}</option>`).join('')}</select>
      <select id="f-ph" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"><option value="">Normal + découverte</option><option value="normal">Mode normal</option><option value="early">🧪 Découverte</option></select>
      <input id="f-q" placeholder="Joueur ou équipe…" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"></div><div id="picks-tbl"></div>`);
    const cols = [
      { key: 'ref', label: 'Réf.', align: 'left' }, { key: 'date', label: 'Date', align: 'left' },
      { key: 'marche', label: 'Marché', align: 'left' },
      { key: 'joueur', label: 'Joueur', align: 'left', html: (r) => `<span class="font-medium text-white">${esc(r.joueur)}</span>${r.phase === 'early' ? ' 🧪' : ''}` },
      { key: 'equipe', label: 'Équipe', align: 'left', html: (r) => `<a href="#/equipe/${esc(r.equipe)}" class="hover:text-accent">${esc(r.equipe)}</a> <span class="text-slate-500">vs ${esc(r.adversaire)}</span>` },
      { key: 'cote_seuil', label: 'Cote seuil', fmt: (v) => fmtNum(v) }, { key: 'cote', label: 'Cote', fmt: (v) => fmtNum(v) },
      { key: 'mise', label: 'Mise', fmt: (v) => `${fmtNum(v, 1)} U` },
      { key: 'p_final', label: 'Proba', fmt: (v) => (v == null ? '–' : `${Math.round(v * 100)} %`) },
      { key: 'statut', label: 'Statut', html: (r) => chip(r.statut, STATUT[r.statut]) },
      { key: 'profit', label: 'Gain', html: (r) => `<span class="${tone(r.profit)}">${r.profit == null ? '–' : fmtU(r.profit)}</span>`, sort: (r) => r.profit },
      { key: 'ev_cloture', label: 'EV clôture', html: (r) => `<span class="${tone(r.ev_cloture)}">${fmtPct(r.ev_cloture)}</span>`, sort: (r) => r.ev_cloture },
    ];
    const draw = () => {
      const mk = document.getElementById('f-mk').value; const st = document.getElementById('f-st').value;
      const ph = document.getElementById('f-ph').value; const q = document.getElementById('f-q').value.toLowerCase();
      const rows = b.picks.filter((p) => (!mk || p.marche === mk) && (!st || p.statut === st) && (!ph || p.phase === ph)
        && (!q || `${p.joueur} ${p.equipe}`.toLowerCase().includes(q)));
      const t = document.getElementById('picks-tbl'); t.innerHTML = '';
      t.append(table(cols, rows, { maxH: 'max-h-[560px]' }));
    };
    ['f-mk', 'f-st', 'f-ph', 'f-q'].forEach((id) => document.getElementById(id).addEventListener('input', draw));
    draw();
  }

  // Par marché
  if (b.by_market.length) {
    const box = document.getElementById('markets');
    box.outerHTML = section('Par marché (paris résolus)', '<div id="mk-tbl"></div>');
    document.getElementById('mk-tbl').append(table([
      { key: 'marche', label: 'Marché', align: 'left' }, { key: 'paris', label: 'Paris' },
      { key: 'mise', label: 'Mise', fmt: (v) => `${fmtNum(v, 1)} U` },
      { key: 'gain', label: 'Gain', html: (r) => `<span class="${tone(r.gain)}">${fmtU(r.gain)}</span>`, sort: (r) => r.gain },
      { key: 'roi', label: 'ROI', html: (r) => `<span class="${tone(r.roi)}">${fmtPct(r.roi)}</span>`, sort: (r) => r.roi },
    ], b.by_market));
  }
}
