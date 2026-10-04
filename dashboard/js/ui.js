// Composants visuels communs : cartes KPI, tableaux triables et cliquables, graphiques Chart.js.

export const COLORS = { accent: '#3b82f6', violet: '#a855f7', green: '#22c55e', red: '#f43f5e', amber: '#f59e0b',
  cyan: '#06b6d4', slate: '#94a3b8' };
const charts = [];

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const bad = (x) => x == null || Number.isNaN(x);
export const fmtU = (x) => (bad(x) ? '–' : `${x > 0 ? '+' : ''}${x.toFixed(1)} U`);
export const fmtPct = (x, d = 1) => (bad(x) ? '–' : `${x > 0 ? '+' : ''}${(x * 100).toFixed(d)} %`);
export const ord = (n) => `${n}${n === 1 ? 'er' : 'ᵉ'}`;
export const fmtNum = (x, d = 2) => (bad(x) ? '–' : Number(x).toFixed(d));
export const tone = (x) => (bad(x) || x === 0 ? '' : x > 0 ? 'text-emerald-400' : 'text-rose-400');
export const frDate = (s, opts = { weekday: 'long', day: 'numeric', month: 'long' }) =>
  (s ? new Date(`${s.slice(0, 10)}T12:00:00`).toLocaleDateString('fr-FR', opts) : '');
export const frTime = (utc) => (utc ? new Date(utc).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '');

export function header(title, sub = '') {
  return `<div class="mb-6 fade-in"><h1 class="text-2xl sm:text-3xl font-extrabold tracking-tight">${title}</h1>
    ${sub ? `<p class="mt-1 text-slate-400 text-sm">${sub}</p>` : ''}</div>`;
}

export function kpi(label, value, sub = '', cls = '') {
  return `<div class="card p-4 sm:p-5 fade-in"><div class="text-[11px] uppercase tracking-wider text-slate-400">${label}</div>
    <div class="mt-1 text-2xl sm:text-3xl font-extrabold ${cls}">${value}</div>
    ${sub ? `<div class="mt-1 text-xs text-slate-400">${sub}</div>` : ''}</div>`;
}

export const section = (title, inner, right = '') => `<section class="card p-4 sm:p-5 mb-6 fade-in">
  <div class="flex flex-wrap items-center justify-between gap-3 mb-4"><h2 class="font-bold text-lg">${title}</h2>${right}</div>${inner}</section>`;

export const chip = (txt, cls = 'bg-accent/15 text-blue-300') => `<span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}">${txt}</span>`;
export const img = (src, cls = 'w-8 h-8', alt = '') => (src ? `<img src="${esc(src)}" alt="${esc(alt)}" loading="lazy" class="${cls} object-contain">` : '');
export const loading = (h = 'h-40') => `<div class="skeleton ${h} w-full"></div>`;
export const empty = (msg) => `<div class="text-center text-slate-400 py-10">${msg}</div>`;
export const errorBox = (msg) => `<div class="card p-4 border-rose-500/40 text-rose-300">⚠️ ${esc(msg)}</div>`;

/** Contrôle segmenté : options [{value,label}] ; renvoie le HTML, le clic appelle onChange via data-seg. */
export function segmented(id, options, current) {
  return `<div class="inline-flex flex-wrap gap-0.5 rounded-xl bg-white/5 p-1 text-sm" data-seg="${id}">${options.map((o) =>
    `<button data-value="${esc(o.value)}" class="px-3 py-1.5 rounded-lg transition ${o.value === current ? 'bg-accent text-white shadow' : 'text-slate-300 hover:text-white'}">${o.label}</button>`).join('')}</div>`;
}
export function onSegment(root, id, cb) {
  root.querySelector(`[data-seg="${id}"]`)?.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (b) cb(b.dataset.value);
  });
}

/**
 * Tableau triable.
 * @param {Array<{key,label,fmt?,html?,align?,sort?}>} cols  html(row) pour un rendu riche
 * @param {Array<object>} rows
 * @param {{href?:(row)=>string, maxH?:string, sortKey?:string, desc?:boolean, rank?:boolean}} opts
 */
export function table(cols, rows, opts = {}) {
  const wrap = document.createElement('div');
  wrap.className = `overflow-auto scroll-thin rounded-xl border border-line ${opts.maxH || ''}`;
  let key = opts.sortKey || null;
  let desc = opts.desc ?? true;
  const render = () => {
    const data = [...rows];
    if (key) {
      const c = cols.find((x) => x.key === key);
      const val = c?.sort || ((r) => r[key]);
      data.sort((a, b) => {
        const x = val(a); const y = val(b);
        if (x == null) return 1; if (y == null) return -1;
        return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'fr')) * (desc ? -1 : 1);
      });
    }
    const th = cols.map((c) => `<th data-k="${c.key}" class="px-3 py-2.5 font-semibold text-slate-400 whitespace-nowrap cursor-pointer select-none ${c.align === 'left' ? 'text-left' : 'text-right'} first:text-left">${c.label}${key === c.key ? (desc ? ' ↓' : ' ↑') : ''}</th>`).join('');
    const tr = data.map((r, i) => {
      const href = opts.href ? opts.href(r) : null;
      const tds = cols.map((c) => {
        const v = c.html ? c.html(r, i) : c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key] ?? '');
        return `<td class="px-3 py-2 whitespace-nowrap ${c.align === 'left' ? 'text-left' : 'text-right'} first:text-left">${v}</td>`;
      }).join('');
      return `<tr class="border-t border-line" ${href ? `data-href="${esc(href)}"` : ''}>${tds}</tr>`;
    }).join('');
    wrap.innerHTML = `<table class="tbl w-full text-sm tabular-nums"><thead><tr>${th}</tr></thead><tbody>${tr || `<tr><td colspan="${cols.length}" class="py-8 text-center text-slate-400">Aucune donnée</td></tr>`}</tbody></table>`;
  };
  wrap.addEventListener('click', (e) => {
    const h = e.target.closest('th[data-k]');
    if (h) { if (key === h.dataset.k) desc = !desc; else { key = h.dataset.k; desc = true; } render(); }
  });
  render();
  return wrap;
}

export function mount(el, html) {
  if (typeof html === 'string') el.innerHTML = html; else { el.innerHTML = ''; el.append(html); }
}

// ── Graphiques ──────────────────────────────────────────────────────────────
export function destroyCharts() { while (charts.length) charts.pop().destroy(); }

export function chart(canvasOrId, config) {
  const cv = typeof canvasOrId === 'string' ? document.getElementById(canvasOrId) : canvasOrId;
  if (!cv || !window.Chart) return null;
  const Chart = window.Chart;
  Chart.defaults.color = '#94a3b8';
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  Chart.defaults.borderColor = 'rgba(148,163,184,.12)';
  const opts = config.options || {};
  const c = new Chart(cv, {
    ...config,
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 400 },
      interaction: { mode: 'index', intersect: false },
      ...opts,
      plugins: {
        legend: { position: 'top', align: 'end', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
        tooltip: { backgroundColor: '#0b1120', borderColor: 'rgba(148,163,184,.25)', borderWidth: 1, padding: 10 },
        ...(opts.plugins || {}),
      },
    },
  });
  charts.push(c);
  return c;
}

export const canvas = (id, h = 'h-72') => `<div class="relative ${h}"><canvas id="${id}"></canvas></div>`;
