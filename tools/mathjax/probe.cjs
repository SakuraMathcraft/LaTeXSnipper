// Exercise the actual browser runtime with an offline Node DOM adaptor.
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '../../src/assets/MathJax').replaceAll('\\', '/');
require(root + '/config.js');
require(root + '/runtime.js');
require(root + '/office.js');
const api = globalThis.LaTeXSnipperMathJax;
const settings = JSON.parse(process.argv[2] || '{}');
api.configure({root, output: 'svg', typeset: false, font: settings.font});
MathJax.loader.load.push('adaptors/liteDOM');
MathJax.loader.source = {'adaptors/liteDOM': path.join(__dirname, 'liteDOM.js').replaceAll('\\', '/')};
const loaded = [];
MathJax.loader.require = file => {
  if (/^https?:/.test(file)) throw new Error('Unexpected network request: ' + file);
  loaded.push(file);
  return require(file);
};
MathJax.loader.failed = error => { console.error(error.message); process.exit(1); };
require(root + '/startup.js');
(async () => {
  await MathJax.startup.promise;
  const inputs = JSON.parse(fs.readFileSync(0, 'utf8'));
  const results = await Promise.all(inputs.map(input =>
    (input.officeInput ? LaTeXSnipperOfficeMath : api).convert(input)));
  if (api.error) throw new Error(api.error);
  process.stdout.write(JSON.stringify({results, loaded}));
})().catch(error => { console.error(error); process.exit(1); });
