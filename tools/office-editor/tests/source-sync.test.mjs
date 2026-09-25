import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SourceSync} from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/source-sync.mjs';
import {inspectLatex, comparableLatex} from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/latex-structure.mjs';

function setup() {
  let sync, preview = '', mode;
  const jobs = [];
  const source = {value: '', revision: 0, reset(value) { this.value = value; this.revision++; },
    replace(value, origin = 'source') { this.value = value; this.revision++; sync.sourceChanged({origin}); },
    setEnabled(value) { this.enabled = value; }};
  const mathfield = {setValue(value) { preview = value; }, errors: []};
  sync = new SourceSync({source, mathfield, readVisual: () => preview, onMode: value => { mode = value; },
    schedule: job => jobs.push(job), cancel() { /* Simulate a task already queued when cancelled. */ }});
  return {source, mathfield, sync, jobs, preview: value => { preview = value; }, mode: () => mode};
}
test('load and reference refresh preserve source bytes and create no edit', () => {
  const {sync, source} = setup();
  const latex = '  \\begin{align}x&=1\\\\y&=2\\end{align} % note\n';
  sync.load(latex); sync.refresh(); assert.equal(source.value, latex); assert.equal(source.revision, 1);
});
test('cancelled delayed preview cannot replace newer source or preview', () => {
  const {sync, source, mathfield, jobs} = setup();
  const previews = []; mathfield.setValue = value => previews.push(value);
  sync.load('x'); source.replace('x+1'); source.replace('x+2'); jobs[0](); jobs[1]();
  assert.deepEqual(previews, ['x', 'x+2']); assert.equal(source.value, 'x+2');
});
test('an input notification without a user-edit ticket cannot overwrite source', () => {
  const {sync, source, preview} = setup(); sync.load('x'); preview('normalized'); sync.visualInput();
  assert.equal(source.value, 'x');
});
test('explicit visual editing commits exactly once', () => {
  const {sync, source, preview} = setup(); sync.load('x'); sync.beforeVisualInput({}); preview('x+1');
  sync.visualInput(); sync.visualInput(); assert.equal(source.value, 'x+1'); assert.equal(source.revision, 2);
});
test('new source invalidates an old visual edit', () => {
  const {sync, source, preview} = setup(); sync.load('x'); sync.beforeVisualInput({});
  source.replace('new source'); preview('old visual'); sync.visualInput(); assert.equal(source.value, 'new source');
});

test('submission lock survives a queued refresh and blocks visual edits and history', () => {
  const {sync, source, mathfield, jobs} = setup();
  sync.load('x'); source.replace('x+1'); sync.setLocked(true); jobs.at(-1)();
  assert.equal(mathfield.readOnly, true); assert.equal(source.enabled, false);
  assert.equal(sync.performVisual(() => assert.fail('locked edit')), false);
  source.undo = () => assert.fail('locked undo'); sync.history(false);
  sync.setLocked(false); assert.equal(mathfield.readOnly, false); assert.equal(source.enabled, true);
});
test('composition delays preview until committed', () => {
  const {sync, source, mathfield, jobs} = setup(); const previews = [];
  mathfield.setValue = value => previews.push(value); sync.load('x'); sync.composition(true);
  source.replace('中'); source.replace('中文'); assert.deepEqual(previews, ['x']);
  sync.composition(false); jobs.at(-1)(); assert.deepEqual(previews, ['x', '中文']);
});
test('visual composition commits only the completed value', () => {
  const {sync, source, preview} = setup(); sync.load('x'); sync.visualComposition(true);
  sync.beforeVisualInput({}); preview('中'); sync.visualInput(); assert.equal(source.value, 'x');
  preview('中文'); sync.visualComposition(false); assert.equal(source.value, '中文');
});
test('lossy visual serialization and commented input become reference-only', () => {
  const {sync, source, mathfield} = setup(); mathfield.setValue = () => {};
  sync.load('x+1'); assert.equal(mathfield.readOnly, true); assert.equal(source.value, 'x+1');
  sync.load('x % comment'); assert.equal(mathfield.readOnly, true);
});
test('a new document invalidates delayed work from the previous session', () => {
  const {sync, source, jobs} = setup(); sync.load('x'); source.replace('x+1'); sync.load('new'); jobs[0]();
  assert.equal(source.value, 'new');
});
test('structural diagnostics respect comments and escaped delimiters', () => {
  assert.deepEqual(inspectLatex('\\begin{align}a&=\\{x\\} % }\\end{bad}\n\\end{align}'), []);
  assert.equal(inspectLatex('\\frac{a}{b').length, 1);
  assert.equal(inspectLatex('\\begin{align}x\\end{matrix}').length, 2);
  assert.deepEqual(inspectLatex('\\verb|{foo}|'), []);
});
test('roundtrip comparison preserves text spaces and ignores only layout spaces', () => {
  assert.equal(comparableLatex(' x + 1 '), comparableLatex('x+1'));
  assert.notEqual(comparableLatex('\\text{a b}'), comparableLatex('\\text{ab}'));
  assert.equal(comparableLatex('x % comment'), null);
  assert.notEqual(comparableLatex('\\alpha b'), comparableLatex('\\alphab'));
  assert.notEqual(comparableLatex('\\text{a \\textbf{b} c}'), comparableLatex('\\text{a \\textbf{b}c}'));
});
