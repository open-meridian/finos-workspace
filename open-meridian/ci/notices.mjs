// The notices of every package the front end's build ships (frontend/package-lock.json's
// entries that are not dev-only), with Workspace's own LICENSE and NOTICE first; and the
// licence scan: a package under the AGPL, the GPL or the SSPL fails it, since this fork is
// Apache-2.0 and its image is built from it. Usage: node notices.mjs FRONTEND_DIR OUT
import fs from 'node:fs';
import path from 'node:path';

const [frontend, out] = process.argv.slice(2);
const root = path.dirname(path.resolve(frontend));
const lock = JSON.parse(fs.readFileSync(path.join(frontend, 'package-lock.json'), 'utf8'));
const REFUSED = /(^|[^L])(A?GPL|SSPL)/i;
const parts = [
  'Notices of what this image ships of FINOS Workspace\'s front end',
  '',
  '== FINOS Workspace: LICENSE ==',
  fs.readFileSync(path.join(root, 'LICENSE'), 'utf8'),
  '== FINOS Workspace: NOTICE ==',
  fs.readFileSync(path.join(root, 'NOTICE'), 'utf8'),
];
const refused = [];
let count = 0;
for (const [where, entry] of Object.entries(lock.packages ?? {})) {
  if (!where || entry.dev || entry.devOptional || entry.link) continue;
  const dir = path.join(frontend, where);
  if (!fs.existsSync(dir)) continue;
  const name = where.replace(/^.*node_modules\//, '');
  const licence = String(entry.license ?? JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8')).license ?? 'UNKNOWN');
  // An SPDX choice (A OR B) is taken under an alternative that is not refused.
  const choices = licence.replace(/[()]/g, '').split(/\s+OR\s+/i);
  if (choices.every((each) => REFUSED.test(each))) refused.push(`${name}@${entry.version}: ${licence}`);
  const texts = fs.readdirSync(dir).filter((f) => /^(licen[cs]e|copying|notice)/i.test(f));
  parts.push(`== ${name}@${entry.version} (${licence}) ==`);
  for (const file of texts) parts.push(fs.readFileSync(path.join(dir, file), 'utf8'));
  count += 1;
}
if (refused.length) {
  console.error(`notices: a package the build ships is under a licence this fork cannot ship:\n${refused.join('\n')}`);
  process.exit(1);
}
fs.writeFileSync(out, parts.join('\n'));
console.log(`notices: ${count} packages, none under the AGPL, the GPL or the SSPL`);
