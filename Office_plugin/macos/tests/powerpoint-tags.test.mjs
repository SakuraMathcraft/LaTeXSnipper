import assert from 'node:assert/strict';
import test from 'node:test';
import {MetadataError} from '../web/app/metadata.mjs';
import {createFormula, formulaFromTags, formulaTags, isFormulaTagSet, isOleFormulaTagSet, TAG} from '../web/app/powerpoint/tags.mjs';

const typography = {typographyVersion: 1, symbolFontId: 'mathjax-tex', numberFontFamily: '', cjkFontFamily: 'PingFang SC',
  defaultMathStyle: 'Automatic', fontSizePoints: 12, color: '#000000'};
const formula = (latex = '\\frac{a}{b}', format = 'Png') => createFormula({documentId: 'doc', equationId: 'eq', latex,
  typography, format, naturalWidthPoints: 20.5, naturalHeightPoints: 30});

test('tags follow PowerPointFormulaMetadataStore: order, upper-case hex and 200-character chunks', () => {
  const latex = 'x'.repeat(150) + '中';
  const tags = formulaTags(formula(latex));
  assert.deepEqual(tags.slice(0, 4), [[TAG.documentId, 'doc'], [TAG.equationId, 'eq'], [TAG.schemaVersion, '3'],
    [TAG.renderEngine, 'Image']]);
  const map = new Map(tags);
  const bytes = new TextEncoder().encode(latex);
  const hex = [...bytes].map(b => b.toString(16).toUpperCase().padStart(2, '0')).join('');
  assert.equal(map.get('LaTeXSnipperLatexBytes'), String(bytes.length));
  assert.equal(map.get('LaTeXSnipperLatexChunks'), '2');
  assert.equal(map.get('LaTeXSnipperLatex0000'), hex.slice(0, 200));
  assert.equal(map.get('LaTeXSnipperLatex0001'), hex.slice(200));
  assert.equal(map.get(TAG.displayMode), 'Display');
  const typographyHex = [...map].filter(([key]) => /^LaTeXSnipperTypography\d{4}$/.test(key)).map(([, value]) => value).join('');
  assert.deepEqual(JSON.parse(Buffer.from(typographyHex, 'hex').toString('utf8')), typography);
  assert.equal(map.get(TAG.naturalWidth), '20.5');
  assert.equal(map.has('LaTeXSnipperImagePath'), false);
});

test('round trips through PowerPoint, which upper-cases tag names; SVG is a Mac-only extra tag', () => {
  for (const format of ['Png', 'Svg']) {
    const upper = formulaTags(formula('a', format)).map(([key, value]) => [key.toUpperCase(), value]);
    assert.deepEqual(formulaFromTags(upper), formula('a', format));
  }
  const windows = formulaTags(formula()).filter(([key]) => key !== TAG.imageFormat);
  assert.equal(formulaFromTags(windows).format, 'Png');
});

test('an empty formula source is stored as the Windows "0" payload', () => {
  const map = new Map(formulaTags(formula('')));
  assert.deepEqual([map.get('LaTeXSnipperLatexBytes'), map.get('LaTeXSnipperLatexChunks'), map.get('LaTeXSnipperLatex0000')], ['0', '1', '0']);
  assert.equal(formulaFromTags([...map]).latex, '');
});

test('damaged, OLE or foreign metadata is rejected', () => {
  const good = formulaTags(formula());
  const without = name => good.filter(([key]) => key !== name);
  const replaced = (name, value) => good.map(([key, old]) => [key, key === name ? value : old]);
  for (const broken of [without(TAG.equationId), without('LaTeXSnipperLatex0000'), replaced('LaTeXSnipperLatexBytes', '99'),
    replaced(TAG.schemaVersion, '2'), replaced(TAG.renderEngine, 'MathJaxSvg'), replaced(TAG.naturalWidth, '0'),
    replaced('LaTeXSnipperLatex0000', 'ZZ')])
    assert.throws(() => formulaFromTags(broken), MetadataError);
  assert.equal(isFormulaTagSet(good), true);
  assert.equal(isFormulaTagSet([['LATEXSNIPPEREQUATIONID', '  ']]), false);
  assert.equal(isOleFormulaTagSet(replaced(TAG.renderEngine, 'MathJaxSvg')), true);
  assert.equal(isOleFormulaTagSet(good), false);
});
