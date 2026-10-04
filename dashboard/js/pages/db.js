// Base de données complète du bot (db.json exporté chaque soir, lecture seule).
import { botFile } from '../api.js';
import { esc, header, section, segmented, onSegment, table } from '../ui.js';

const PAGE = 300;

export async function render(el) {
  const data = await botFile('db.json');
  const bases = Object.keys(data);
  let base = bases[0];
  let tname = Object.keys(data[base])[0];
  let shown = PAGE;

  el.innerHTML = header('Base de données', 'Toutes les tables du bot, exportées chaque soir (lecture seule). Les colonnes JSON techniques sont masquées.')
    + section('Explorer', `<div class="flex flex-wrap gap-3 items-center mb-4"><div id="seg-wrap"></div>
      <select id="db-table" class="bg-white/5 border border-line rounded-lg px-3 py-2 text-sm"></select>
      <input id="db-q" placeholder="Filtrer (n'importe quelle colonne)…" class="flex-1 min-w-[200px] bg-white/5 border border-line rounded-lg px-3 py-2 text-sm">
      <button id="db-csv" class="px-3 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-blue-500">⬇ CSV</button></div>
      <p id="db-info" class="text-xs text-slate-400 mb-3"></p><div id="db-tbl"></div>
      <div class="mt-3 text-center"><button id="db-more" class="hidden px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-sm">Afficher plus</button></div>`);

  const sel = el.querySelector('#db-table');
  const q = el.querySelector('#db-q');

  const filtered = () => {
    const t = data[base][tname];
    const s = q.value.toLowerCase();
    return s ? t.rows.filter((r) => r.some((v) => String(v ?? '').toLowerCase().includes(s))) : t.rows;
  };

  const draw = () => {
    const t = data[base][tname];
    const rows = filtered();
    const objs = rows.slice(0, shown).map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])));
    const cols = t.columns.map((c) => ({ key: c, label: esc(c), align: 'left' }));
    el.querySelector('#db-info').textContent = `${rows.length} ligne(s) affichable(s) sur ${t.total} en base`
      + `${t.total > t.rows.length ? ` (export limité aux ${t.rows.length} plus récentes)` : ''} · ${t.columns.length} colonnes`;
    const box = el.querySelector('#db-tbl'); box.innerHTML = '';
    box.append(table(cols, objs, { maxH: 'max-h-[620px]' }));
    el.querySelector('#db-more').classList.toggle('hidden', rows.length <= shown);
  };

  const fillTables = () => {
    sel.innerHTML = Object.entries(data[base]).map(([n, t]) => `<option value="${esc(n)}">${esc(n)} (${t.total} lignes)</option>`).join('');
    tname = Object.keys(data[base])[0];
    sel.value = tname;
  };

  const drawSeg = () => {
    el.querySelector('#seg-wrap').innerHTML = segmented('db', bases.map((b) => ({ value: b, label: b })), base);
    onSegment(el, 'db', (v) => { base = v; shown = PAGE; fillTables(); drawSeg(); draw(); });
  };

  sel.addEventListener('change', () => { tname = sel.value; shown = PAGE; draw(); });
  q.addEventListener('input', () => { shown = PAGE; draw(); });
  el.querySelector('#db-more').addEventListener('click', () => { shown += PAGE; draw(); });
  el.querySelector('#db-csv').addEventListener('click', () => {
    const t = data[base][tname];
    const cell = (v) => { const s = String(v ?? ''); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [t.columns.map(cell).join(','), ...filtered().map((r) => r.map(cell).join(','))].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `${tname}.csv`; a.click(); URL.revokeObjectURL(a.href);
  });

  drawSeg(); fillTables(); draw();
}
