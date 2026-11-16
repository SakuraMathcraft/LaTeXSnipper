// Run from Office_plugin/macos: npm test
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  bookmarkName, buildTag, createFormula, equationIdFromTag, FormulaMetadataMissing, loadFormula, numberStateAfter,
  numberStates, referenceCode, revisionFromTag, sequenceCode, sequenceResult, serializeFormula, variableName,
} from '../web/app/word/contract.mjs';

const ID = '0123456789abcdef0123456789abcdef';
const DOC = 'fedcba9876543210fedcba9876543210';
const typography = {typographyVersion: 1, symbolFontId: 'mathjax-tex', numberFontFamily: '', cjkFontFamily: 'PingFang SC',
  defaultMathStyle: 'Automatic', fontSizePoints: 10.5, color: '#112233'};
const settings = {numberEnclosure: 'Parentheses', includeChapter: false, includeSection: false, numberSeparator: '-'};

test('tags follow WordFormulaMetadataStore: id before the first bar, revision after it', () => {
  const tag = buildTag(ID, 'abcdef0123');
  assert.equal(tag, `latexsnipper-eq-${ID}|abcdef0123`);
  assert.equal(tag.length, 59);
  assert.equal(equationIdFromTag(tag), ID);
  assert.equal(revisionFromTag(tag), 'abcdef0123');
  assert.equal(equationIdFromTag(`latexsnipper-eq-${ID}`), ID);
  assert.equal(revisionFromTag(`latexsnipper-eq-${ID}|`), '');
  assert.equal(equationIdFromTag('LaTeXSnipper-eq-x'), '');
  assert.throws(() => buildTag(ID + ID), /64/);
});

test('bookmarks keep the 40 characters Word stores, references keep the full name', () => {
  assert.equal(bookmarkName(ID), 'LaTeXSnipperEq_0123456789abcdef012345678');
  assert.equal(bookmarkName(ID).length, 40);
  assert.equal(referenceCode(ID), ` REF LaTeXSnipperEq_${ID} \\h `);
});

test('SEQ codes match WordEquationNumbering for every documented combination', () => {
  assert.equal(sequenceCode({reset: true, prefix: '', enclosure: 'Parentheses'}), ` SEQ LaTeXSnipperEquation \\r 1 \\# "'('0')'" `);
  assert.equal(sequenceCode({reset: false, prefix: '', enclosure: 'Parentheses'}), ` SEQ LaTeXSnipperEquation \\# "'('0')'" `);
  assert.equal(sequenceCode({reset: true, prefix: '2-', enclosure: 'Parentheses'}), ` SEQ LaTeXSnipperEquation \\r 1 \\# "'(2-'0')'" `);
  assert.equal(sequenceCode({reset: false, prefix: '3.1.', enclosure: 'SquareBrackets'}), ` SEQ LaTeXSnipperEquation \\# "'[3.1.'0']'" `);
  assert.equal(sequenceCode({reset: false, prefix: '', enclosure: 'None'}), ' SEQ LaTeXSnipperEquation ');
  assert.equal(sequenceCode({reset: false, prefix: '1·', enclosure: 'None'}), ` SEQ LaTeXSnipperEquation \\# "'1·'0" `);
  assert.equal(sequenceCode({reset: false, prefix: "it's-", enclosure: 'None'}), ` SEQ LaTeXSnipperEquation \\# "'it''s-'0" `);
  assert.equal(sequenceResult({prefix: '2-', enclosure: 'Braces'}, 3), '{2-3}');
});

test('boundaries restart numbering; a chapter boundary starts the next chapter', () => {
  const timeline = [{kind: 'formula'}, {kind: 'formula'}, {kind: 'chapter'}, {kind: 'formula'}, {kind: 'section'},
    {kind: 'formula'}, {kind: 'chapter'}, {kind: 'formula'}];
  const states = numberStates(timeline, {...settings, includeChapter: true, includeSection: true, numberSeparator: '.'});
  assert.deepEqual([...states.entries()].map(([index, state]) => [index, state.prefix, state.reset, state.value]), [
    [0, '1.1.', true, 1], [1, '1.1.', false, 2], [3, '2.1.', true, 1], [5, '2.2.', true, 1], [7, '3.1.', true, 1]]);
  // Boundaries reset the count even when the prefix leaves them out.
  assert.equal(numberStates([{kind: 'formula'}, {kind: 'section'}, {kind: 'formula'}], settings).get(2).reset, true);
  assert.deepEqual(numberStateAfter([], settings), {prefix: '', reset: true, enclosure: 'Parentheses', value: 1});
  assert.equal(numberStateAfter([{kind: 'formula'}], settings).reset, false);
});

test('metadata variables round trip with the Windows key order and are read back through the tag', () => {
  const formula = createFormula({documentId: DOC, equationId: ID, latex: '  \\bm{x}^2 ', display: false,
    numberingMode: 'Manual', numberText: ' 7 ', typography});
  assert.equal(formula.latex, '\\boldsymbol{x}^2');
  assert.equal(formula.displayMode, 'Display');
  assert.equal(formula.numberText, '7');
  const json = serializeFormula(formula);
  assert.deepEqual(Object.keys(JSON.parse(json)), ['schemaVersion', 'documentId', 'equationId', 'latex', 'displayMode',
    'numberingMode', 'numberText', 'renderEngine', 'typography']);
  assert.deepEqual(Object.keys(JSON.parse(json).typography), ['typographyVersion', 'symbolFontId', 'numberFontFamily',
    'cjkFontFamily', 'defaultMathStyle', 'fontSizePoints', 'color']);
  const variables = new Map([[variableName(ID, 'abcdef0123'), json]]);
  assert.deepEqual(loadFormula(buildTag(ID, 'abcdef0123'), variables), formula);
});

test('Windows JavaScriptSerializer payloads load, including string schema versions and escaped markup', () => {
  const windows = `{"schemaVersion":"3","documentId":"${DOC}","equationId":"${ID}","latex":"a\\u003cb","displayMode":"display",`
    + `"numberingMode":"automatic","numberText":"","renderEngine":"Omml","typography":{"typographyVersion":1,`
    + '"symbolFontId":"mathjax-stix2","numberFontFamily":"","cjkFontFamily":"Microsoft YaHei","defaultMathStyle":"Bold",'
    + '"fontSizePoints":12,"color":"#000000"}}';
  const formula = loadFormula(buildTag(ID, 'r1'), new Map([[variableName(ID, 'r1'), windows]]));
  assert.equal(formula.latex, 'a<b');
  assert.equal(formula.displayMode, 'Display');
  assert.equal(formula.numberingMode, 'Automatic');
});

test('missing, foreign or non-OMML metadata is reported as missing', () => {
  const good = serializeFormula(createFormula({documentId: DOC, equationId: ID, latex: 'x', display: false, typography}));
  const tag = buildTag(ID, 'r1');
  const load = value => () => loadFormula(tag, new Map([[variableName(ID, 'r1'), value]]));
  assert.throws(() => loadFormula(tag, new Map()), FormulaMetadataMissing);
  assert.throws(() => loadFormula(`latexsnipper-eq-${ID}`, new Map([[variableName(ID, ''), good]])), FormulaMetadataMissing);
  assert.throws(load('{'), FormulaMetadataMissing);
  assert.throws(load(good.replace(ID, DOC)), FormulaMetadataMissing);
  assert.throws(load(good.replace('"Omml"', '"MathJaxSvg"')), FormulaMetadataMissing);
  assert.throws(load(good.replace('"Automatic"', '"automatic"')), FormulaMetadataMissing);
  assert.throws(load(good.replace('"schemaVersion":3', '"schemaVersion":2')), FormulaMetadataMissing);
});
