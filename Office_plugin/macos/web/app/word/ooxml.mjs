// WordprocessingML built and rewritten exactly as WordOmmlDocumentBuilder and the
// Windows formula lifecycle do. Everything here is pure: it takes and returns
// XML strings, so it runs the same in the task pane and in Node tests. Only DOM
// Level 2 core methods are used, which both browsers and @xmldom provide.
import {
  EQUATION_TITLE, SEQUENCE_MARKER, bookmarkName, equationIdFromTag,
} from './contract.mjs';

export const NS = {
  w: 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
  m: 'http://schemas.openxmlformats.org/officeDocument/2006/math',
  w15: 'http://schemas.microsoft.com/office/word/2012/wordml',
  pkg: 'http://schemas.microsoft.com/office/2006/xmlPackage',
};
const DOCUMENT_PART = '/word/document.xml';
const SETTINGS_PART = '/word/settings.xml';
const STYLES_PART = '/word/styles.xml';
// Zero-width markup that sits between characters without being content.
const MARKUP = new Set(['bookmarkStart', 'bookmarkEnd', 'proofErr', 'permStart', 'permEnd',
  'commentRangeStart', 'commentRangeEnd', 'moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart',
  'moveToRangeEnd', 'customXmlInsRangeStart', 'customXmlInsRangeEnd', 'customXmlDelRangeStart',
  'customXmlDelRangeEnd', 'lastRenderedPageBreak']);
const TWIPS_PER_POINT = 20;
const DEFAULT_CELL_MARGIN_TWIPS = 108;

export function escapeXml(value) {
  return String(value).replace(/[<>&"']/g, character =>
    ({'<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;'})[character]);
}

const escapeText = value => String(value).replace(/[<>&]/g, character => ({'<': '&lt;', '>': '&gt;', '&': '&amp;'})[character]);

// Packages -----------------------------------------------------------------------

export function flatPackage(bodyXml) {
  return '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">'
    + '<pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml" pkg:padding="512"><pkg:xmlData>'
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    + '</pkg:xmlData></pkg:part>'
    + '<pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"><pkg:xmlData>'
    + `<w:document xmlns:w="${NS.w}" xmlns:w15="${NS.w15}" xmlns:m="${NS.m}"><w:body>${bodyXml}</w:body></w:document>`
    + '</pkg:xmlData></pkg:part></pkg:package>';
}

export function parseXml(xml) {
  const document = new DOMParser().parseFromString(xml, 'application/xml');
  const root = document.documentElement;
  if (!root || root.localName === 'parsererror' || root.getElementsByTagName('parsererror').length)
    throw new Error('Word 返回的 OOXML 无效。');
  return document;
}

export const serializeXml = node => new XMLSerializer().serializeToString(node);

function part(document, name) {
  for (const element of elements(document, NS.pkg, 'part'))
    if (element.getAttributeNS(NS.pkg, 'name') === name) return element;
  return null;
}

/** The w:body of a flat-OPC package returned by getOoxml(). */
export function packageBody(document) {
  const documentPart = part(document, DOCUMENT_PART);
  const body = documentPart && first(documentPart, NS.w, 'body');
  if (!body) throw new Error('Word 返回的 OOXML 缺少正文。');
  return body;
}

/** Word document variables (w:docVars in settings.xml) from a body.getOoxml() package. */
export function readVariables(packageXml) {
  const settings = part(parseXml(packageXml), SETTINGS_PART);
  const variables = new Map();
  if (!settings) return variables;
  for (const variable of elements(settings, NS.w, 'docVar'))
    variables.set(variable.getAttributeNS(NS.w, 'name'), variable.getAttributeNS(NS.w, 'val'));
  return variables;
}

// Formula XML --------------------------------------------------------------------

/** ExtractEquationOmml: the first m:oMath; an m:oMathPara wrapper is dropped. */
export function extractOMath(omml) {
  const document = parseXml(String(omml).replace(' xmlns:mml="http://www.w3.org/1998/Math/MathML"', ''));
  const root = document.documentElement;
  const math = root.localName === 'oMath' ? root : first(root, NS.m, 'oMath');
  if (!math) throw new Error('OMML 中未找到 m:oMath 公式。');
  return serializeXml(math);
}

export function equationControl(oMathXml, tag) {
  return `<w:sdt><w:sdtPr><w:alias w:val="${EQUATION_TITLE}"/><w:tag w:val="${escapeXml(tag)}"/></w:sdtPr>`
    + `<w:sdtContent>${oMathXml}</w:sdtContent></w:sdt>`;
}

const TAB_RUN = '<w:r><w:tab/></w:r>';

export function manualNumberXml(equationId, text, bookmarkId) {
  return `<w:bookmarkStart w:id="${bookmarkId}" w:name="${bookmarkName(equationId)}"/>`
    + `<w:r><w:t xml:space="preserve">${escapeText(text)}</w:t></w:r><w:bookmarkEnd w:id="${bookmarkId}"/>`;
}

/** A SEQ field whose bookmark spans field begin to result end, like InsertEquationNumberAtRange. */
export function automaticNumberXml(equationId, code, result, bookmarkId) {
  return `<w:bookmarkStart w:id="${bookmarkId}" w:name="${bookmarkName(equationId)}"/>`
    + '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    + `<w:r><w:instrText xml:space="preserve">${escapeText(code)}</w:instrText></w:r>`
    + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    + `<w:r><w:t xml:space="preserve">${escapeText(result)}</w:t></w:r>`
    + `<w:bookmarkEnd w:id="${bookmarkId}"/><w:r><w:fldChar w:fldCharType="end"/></w:r>`;
}

/**
 * One formula paragraph (BuildFlatOpcDocument plus ApplyNumberedFormulaParagraphLayout,
 * whose tab stops Windows sets after insertion and Office.js can only write as XML).
 * `number` is the number XML for numbered formulas; `widthPoints` the text width.
 */
export function formulaParagraph({sdt, display, number = null, placement = 'Right', widthPoints = 0}) {
  if (!display) return `<w:p>${sdt}</w:p>`;
  if (number === null)
    return `<w:p><w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="center"/></w:pPr>${sdt}</w:p>`;
  const width = Math.max(1, Math.round(widthPoints * TWIPS_PER_POINT));
  const properties = '<w:pPr><w:tabs>'
    + `<w:tab w:val="center" w:pos="${Math.round(width / 2)}"/><w:tab w:val="right" w:pos="${width}"/></w:tabs>`
    + '<w:snapToGrid w:val="0"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
    + '<w:ind w:left="0" w:right="0" w:firstLine="0"/><w:jc w:val="left"/></w:pPr>';
  const content = placement === 'Left' ? number + TAB_RUN + sdt : TAB_RUN + sdt + TAB_RUN + number;
  return `<w:p>${properties}${content}</w:p>`;
}

// Layout -------------------------------------------------------------------------

const twips = (element, name) => Number.parseInt(element?.getAttributeNS(NS.w, name) || '0', 10) || 0;

/**
 * GetEquationContentWidthPoints for body text, from the w:sectPr of the
 * paragraph's section: one column, or equal columns. Unequal columns need
 * Word's layout, which Office.js does not expose; the first column is used.
 */
export function sectionTextWidthPoints(sectionXml) {
  const document = parseXml(sectionXml);
  const sections = elements(document, NS.w, 'sectPr');
  const section = sections[sections.length - 1];
  if (!section) throw new Error('Word 无法确定公式所在栏的位置。');
  const size = first(section, NS.w, 'pgSz');
  const margin = first(section, NS.w, 'pgMar');
  let width = twips(size, 'w') - twips(margin, 'left') - twips(margin, 'right') - twips(margin, 'gutter');
  const columns = first(section, NS.w, 'cols');
  const count = Number.parseInt(columns?.getAttributeNS(NS.w, 'num') || '1', 10) || 1;
  if (count > 1) {
    const explicit = elements(columns, NS.w, 'col');
    const equal = columns.getAttributeNS(NS.w, 'equalWidth') !== '0' && columns.getAttributeNS(NS.w, 'equalWidth') !== 'false';
    if (!equal && explicit.length) width = twips(explicit[0], 'w');
    else width = (width - (count - 1) * (twips(columns, 'space') || 720)) / count;
  }
  if (!(width > 0)) throw new Error('Word 无法确定公式所在栏的位置。');
  return width / TWIPS_PER_POINT;
}

/** Cell width minus its left and right padding (Word's default padding is 108 twips). */
export function cellTextWidthPoints(cellWidthPoints, leftPaddingPoints, rightPaddingPoints) {
  const padding = value => Number.isFinite(value) && value >= 0 ? value : DEFAULT_CELL_MARGIN_TWIPS / TWIPS_PER_POINT;
  return Math.max(1, cellWidthPoints - padding(leftPaddingPoints) - padding(rightPaddingPoints));
}

// Rewriting paragraphs -------------------------------------------------------------

/** Parses `xml` (paragraph or run markup) into nodes owned by `document`. */
export function importNodes(document, xml) {
  const wrapper = parseXml(`<w:body xmlns:w="${NS.w}" xmlns:w15="${NS.w15}" xmlns:m="${NS.m}">${xml}</w:body>`);
  return [...wrapper.documentElement.childNodes].map(node => document.importNode(node, true));
}

export function elements(node, ns, localName) {
  return [...node.getElementsByTagNameNS(ns, localName)];
}

function first(node, ns, localName) {
  return node.getElementsByTagNameNS(ns, localName)[0] || null;
}

const isW = (node, name) => node?.nodeType === 1 && node.namespaceURI === NS.w && node.localName === name;
const childElements = node => [...node.childNodes].filter(child => child.nodeType === 1);

export function controlTag(sdt) {
  const properties = childElements(sdt).find(child => isW(child, 'sdtPr'));
  const tag = properties && childElements(properties).find(child => isW(child, 'tag'));
  return tag ? tag.getAttributeNS(NS.w, 'val') : '';
}

/** The managed content control for `equationId` and its paragraph, or null. */
export function findFormulaControl(root, equationId) {
  for (const sdt of elements(root, NS.w, 'sdt')) {
    if (equationIdFromTag(controlTag(sdt)) !== equationId) continue;
    let paragraph = sdt.parentNode;
    while (paragraph && !isW(paragraph, 'p')) paragraph = paragraph.parentNode;
    return paragraph ? {sdt, paragraph} : null;
  }
  return null;
}

/** The child of `paragraph` that contains `node`. */
function topLevel(paragraph, node) {
  let current = node;
  while (current && current.parentNode !== paragraph) current = current.parentNode;
  return current;
}

const isContent = node => node.nodeType === 1 && !isW(node, 'pPr') && !MARKUP.has(node.localName)
  && !(isW(node, 'r') && childElements(node).every(child => isW(child, 'rPr') || (isW(child, 't') && !child.textContent)));

/** Maps each direct child of a paragraph to the complex field it belongs to, if any. */
function complexFields(paragraph) {
  const fields = [];
  const stack = [];
  for (const [index, child] of childElements(paragraph).entries()) {
    if (!isW(child, 'r')) continue;
    for (const item of childElements(child)) {
      if (isW(item, 'fldChar')) {
        const type = item.getAttributeNS(NS.w, 'fldCharType');
        if (type === 'begin') stack.push({begin: index, end: -1, code: ''});
        else if (type === 'end' && stack.length) {
          const field = stack.pop();
          field.end = index;
          fields.push(field);
        }
      } else if (isW(item, 'instrText') && stack.length) {
        stack[stack.length - 1].code += item.textContent;
      }
    }
  }
  return fields;
}

/**
 * Removes the number that the bookmark LaTeXSnipperEq_<id> owns. When the
 * bookmark lies on a SEQ field, the whole field goes, so no empty field shell
 * stays behind (Windows deletes the bookmarked span). Returns whether the
 * formula was numbered.
 */
function removeNumber(paragraph, equationId, sdt) {
  const name = bookmarkName(equationId);
  const start = elements(paragraph, NS.w, 'bookmarkStart').find(item => item.getAttributeNS(NS.w, 'name') === name);
  if (!start) return false;
  const id = start.getAttributeNS(NS.w, 'id');
  const end = elements(paragraph, NS.w, 'bookmarkEnd').find(item => item.getAttributeNS(NS.w, 'id') === id);
  const children = childElements(paragraph);
  const from = children.indexOf(topLevel(paragraph, start));
  const to = end ? children.indexOf(topLevel(paragraph, end)) : from;
  const formula = children.indexOf(topLevel(paragraph, sdt));
  if (from < 0 || to < from || (formula >= from && formula <= to)) {
    start.parentNode.removeChild(start);
    end?.parentNode.removeChild(end);
    return true;
  }
  let first = from;
  let last = to;
  for (const field of complexFields(paragraph)) {
    if (!field.code.includes(SEQUENCE_MARKER) || field.end < first || field.begin > last) continue;
    first = Math.min(first, field.begin);
    last = Math.max(last, field.end);
  }
  for (const child of children.slice(first, last + 1)) paragraph.removeChild(child);
  return true;
}

/** Removes one tab character directly before (`side` -1) or after (+1) `anchor`. */
function removeAdjacentTab(paragraph, anchor, side) {
  let node = side < 0 ? anchor.previousSibling : anchor.nextSibling;
  while (node && !isContent(node)) node = side < 0 ? node.previousSibling : node.nextSibling;
  if (!isW(node, 'r')) return;
  const items = childElements(node).filter(child => !isW(child, 'rPr'));
  const edge = side < 0 ? items[items.length - 1] : items[0];
  if (!isW(edge, 'tab')) return;
  node.removeChild(edge);
  if (items.length === 1) paragraph.removeChild(node);
}

/**
 * RemoveFormulaForReplacement: deletes the formula's number, its content
 * control and the layout tabs right next to it, keeping all other content of
 * the paragraph. Returns the node the formula was in front of (null = end).
 */
function removeFormula(paragraph, sdt, equationId) {
  const numbered = removeNumber(paragraph, equationId, sdt);
  const anchor = topLevel(paragraph, sdt);
  if (numbered) {
    removeAdjacentTab(paragraph, anchor, -1);
    removeAdjacentTab(paragraph, anchor, 1);
  }
  const next = anchor.nextSibling;
  if (anchor === sdt) paragraph.removeChild(sdt);
  else sdt.parentNode.removeChild(sdt);
  return next;
}

function cloneParagraph(paragraph, nodes, keepSection) {
  const clone = paragraph.ownerDocument.createElementNS(NS.w, 'w:p');
  const properties = childElements(paragraph).find(child => isW(child, 'pPr'));
  if (properties) {
    const copy = properties.cloneNode(true);
    if (!keepSection) for (const section of childElements(copy).filter(child => isW(child, 'sectPr'))) copy.removeChild(section);
    clone.appendChild(copy);
  }
  for (const node of nodes) clone.appendChild(node);
  return clone;
}

/**
 * Puts `replacement` (one formula paragraph) where `paragraph`'s children
 * from `before` on would start, isolating it from the user's content on
 * either side the way Windows inserts paragraph marks: content before and
 * after stays in paragraphs of its own with the original properties.
 * Zero-width markup (bookmarks) next to the formula moves into its paragraph,
 * so neighbouring bookmarks keep their place. A section break stays last.
 */
export function isolateParagraph(paragraph, before, replacement) {
  const children = [...paragraph.childNodes].filter(child => !isW(child, 'pPr'));
  const split = before ? children.indexOf(before) : children.length;
  const leading = children.slice(0, split);
  const trailing = children.slice(split);
  const hasLeading = leading.some(isContent);
  const hasTrailing = trailing.some(isContent);
  const properties = childElements(paragraph).find(child => isW(child, 'pPr'));
  const section = properties && childElements(properties).find(child => isW(child, 'sectPr'));
  const replacementProperties = childElements(replacement).find(child => isW(child, 'pPr'));
  const firstContent = replacementProperties ? replacementProperties.nextSibling : replacement.firstChild;
  if (!hasLeading) for (const node of leading) replacement.insertBefore(node, firstContent);
  if (!hasTrailing) for (const node of trailing) replacement.appendChild(node);
  const result = [];
  if (hasLeading) result.push(cloneParagraph(paragraph, leading, false));
  result.push(replacement);
  if (hasTrailing) result.push(cloneParagraph(paragraph, trailing, false));
  if (section) {
    const last = result[result.length - 1];
    const lastProperties = childElements(last).find(child => isW(child, 'pPr'))
      || last.insertBefore(last.ownerDocument.createElementNS(NS.w, 'w:pPr'), last.firstChild);
    lastProperties.appendChild(section.cloneNode(true));
  }
  const parent = paragraph.parentNode;
  for (const node of result) parent.insertBefore(node, paragraph);
  parent.removeChild(paragraph);
  return result;
}

/** Deletes a formula with its number and layout tabs; the paragraph stays. */
export function deleteFormulaXml(packageXml, equationId) {
  const document = parseXml(packageXml);
  const found = findFormulaControl(packageBody(document), equationId);
  if (!found) throw new Error('无法找到所选公式。');
  removeFormula(found.paragraph, found.sdt, equationId);
  return serializeXml(document);
}

/**
 * Replaces a formula and its number by `paragraphXml` (a display formula
 * paragraph), the structural update path of UpdateFormulaAsync.
 */
export function replaceFormulaXml(packageXml, equationId, paragraphXml) {
  const document = parseXml(packageXml);
  const found = findFormulaControl(packageBody(document), equationId);
  if (!found) throw new Error('无法找到所选公式。');
  const before = removeFormula(found.paragraph, found.sdt, equationId);
  const [replacement] = importNodes(document, paragraphXml);
  isolateParagraph(found.paragraph, before, replacement);
  return serializeXml(document);
}

/** Whether the first paragraph of a package holds anything besides properties and zero-width markup. */
export function paragraphHasContent(packageXml) {
  const paragraph = childElements(packageBody(parseXml(packageXml))).find(child => isW(child, 'p'));
  return Boolean(paragraph && childElements(paragraph).some(isContent));
}
