// À propos : sources des données et fonctionnement du dashboard.
import { botFile } from '../api.js';
import { header, section } from '../ui.js';

export async function render(el) {
  const b = await botFile('bot.json').catch(() => null);
  const upd = b ? new Date(b.last_updated).toLocaleString('fr-FR') : 'indisponible';
  el.innerHTML = header('À propos') + section('Sources', `<ul class="space-y-2 text-sm text-slate-300 list-disc pl-5">
    <li><b>Données NHL</b> (classement, résultats, calendrier, effectifs, joueurs) : API publique <code>api-web.nhle.com</code>, en direct, relayée par Vercel (<code>/nhl/…</code>).</li>
    <li><b>Données du bot</b> (picks, base de données) : <code>bot.json</code> et <code>db.json</code>, exportés par le bot chaque soir sur la branche <code>dashboard-data</code>. Dernière mise à jour : ${upd}.</li>
    <li><b>Simulateur de bankroll</b> : <code>simulateur.html</code> à la racine du dépôt.</li>
    <li><b>Mode découverte 🧪</b> : picks sur des joueurs à moins de 10 matchs cette saison, estimés aussi avec la saison passée, mise réduite de moitié.</li></ul>`)
    + section('Lancer en local', `<pre class="text-xs bg-black/30 rounded-lg p-3 overflow-auto">python dashboard/exporter.py      # régénère bot.json et db.json
python dashboard/dev_server.py    # http://localhost:8000</pre>`);
}
