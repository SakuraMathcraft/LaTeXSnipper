import assert from 'node:assert/strict';
import test from 'node:test';
import {paragraphs, wordPackage} from './dom.mjs';
import {buildTag, sequenceCode} from '../web/app/word/contract.mjs';
import {
  automaticNumberXml, deleteFormulaXml, equationControl, extractOMath, formulaParagraph, manualNumberXml,
  readVariables, replaceFormulaXml, sectionTextWidthPoints,
} from '../web/app/word/ooxml.mjs';

const ID = '0123456789abcdef0123456789abcdef';
const BOOKMARK = 'LaTeXSnipperEq_0123456789abcdef012345678';
const OMATH = '<m:oMath><m:r><m:t>x</m:t></m:r></m:oMath>';
const sdt = equationControl(OMATH, buildTag(ID, 'abcdef0123'));
const userBookmark = (id, name, text, superscript = false) => `<w:bookmarkStart w:id="${id}" w:name="${name}"/>`
  + `<w:r>${superscript ? '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr>' : ''}<w:t>${text}</w:t></w:r><w:bookmarkEnd w:id="${id}"/>`;

test('the content control carries the Windows alias and tag around exactly one m:oMath', () => {
  assert.equal(sdt, '<w:sdt><w:sdtPr><w:alias w:val="LaTeXSnipper Equation"/>'
    + `<w:tag w:val="latexsnipper-eq-${ID}|abcdef0123"/></w:sdtPr><w:sdtContent>${OMATH}</w:sdtContent></w:sdt>`);
  const para = `<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:mml="http://www.w3.org/1998/Math/MathML">${OMATH}</m:oMathPara>`;
  assert.match(extractOMath(para), /^<m:oMath[ >].*<m:t>x<\/m:t><\/m:r><\/m:oMath>$/);
  assert.doesNotMatch(extractOMath(para), /oMathPara|mml/);
  assert.throws(() => extractOMath('<m:r xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"/>'), /m:oMath/);
});

test('paragraph layouts match BuildFlatOpcDocument and the numbered tab stops', () => {
  assert.equal(formulaParagraph({sdt, display: false}), `<w:p>${sdt}</w:p>`);
  assert.equal(formulaParagraph({sdt, display: true}),
    `<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="center"/></w:pPr>${sdt}</w:p>`);
  const number = manualNumberXml(ID, '(5)', 9);
  const right = formulaParagraph({sdt, display: true, number, placement: 'Right', widthPoints: 451.3});
  assert.match(right, /<w:tab w:val="center" w:pos="4513"\/><w:tab w:val="right" w:pos="9026"\/>/);
  assert.match(right, /<w:snapToGrid w:val="0"\/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"\/><w:ind w:left="0" w:right="0" w:firstLine="0"\/><w:jc w:val="left"\/>/);
  assert.ok(right.endsWith(`<w:r><w:tab/></w:r>${sdt}<w:r><w:tab/></w:r>${number}</w:p>`));
  const left = formulaParagraph({sdt, display: true, number, placement: 'Left', widthPoints: 400});
  assert.ok(left.endsWith(`${number}<w:r><w:tab/></w:r>${sdt}</w:p>`));
  assert.match(number, new RegExp(`<w:bookmarkStart w:id="9" w:name="${BOOKMARK}"/><w:r><w:t xml:space="preserve">\\(5\\)</w:t></w:r><w:bookmarkEnd w:id="9"/>`));
});

test('automatic numbers are a SEQ field bookmarked from field begin to result end', () => {
  const xml = automaticNumberXml(ID, sequenceCode({reset: true, prefix: '', enclosure: 'Parentheses'}), '(1)', 3);
  assert.match(xml, new RegExp(`^<w:bookmarkStart w:id="3" w:name="${BOOKMARK}"/><w:r><w:fldChar w:fldCharType="begin"/>`));
  assert.match(xml, /<w:instrText xml:space="preserve"> SEQ LaTeXSnipperEquation \\r 1 \\# "'\('0'\)'" <\/w:instrText>/);
  assert.ok(xml.endsWith('<w:t xml:space="preserve">(1)</w:t></w:r><w:bookmarkEnd w:id="3"/><w:r><w:fldChar w:fldCharType="end"/></w:r>'));
});

test('document variables are read from settings.xml in the body package', () => {
  const variables = readVariables(wordPackage('<w:p/>', {settings: '<w:docVars><w:docVar w:name="LaTeXSnipper.DocumentId" w:val="abc"/>'
    + '<w:docVar w:name="LS.E.x.r" w:val="{&quot;a&quot;:&quot;中&quot;}"/></w:docVars>'}));
  assert.equal(variables.get('LaTeXSnipper.DocumentId'), 'abc');
  assert.equal(variables.get('LS.E.x.r'), '{"a":"中"}');
  assert.equal(readVariables(wordPackage('<w:p/>')).size, 0);
});

test('text width comes from the section page size, margins, gutter and equal columns', () => {
  const section = cols => wordPackage(`<w:p/><w:sectPr><w:pgSz w:w="11906" w:h="16838"/>`
    + `<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" w:gutter="106"/>${cols}</w:sectPr>`);
  assert.equal(sectionTextWidthPoints(section('')), (11906 - 3600 - 106) / 20);
  assert.equal(sectionTextWidthPoints(section('<w:cols w:num="2" w:space="425"/>')), (11906 - 3706 - 425) / 2 / 20);
  assert.equal(sectionTextWidthPoints(section('<w:cols w:num="2" w:equalWidth="0"><w:col w:w="3000" w:space="400"/><w:col w:w="4000"/></w:cols>')), 150);
});

const numbered = (number, extra = '') => wordPackage(`<w:p><w:pPr><w:jc w:val="left"/></w:pPr>${userBookmark(1, 'KeepHead', 'HEAD')}`
  + `<w:r><w:tab/></w:r>${sdt}<w:r><w:tab/></w:r>${number}${userBookmark(2, 'KeepTail', 'TAIL', true)}</w:p>${extra}`);

test('deleting a manually numbered formula removes its number and layout tabs only', () => {
  const [paragraph, ...rest] = paragraphs(deleteFormulaXml(numbered(manualNumberXml(ID, '(Q)', 7), '<w:p><w:r><w:t>next</w:t></w:r></w:p>'), ID));
  assert.equal(paragraph.text, 'HEADTAIL');
  assert.deepEqual(paragraph.tags, []);
  assert.doesNotMatch(paragraph.xml, /w:tab\/|LaTeXSnipperEq_|\(Q\)/);
  assert.match(paragraph.xml, /w:name="KeepHead".*HEAD.*w:name="KeepTail".*superscript.*TAIL/);
  assert.deepEqual(rest.map(item => item.text), ['next']);
});

test('deleting an automatically numbered formula removes the whole SEQ field', () => {
  const field = automaticNumberXml(ID, sequenceCode({reset: false, prefix: '', enclosure: 'Parentheses'}), '(4)', 7);
  const [paragraph] = paragraphs(deleteFormulaXml(numbered(field), ID));
  assert.equal(paragraph.text, 'HEADTAIL');
  assert.doesNotMatch(paragraph.xml, /fldChar|instrText|SEQ/);
});

test('a renumbered bookmark that covers only the field result still removes the field', () => {
  const code = sequenceCode({reset: false, prefix: '', enclosure: 'Parentheses'});
  const field = '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    + `<w:r><w:instrText xml:space="preserve">${code}</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>`
    + `<w:bookmarkStart w:id="7" w:name="${BOOKMARK}"/><w:r><w:t>(4)</w:t></w:r><w:bookmarkEnd w:id="7"/>`
    + '<w:r><w:fldChar w:fldCharType="end"/></w:r>';
  const [paragraph] = paragraphs(deleteFormulaXml(numbered(field), ID));
  assert.equal(paragraph.text, 'HEADTAIL');
  assert.doesNotMatch(paragraph.xml, /fldChar/);
});

test('only directly adjacent tabs are scaffolding; a user tab further away stays', () => {
  const xml = wordPackage(`<w:p><w:r><w:t>a</w:t><w:tab/></w:r><w:r><w:t>b</w:t></w:r><w:r><w:tab/></w:r>${sdt}`
    + `<w:r><w:tab/></w:r>${manualNumberXml(ID, '(1)', 4)}</w:p>`);
  const [paragraph] = paragraphs(deleteFormulaXml(xml, ID));
  assert.equal(paragraph.text, 'ab');
  assert.equal((paragraph.xml.match(/<w:tab\/>/g) || []).length, 1);
});

test('an unnumbered formula leaves neighbouring tabs alone', () => {
  const xml = wordPackage(`<w:p><w:r><w:t>a</w:t></w:r><w:r><w:tab/></w:r>${sdt}<w:r><w:tab/></w:r></w:p>`);
  assert.equal((paragraphs(deleteFormulaXml(xml, ID))[0].xml.match(/<w:tab\/>/g) || []).length, 2);
});

test('a structural update isolates the new formula and keeps text, bookmarks and the section break', () => {
  const other = '9876543210fedcba9876543210fedcba';
  const replacement = formulaParagraph({sdt: equationControl(OMATH, buildTag(ID, 'ffffffffff')), display: true,
    number: manualNumberXml(ID, '(2)', 11), widthPoints: 400});
  const source = wordPackage(`<w:p><w:pPr><w:pStyle w:val="Body"/><w:sectPr><w:pgSz w:w="100"/></w:sectPr></w:pPr>`
    + `${userBookmark(1, 'KeepHead', 'HEAD')}${sdt}${userBookmark(2, 'KeepTail', 'TAIL', true)}`
    + `<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> REF LaTeXSnipperEq_${other} \\h </w:instrText></w:r>`
    + '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>');
  const result = paragraphs(replaceFormulaXml(source, ID, replacement));
  assert.deepEqual(result.map(item => item.text), ['HEAD', '(2)', 'TAIL']);
  assert.deepEqual(result[1].tags, [buildTag(ID, 'ffffffffff')]);
  assert.match(result[0].xml, /w:pStyle w:val="Body".*KeepHead/);
  assert.doesNotMatch(result[0].xml, /sectPr/);
  assert.match(result[2].xml, /w:pStyle w:val="Body".*<w:sectPr>.*KeepTail.*superscript.*REF LaTeXSnipperEq_/);
});

test('a formula alone in its paragraph is replaced in place', () => {
  const replacement = formulaParagraph({sdt, display: true, number: manualNumberXml(ID, '(1)', 5), widthPoints: 300});
  const result = paragraphs(replaceFormulaXml(wordPackage(`<w:p><w:pPr><w:jc w:val="center"/></w:pPr>${userBookmark(3, 'Mark', '')}${sdt}</w:p>`), ID, replacement));
  assert.equal(result.length, 1);
  assert.match(result[0].xml, /w:name="Mark"/);
  assert.match(result[0].xml, /w:tab w:val="right" w:pos="6000"/);
});
