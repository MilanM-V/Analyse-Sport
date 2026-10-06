// Routeur (#/page/param) et navigation du dashboard.
import { botFile } from './api.js';
import { destroyCharts, errorBox } from './ui.js';
import * as bot from './pages/bot.js';
import * as bankroll from './pages/bankroll.js';
import * as db from './pages/db.js';
import * as standings from './pages/standings.js';
import * as leaders from './pages/leaders.js';
import * as results from './pages/results.js';
import * as calendar from './pages/calendar.js';
import * as team from './pages/team.js';
import * as player from './pages/player.js';
import * as about from './pages/about.js';

const ROUTES = {
  '': bot, bankroll, base: db, classement: standings, leaders, resultats: results, calendrier: calendar,
  equipe: team, joueur: player, 'a-propos': about,
};
const NAV = [
  ['Bot', [['', '🏒', 'Performances & picks'], ['bankroll', '💰', 'Bankroll'], ['base', '🗄️', 'Base de données']]],
  ['NHL', [['classement', '🏆', 'Classement'], ['leaders', '⭐', 'Meilleurs joueurs'], ['resultats', '📅', 'Résultats par soirée'],
    ['calendrier', '🗓️', 'Calendrier'], ['equipe', '👥', 'Équipes'], ['joueur', '🧑', 'Joueurs']]],
  ['Infos', [['a-propos', 'ℹ️', 'À propos']]],
];

const app = document.getElementById('app');
const sidebar = document.getElementById('sidebar');
const backdrop = document.getElementById('backdrop');

document.getElementById('nav').innerHTML = NAV.map(([group, items]) => `
  <div><div class="px-3 mb-2 text-[11px] uppercase tracking-wider text-slate-500 font-semibold">${group}</div>
  ${items.map(([path, icon, label]) => `<a href="#/${path}" data-route="${path}" class="nav-link flex items-center gap-3 px-3 py-2 rounded-lg text-slate-300 hover:bg-white/5 hover:text-white transition">
    <span class="w-5 text-center">${icon}</span><span class="flex-1">${label}</span><span class="dot w-1.5 h-1.5 rounded-full"></span></a>`).join('')}</div>`).join('');

function setMenu(open) {
  sidebar.classList.toggle('-translate-x-full', !open);
  backdrop.classList.toggle('hidden', !open);
}
document.getElementById('menu-btn').addEventListener('click', () => setMenu(sidebar.classList.contains('-translate-x-full')));
backdrop.addEventListener('click', () => setMenu(false));

// Lignes de tableau cliquables (data-href) et cartes cliquables
document.addEventListener('click', (e) => {
  const row = e.target.closest('[data-href]');
  if (row && !e.target.closest('a')) location.hash = row.dataset.href;
});

let seq = 0;
async function route() {
  const [page = '', ...params] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const mod = ROUTES[page] || bot;
  document.querySelectorAll('.nav-link').forEach((a) => a.classList.toggle('active', a.dataset.route === (ROUTES[page] ? page : '')));
  setMenu(false);
  destroyCharts();
  const my = ++seq;
  app.innerHTML = '';
  window.scrollTo(0, 0);
  try {
    await mod.render(app, params, () => my === seq);
  } catch (e) {
    console.error(e);
    if (my === seq) app.innerHTML = errorBox(e.message || String(e));
  }
}

window.addEventListener('hashchange', route);
route();

botFile('bot.json').then((b) => {
  document.getElementById('updated').textContent =
    `Données du bot : ${new Date(b.last_updated).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })}`;
}).catch(() => { /* affiché par la page Performances */ });
