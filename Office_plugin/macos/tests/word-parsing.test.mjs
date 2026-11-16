import assert from 'node:assert/strict';
import test from 'node:test';
import {paragraphs, wordPackage} from './dom.mjs';
import {applyCandidates, findCandidates, paragraphGroups, processTag, scanLatex} from '../web/app/word/parsing.mjs';

const run = (text, properties = '') => `<w:r>${properties ? `<w:rPr>${properties}</w:rPr>` : ''}<w:t xml:space="preserve">${text}</w:t></w:r>`;
const para = (...content) => `<w:p>${content.join('')}</w:p>`;
const sdtXml = name => `<w:sdt><w:sdtPr><w:tag w:val="${name}"/></w:sdtPr><w:sdtContent><m:oMath/></w:sdtContent></w:sdt>`;
const formulaParagraphXml = name => `<w:p><w:pPr><w:jc w:val="center"/></w:pPr>${sdtXml(name)}</w:p>`;
const sources = text => scanLatex(text).map(match => match.originalText);

test('the scanner reproduces the Windows parsing fixture', () => {
  assert.deepEqual(sources('$E_{\\mathrm{start}}=0$ and $q(t)$, \\(p_i=\\frac{\\partial L}{\\partial\\dot q_i}\\)'),
    ['$E_{\\mathrm{start}}=0$', '$q(t)$', '\\(p_i=\\frac{\\partial L}{\\partial\\dot q_i}\\)']);
  assert.deepEqual(sources('$q$$\\dot q$$\\ddot q$'), ['$q$', '$\\dot q$', '$\\ddot q$']);
  assert.deepEqual(sources('价格 \\$100'), []);
  assert.deepEqual(sources('\\\\$x$'), ['$x$']);
  assert.deepEqual(sources('$C(q)=\\$100+q$'), ['$C(q)=\\$100+q$']);
  assert.deepEqual(sources('\\\\(a+b\\)'), []);
  assert.deepEqual(sources('\\\\\\(a-b\\)'), ['\\(a-b\\)']);
  assert.deepEqual(sources('\\\\[a+b\\]'), []);
  assert.deepEqual(sources('\\\\\\[a-b\\]'), ['\\[a-b\\]']);
  assert.deepEqual(sources('\\(a+\\text{\\$100}\\) \\[E=\\text{price \\$100}\\]'), ['\\(a+\\text{\\$100}\\)', '\\[E=\\text{price \\$100}\\]']);
  assert.deepEqual(sources('$a+\\text{\\(literal\\)}$'), ['$a+\\text{\\(literal\\)}$']);
  assert.deepEqual(sources('孤立结束符号 $、\\) 和 \\] 不会成为公式'), []);
  assert.deepEqual(sources('$   $ \\(   \\) $$$$ \\[   \\]'), []);
  assert.deepEqual(sources('$\\frac{\\partial L}{\\partial q}\rnext'), []);
  assert.deepEqual(sources('$$a+b\r…$x$…\r…$$c=d$$'), ['$x$', '$$c=d$$']);
  assert.deepEqual(sources('$$E=mc^2 % \\tag{ignored}\r+0$$'), ['$$E=mc^2 % \\tag{ignored}\r+0$$']);
  assert.deepEqual(sources('$a\x07b$ $c\0d$'), []);
  assert.equal(scanLatex('$$ x\u00a0$$')[0].latex, 'x');
});

test('\\tag becomes a manual number only once, at top level, in display formulas', () => {
  assert.deepEqual(processTag('\\frac{\\partial F}{\\partial y}=0\\tag{5}', true), {latex: '\\frac{\\partial F}{\\partial y}=0', numberText: '5'});
  assert.deepEqual(processTag('E=mc^2\\tag {  7  }', true), {latex: 'E=mc^2', numberText: '7'});
  assert.deepEqual(processTag('\\tag{8}E=mc^2', true), {latex: 'E=mc^2', numberText: '8'});
  assert.deepEqual(processTag('E=mc^2 % \\tag{ignored}\r+0', true), {latex: 'E=mc^2 % \\tag{ignored}\r+0', numberText: null});
  assert.deepEqual(processTag('x\\tagx', true), {latex: 'x\\tagx', numberText: null});
  for (const invalid of ['E=T+V\\tag{}', 'm\\ddot q+kq=0\\tag{A}\\tag{B}', '\\ddot q+\\omega^2q=0\\tag{osc',
    '\\frac{\\partial L}{\\partial q}=0\\tag*{star}', '\\tag{9}', '{x\\tag{1}}'])
    assert.equal(processTag(invalid, true), null, invalid);
  assert.equal(processTag('x\\tag{1}', false), null);
});

test('content controls, fields, hyperlinks, equations, comments and code paragraphs are never parsed', () => {
  const xml = wordPackage([
    para(run('A $a$ '), sdtXml('other').replace('<m:oMath/>', run('$unsafe$')), run(' $b$')),
    para('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> QUOTE "$field$" </w:instrText></w:r>',
      '<w:r><w:fldChar w:fldCharType="separate"/></w:r>', run('$field$'), '<w:r><w:fldChar w:fldCharType="end"/></w:r>', run(' $c$')),
    para('<w:hyperlink w:anchor="x">', run('$link$'), '</w:hyperlink>', '<m:oMath><m:r><m:t>$m$</m:t></m:r></m:oMath>'),
    para('<w:commentRangeStart w:id="0"/>', run('$commented$'), '<w:commentRangeEnd w:id="0"/>', run('$d$')),
    para(run('$a'), '<w:ins w:id="1"><w:r><w:t>+b</w:t></w:r></w:ins>', run('$')),
    '<w:p><w:pPr><w:pStyle w:val="HTMLCode"/></w:pPr>' + run('$code$') + '</w:p>',
  ].join(''), {styles: '<w:style w:styleId="HTMLCode"><w:name w:val="HTML Code"/></w:style>'});
  assert.deepEqual(findCandidates(xml).map(item => item.originalText), ['$a$', '$b$', '$c$', '$d$']);
});

test('with selection markers only formulas wholly inside the selection are found', () => {
  const marker = name => `<w:bookmarkStart w:id="90" w:name="${name}"/><w:bookmarkEnd w:id="90"/>`;
  const markers = {start: '_LSParseA', end: '_LSParseB'};
  const xml = wordPackage(para(run('$x$ $y'), marker('_LSParseA'), run('$z$ $w'), marker('_LSParseB'), run('$')));
  assert.deepEqual(findCandidates(xml, markers).map(item => item.originalText), ['$z$']);
  const later = wordPackage(para(run('$x$')) + para(run('$y$'), marker('_LSParseB'), run('$z$')));
  assert.deepEqual(findCandidates(later, markers).map(item => item.originalText), ['$x$', '$y$']);
  const result = applyCandidates(later, [], markers);
  assert.doesNotMatch(result, /_LSParse/);
});

test('inline replacement keeps surrounding runs, their formatting and bookmarks', () => {
  const xml = wordPackage(para(run('前 $x', '<w:b/>'), run('+y$', '<w:i/>'),
    '<w:bookmarkStart w:id="1" w:name="Tail"/>', run(' 后', '<w:vertAlign w:val="superscript"/>'), '<w:bookmarkEnd w:id="1"/>'));
  const [candidate] = findCandidates(xml);
  assert.equal(candidate.latex, 'x+y');
  const [paragraph] = paragraphs(applyCandidates(xml, [{...candidate, xml: {sdt: sdtXml('new')}}]));
  assert.equal(paragraph.text, '前  后');
  assert.deepEqual(paragraph.tags, ['new']);
  assert.match(paragraph.xml, /<w:b\/><\/w:rPr><w:t xml:space="preserve">前 <\/w:t><\/w:r><w:sdt>.*<\/w:sdt><w:bookmarkStart w:id="1" w:name="Tail"\/><w:r><w:rPr><w:vertAlign w:val="superscript"\/><\/w:rPr><w:t xml:space="preserve"> 后/);
  assert.doesNotMatch(paragraph.xml, /x\+y|\$/);
});

test('several formulas in one paragraph are replaced last to first', () => {
  const xml = wordPackage(para(run('a $1$ b $2$ c')));
  const candidates = findCandidates(xml).map((item, index) => ({...item, xml: {sdt: sdtXml('f' + index)}}));
  const [paragraph] = paragraphs(applyCandidates(xml, candidates));
  assert.equal(paragraph.text, 'a  b  c');
  assert.deepEqual(paragraph.tags, ['f0', 'f1']);
});

test('a display formula with text around it gets its own paragraph', () => {
  const xml = wordPackage('<w:p><w:pPr><w:pStyle w:val="Body"/></w:pPr>' + run('前文 $$x=0$$ 后文。') + '</w:p>');
  const [candidate] = findCandidates(xml);
  const result = paragraphs(applyCandidates(xml, [{...candidate, xml: {paragraph: formulaParagraphXml('d')}}]));
  assert.deepEqual(result.map(item => [item.text, item.tags]), [['前文 ', []], ['', ['d']], [' 后文。', []]]);
  assert.match(result[0].xml, /Body/);
  assert.match(result[2].xml, /Body/);
});

test('a display formula across paragraphs collapses into one; whitespace around it goes too', () => {
  const xml = wordPackage(para(run('  \\[\\begin{aligned}')) + para(run('a&=b')) + para(run('\\end{aligned}\\] '))
    + '<w:p><w:pPr><w:sectPr/></w:pPr>' + run('after') + '</w:p>');
  const [candidate] = findCandidates(xml);
  assert.equal(candidate.latex, '\\begin{aligned}\ra&=b\r\\end{aligned}');
  const result = paragraphs(applyCandidates(xml, [{...candidate, xml: {paragraph: formulaParagraphXml('m')}}]));
  assert.deepEqual(result.map(item => [item.text, item.tags]), [['', ['m']], ['after', []]]);
});

test('the font size of the source text is reported only when it is uniform', () => {
  const xml = wordPackage(para(run('$a$', '<w:sz w:val="28"/>'), run(' $b', '<w:sz w:val="28"/>'), run('c$', '<w:sz w:val="20"/>'), run(' $d$')),
    {styles: '<w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>'});
  assert.deepEqual(findCandidates(xml).map(item => item.fontSizePoints), [14, 0, 10.5]);
});

test('paragraph groups join the paragraphs a display formula spans', () => {
  assert.deepEqual(paragraphGroups([['plain', '$$a', 'b$$', 'x', '$y$'], ['cell $z$']]),
    [[0, 1, 2], [0, 4, 4], [1, 0, 0]]);
});
