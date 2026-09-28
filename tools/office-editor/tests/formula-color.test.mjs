import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {formulaColor, hasFormulaContent, inheritFormulaColor, initialFormulaColor, withFormulaColor}
  from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/formula-color.mjs';

test('global color remains in source through visual recoloring and toolbar changes', () => {
  const blue = '#363bd3';
  const visual = '\\textcolor{#363bd3}{\\textcolor{#363bd3}{\\lim_{n\\to\\infty}a_n=}\\textcolor{red}{L}}';
  const canonical = inheritFormulaColor(visual, blue);
  assert.equal(canonical, '\\textcolor{#363bd3}{\\lim_{n\\to\\infty}a_n=\\textcolor{red}{L}}');
  assert.equal(withFormulaColor(canonical, '#123456'),
    '\\textcolor{#123456}{\\lim_{n\\to\\infty}a_n=\\textcolor{red}{L}}');
  assert.equal(formulaColor(canonical), blue);
});

test('empty colored draft keeps its configured global color without becoming a formula', () => {
  const latex = initialFormulaColor('', '#363bd3');
  assert.equal(latex, '\\textcolor{#363bd3}{}');
  assert.equal(formulaColor(latex), '#363bd3');
  assert.equal(hasFormulaContent(latex), false);
});
