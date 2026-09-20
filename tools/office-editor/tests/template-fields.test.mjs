import {test} from 'node:test';
import assert from 'node:assert/strict';
import {EditorState} from '@codemirror/state';
import {keymap} from '@codemirror/view';
import {templateFields, templateTransaction} from '../template-fields.js';
import {templateParts} from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/template-catalog.mjs';

test('source templates preserve literal TeX, multiline selections and snippet-like user text', () => {
  const selected = '\\{x\\}\n\\text{${literal} #?}';
  let state = EditorState.create({doc: selected, extensions: templateFields});
  state = state.update(templateTransaction(templateParts('\\frac{#0}{#?}', selected), 0, selected.length)).state;
  assert.equal(state.doc.toString(), `\\frac{${selected}}{}`);
  assert.equal(state.selection.main.from, state.doc.length - 1);
  state = state.update(state.replaceSelection('denominator')).state;
  assert.equal(state.doc.toString(), `\\frac{${selected}}{denominator}`);
});

test('a symbol inserted before a variable keeps its command boundary', () => {
  let state = EditorState.create({doc: 'x', extensions: templateFields});
  state = state.update(templateTransaction(templateParts('\\alpha'), 0, 0, 'x')).state;
  assert.equal(state.doc.toString(), '\\alpha x');
  assert.equal(state.selection.main.from, '\\alpha '.length);
});

test('Tab and Shift-Tab track filled source fields and leave at the template end', () => {
  let state = EditorState.create({extensions: templateFields});
  const view = {get state() { return state; }, composing: false, dispatch(spec) { state = state.update(spec).state; }};
  view.dispatch(templateTransaction(templateParts('\\frac{#0}{#?}'), 0, 0));
  const tab = state.facet(keymap).flat().find(binding => binding.key === 'Tab');
  view.dispatch(state.replaceSelection('x+1'));
  assert.equal(tab.run(view), true);
  view.dispatch(state.replaceSelection('y'));
  assert.equal(tab.shift(view), true);
  assert.equal(state.sliceDoc(state.selection.main.from, state.selection.main.to), 'x+1');
  assert.equal(tab.run(view), true);
  assert.equal(state.sliceDoc(state.selection.main.from, state.selection.main.to), 'y');
  assert.equal(tab.run(view), true);
  assert.equal(state.selection.main.from, state.doc.length);
  assert.equal(tab.run(view), false);
});
