import {build} from 'esbuild';
import {readFile, writeFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const assets = resolve(root, '../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets');
const result = await build({entryPoints: [resolve(root, 'source-editor.js')], outfile: resolve(assets, 'source-editor.bundle.js'),
  absWorkingDir: root, bundle: true, minify: true, format: 'esm', target: 'es2022', legalComments: 'inline', metafile: true});
const licenses = [];
const packages = new Set();
for (const input of Object.keys(result.metafile.inputs).filter(path => path.startsWith('node_modules/'))) {
  let directory = dirname(resolve(root, input));
  while (!existsSync(resolve(directory, 'package.json'))) directory = dirname(directory);
  packages.add(directory);
}
for (const directory of [...packages].sort()) {
  const pkg = JSON.parse(await readFile(resolve(directory, 'package.json'), 'utf8'));
  licenses.push(`${pkg.name} ${pkg.version}\n${await readFile(resolve(directory, 'LICENSE'), 'utf8')}`);
}
await writeFile(resolve(assets, 'source-editor.LICENSE.txt'), licenses.join('\n\n'));
