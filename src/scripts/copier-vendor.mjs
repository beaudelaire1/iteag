/**
 * Copie les bibliothèques tierces depuis node_modules vers static/js/vendor/.
 *
 * Elles sont servies depuis notre origine, jamais depuis un CDN : la politique
 * de sécurité reste `script-src 'self'`, et une panne ou une compromission
 * chez un tiers ne peut pas atteindre les visiteurs (ADR-003, ADR-005).
 *
 * Le script échoue bruyamment si une source manque : une page servie sans son
 * lecteur vaut mieux découverte à la construction qu'en production.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const racine = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const FICHIERS = [
  ["node_modules/hls.js/dist/hls.light.min.js", "static/js/vendor/hls.min.js"],
];

mkdirSync(resolve(racine, "static/js/vendor"), { recursive: true });

let erreurs = 0;
for (const [source, cible] of FICHIERS) {
  const chemin = resolve(racine, source);
  if (!existsSync(chemin)) {
    console.error(`✗ source absente : ${source} — exécuter « npm install »`);
    erreurs += 1;
    continue;
  }
  // La référence à la source map est retirée. Elle pointe vers un fichier que
  // nous ne livrons pas — le manifeste de production refuse alors la collecte,
  // et l'image ne se construit plus. Livrer la map à la place exposerait le
  // source d'une dépendance sans rien apporter en production.
  const source_js = readFileSync(chemin, "utf8").replace(/\n?\/\/# sourceMappingURL=.*$/m, "\n");
  writeFileSync(resolve(racine, cible), source_js);
  console.log(`✓ ${cible}`);
}

if (erreurs > 0) process.exit(1);
