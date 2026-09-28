// Inventaire des chaînes de texte affichées par les plaques, pour les traduire sans casser
// les mises en page. Sortie : par fichier, les littéraux candidats avec leur nombre d'occurrences.
//   bun scan-ui-strings.mjs
import { readdirSync, readFileSync } from 'node:fs';

const dir = 'src/scenes';
// valeurs de code à ne pas traduire (palette, unités, identifiants de police, sélecteurs)
const SKIP = /^(?:#[0-9a-f]{3,8}|\.{0,2}\/|\w+\.(ts|js|png|wav|json)|px|em|pt|%|ink|bone|signal|paper|rust|acid|lime|cyan|rose|slate|amber|hot|cold|TRUE|FALSE|null|none|left|right|center|start|end|top|bottom|middle|alphabetic|butt|round|square|bevel|miter|repeat|no-repeat|mono|serif|sans|archivo|plex|cormorant|hershey|ems|w\d{3}|[A-Z]$)$/i;

const rows = [];
for (const f of readdirSync(dir).filter((f) => f.endsWith('.ts'))) {
  const src = readFileSync(`${dir}/${f}`, 'utf8');
  const hits = new Map();
  // les commentaires contiennent aussi des guillemets : on les retire pour ne garder que le code
  const code = src.split('\n')
    .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .map((l) => l.replace(/\/\/.*$/, ''))
    .join('\n');
  for (const m of code.matchAll(/(['"`])((?:(?!\1)[^\\\n]|\\.)*)\1/g)) {
    const s = m[2];
    // texte affiché : au moins une lettre, pas un chemin/identifiant, pas du code
    if (!/[A-Za-zÀ-ÿ]/.test(s)) continue;
    if (s.length < 2 || s.length > 90) continue;
    if (SKIP.test(s)) continue;
    if (/^[\w.-]+$/.test(s) && !/[A-Z]{2,}/.test(s)) continue;  // identifiant ou valeur simple
    if (/^[a-z][a-zA-Z0-9]*$/.test(s)) continue;                 // camelCase / mot-clé
    if (/(^|\s)(import|from|const|function|return|new |this\.)/.test(s)) continue;
    hits.set(s, (hits.get(s) ?? 0) + 1);
  }
  if (hits.size) rows.push([f, [...hits.entries()].sort()]);
}

let total = 0;
for (const [f, hits] of rows.sort((a, b) => b[1].length - a[1].length)) {
  total += hits.length;
  console.log(`\n=== ${f}  (${hits.length}) ===`);
  for (const [s, n] of hits) console.log(`  ${n}×  ${JSON.stringify(s)}`);
}
console.log(`\ntotal ${total} chaînes distinctes`);
