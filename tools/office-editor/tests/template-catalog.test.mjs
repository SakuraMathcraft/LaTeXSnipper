import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CATALOG, CATEGORIES, COMMANDS, findEntries, entryTemplate, templateParts} from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/template-catalog.mjs';

test('every category searches the same unique catalog in either language and by command', () => {
  assert.equal(new Set(CATALOG.map(entry => entry.template)).size, CATALOG.length);
  for (const category of CATEGORIES) assert.ok(findEntries(category.id).length, category.id);
  const fraction = findEntries('greek', 'Fraction').find(entry => entry.en === 'Fraction');
  assert.ok(fraction);
  assert.ok(findEntries('physics', '分数').includes(fraction));
  assert.ok(findEntries('chemistry', '\\frac').includes(fraction));
  assert.equal(COMMANDS.find(command => command.label === '\\frac').entry, fraction);
  assert.equal(findEntries('common', 'no-such-formula-123').length, 0);
  assert.ok(findEntries('structures', '阿尔法').some(entry => entry.template === '\\alpha'));
});

test('selection fills an explicit hole, otherwise the first hole; remaining holes stay independent', () => {
  assert.deepEqual(templateParts('\\frac{#0}{#?}', 'x+1'), [
    {text: '\\frac{'}, {text: 'x+1'}, {text: '}{'}, {hole: true}, {text: '}'}]);
  assert.deepEqual(templateParts('\\overset{#?}{#@}', 'x')[1], {hole: true});
  assert.deepEqual(templateParts('\\overset{#?}{#@}', 'x')[3], {text: 'x'});
  assert.deepEqual(templateParts('#?+#?', '${literal}#?')[1], {text: '${literal}#?'});
  assert.equal(templateParts('#?+#?').filter(part => part.hole).length, 2);
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
