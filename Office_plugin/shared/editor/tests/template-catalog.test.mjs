import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CATALOG, CATEGORIES, COMMANDS, findEntries, entryTemplate, templateParts} from '../../EditorAssets/template-catalog.mjs';
import {GROUPS} from '../../EditorAssets/symbol-library.mjs';

test('every category searches the same unique catalog in either language and by command', () => {
  assert.equal(new Set(CATALOG.map(entry => entry.template)).size, CATALOG.length);
  for (const category of CATEGORIES.filter(category => category.id !== 'common')) assert.ok(findEntries(category.id).length, category.id);
  assert.equal(findEntries('common').length, 0);
  assert.deepEqual(CATEGORIES.map(category => category.id).slice(7, 14),
    ['arrows', 'sets', 'analysis', 'algebra', 'geometry', 'topology', 'numberTheory']);
  const fraction = findEntries('greek', 'Fraction').find(entry => entry.en === 'Fraction');
  assert.ok(fraction);
  assert.ok(findEntries('physics', '分数').includes(fraction));
  assert.ok(findEntries('chemistry', '\\frac').includes(fraction));
  assert.equal(COMMANDS.find(command => command.label === '\\frac').entry, fraction);
  assert.equal(findEntries('common', 'no-such-formula-123').length, 0);
  assert.ok(findEntries('structures', '阿尔法').some(entry => entry.template === '\\alpha'));
});

test('each category keeps its own order for shared symbols and promotes its common formulas', () => {
  assert.deepEqual(findEntries('operators').slice(0, 4).map(entry => entry.template), ['+', '-', '\\times', '\\div']);
  const union = findEntries('operators').find(entry => entry.template === '\\cup');
  assert.ok(union);
  assert.ok(findEntries('sets').includes(union));
  for (const {id, priority} of GROUPS) {
    if (priority) assert.deepEqual(findEntries(id).slice(0, priority.length).map(entry => entry.en), priority, id);
  }
});

test('library tiles contain mathematical templates rather than standalone labels', () => {
  const labelOnly = /^(?:[a-z]+(?: +[a-z]+)*|\\text\{[^}]*\})$/i;
  assert.deepEqual(CATALOG.filter(entry => labelOnly.test(entry.template.trim())), []);
});

test('selection fills an explicit hole, otherwise the first hole; remaining holes stay independent', () => {
  assert.deepEqual(templateParts('\\frac{#0}{#?}', 'x+1'), [
    {text: '\\frac{'}, {text: 'x+1'}, {text: '}{'}, {hole: true}, {text: '}'}]);
  assert.deepEqual(templateParts('\\overset{#?}{#@}', 'x')[1], {hole: true});
  assert.deepEqual(templateParts('\\overset{#?}{#@}', 'x')[3], {text: 'x'});
  assert.deepEqual(templateParts('#?+#?', '${literal}#?')[1], {text: '${literal}#?'});
  assert.equal(templateParts('#?+#?').filter(part => part.hole).length, 2);
});

test('letters inserted into a template slot remain separate from the preceding control word', () => {
  const template = '\\left\\{#0\\in#?\\mid#?\\right\\}';
  const fill = parts => parts.map(part => part.hole ? 'x' : part.text).join('');
  assert.equal(fill(templateParts(template)), '\\left\\{x\\in x\\mid x\\right\\}');
  assert.equal(fill(templateParts('\\lvert#0\\rvert', 'x')), '\\lvert x\\rvert');
});

test('matrix templates retain dimensions and specialized environments', () => {
  const bracketed = CATALOG.find(entry => entry.matrix === 'bmatrix');
  const template = entryTemplate(bracketed, 3, 4);
  assert.equal(templateParts(template).filter(part => part.hole).length, 12);
  assert.ok(template.startsWith('\\begin{bmatrix}'));
  assert.equal(templateParts(entryTemplate(CATALOG.find(entry => entry.matrix === 'cases'), 3, 7)).filter(part => part.hole).length, 6);
  assert.equal((entryTemplate(CATALOG.find(entry => entry.matrix === 'identity'), 3, 7).match(/1/g) || []).length, 3);
  assert.match(entryTemplate(CATALOG.find(entry => entry.matrix === 'augmented'), 2, 3), /\{ccc\|c\}/);
});
