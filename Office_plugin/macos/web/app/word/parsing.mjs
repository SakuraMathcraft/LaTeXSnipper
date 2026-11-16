// "Parse Selected" / "Parse All": LatexDelimiterScanner and LatexTagPreprocessor
// from the Windows add-in, applied to the OOXML of the paragraphs that contain
// delimiters. The text is built from the paragraph runs only: content controls,
// fields, equations, pictures, hyperlinks, comments, tracked changes and code
// paragraphs become hard boundaries, which is how Windows' unsafe spans work.
import {NS, elements, importNodes, isolateParagraph, packageBody, parseXml, serializeXml} from './ooxml.mjs';

const UNSAFE = '\0';
const CELL_END = '\x07';
const CODE_STYLES = new Set(['code', 'html code', 'html preformatted', 'preformatted', '代码', 'html 代码', 'html 预设格式']);
// .NET char.IsWhiteSpace, which String.Trim() uses; it differs from JS trim() at U+0085 and U+FEFF.
const WHITESPACE = /[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/u;

export function dotnetTrim(text) {
  let start = 0;
  let end = text.length;
  while (start < end && WHITESPACE.test(text[start])) start++;
  while (end > start && WHITESPACE.test(text[end - 1])) end--;
  return text.slice(start, end);
}

// Scanner --------------------------------------------------------------------------

const isHard = character => character === UNSAFE || character === CELL_END;
const matchesAt = (text, index, value) => index >= 0 && text.startsWith(value, index);

function isEscaped(text, index) {
  let count = 0;
  for (let cursor = index - 1; cursor >= 0 && text[cursor] === '\\'; cursor--) count++;
  return count % 2 === 1;
}

const DELIMITERS = [
  {open: '$$', close: '$$', kind: 'DisplayDollar', display: true},
  {open: '$', close: '$', kind: 'InlineDollar', display: false},
  {open: '\\(', close: '\\)', kind: 'InlineParenthesis', display: false},
  {open: '\\[', close: '\\]', kind: 'DisplayBracket', display: true},
];

function openingDelimiter(text, index) {
  if (isHard(text[index])) return null;
  return DELIMITERS.find(delimiter => matchesAt(text, index, delimiter.open) && !isEscaped(text, index)) || null;
}

function closingDelimiter(text, start, delimiter) {
  for (let index = start; index <= text.length - delimiter.close.length; index++) {
    const character = text[index];
    if (isHard(character)) return -1;
    if (!delimiter.display && (character === '\r' || character === '\n')) return -1;
    if (matchesAt(text, index, delimiter.close) && !isEscaped(text, index)) return index;
  }
  return -1;
}

function containsTopLevelOpening(text, start, end) {
  let depth = 0;
  let comment = false;
  for (let index = start; index < end; index++) {
    const character = text[index];
    if (comment) {
      if (character === '\r' || character === '\n') comment = false;
      continue;
    }
    if (isEscaped(text, index)) continue;
    if (character === '%') comment = true;
    else if (character === '{') depth++;
    else if (character === '}') depth = Math.max(0, depth - 1);
    else if (depth === 0 && openingDelimiter(text, index)) return true;
  }
  return false;
}

/** LatexDelimiterScanner.Scan: delimited formulas in document order. */
export function scanLatex(text) {
  const matches = [];
  let index = 0;
  while (index < text.length) {
    const delimiter = openingDelimiter(text, index);
    if (!delimiter) { index++; continue; }
    const contentStart = index + delimiter.open.length;
    const close = closingDelimiter(text, contentStart, delimiter);
    if (close < 0 || containsTopLevelOpening(text, contentStart, close)) {
      index += delimiter.open.length;
      continue;
    }
    const end = close + delimiter.close.length;
    const latex = dotnetTrim(text.slice(contentStart, close));
    if (latex) matches.push({offset: index, length: end - index, originalText: text.slice(index, end), latex,
      kind: delimiter.kind, display: delimiter.display});
    index = end;
  }
  return matches;
}

/** LatexTagPreprocessor.Process: extracts one top-level \tag{…} from a display formula. */
export function processTag(latex, display) {
  if (!dotnetTrim(latex || '')) return null;
  let depth = 0;
  let comment = false;
  let tag = null;
  const isTag = index => matchesAt(latex, index, '\\tag') && !isEscaped(latex, index)
    && !(index + 4 < latex.length && /\p{L}/u.test(latex[index + 4]));
  for (let index = 0; index < latex.length; index++) {
    const character = latex[index];
    if (comment) {
      if (character === '\r' || character === '\n') comment = false;
      continue;
    }
    if (character === '%' && !isEscaped(latex, index)) { comment = true; continue; }
    if (character === '{' && !isEscaped(latex, index)) { depth++; continue; }
    if (character === '}' && !isEscaped(latex, index)) { depth = Math.max(0, depth - 1); continue; }
    if (!isTag(index)) continue;
    if (!display || depth !== 0 || tag) return null;
    let cursor = index + 4;
    if (latex[cursor] === '*') return null;
    while (cursor < latex.length && WHITESPACE.test(latex[cursor])) cursor++;
    if (latex[cursor] !== '{') return null;
    const closing = groupEnd(latex, cursor);
    if (closing < 0) return null;
    const value = dotnetTrim(latex.slice(cursor + 1, closing));
    if (!value) return null;
    tag = {start: index, end: closing + 1, value};
    index = closing;
  }
  if (!tag) return {latex: dotnetTrim(latex), numberText: null};
  const cleaned = dotnetTrim(latex.slice(0, tag.start) + latex.slice(tag.end));
  return cleaned ? {latex: cleaned, numberText: tag.value} : null;
}

function groupEnd(text, open) {
  let depth = 0;
  for (let index = open; index < text.length; index++) {
    if (isEscaped(text, index)) continue;
    if (text[index] === '{') depth++;
    else if (text[index] === '}' && --depth === 0) return index;
  }
  return -1;
}

/** Whether Office.js paragraph text might hold a formula; the OOXML scan decides. */
export const mayContainLatex = text => text.includes('$') || text.includes('\\(') || text.includes('\\[');

/**
 * Groups paragraphs that a formula may span. `regions` are lists of paragraph
 * texts (body text between tables, or one table cell). Returns [region, first,
 * last] index triples in document order.
 */
export function paragraphGroups(regions) {
  const groups = [];
  for (const [region, texts] of regions.entries()) {
    const starts = [];
    let offset = 0;
    for (const text of texts) { starts.push(offset); offset += text.length + 1; }
    const paragraphAt = position => {
      let index = 0;
      while (index + 1 < starts.length && starts[index + 1] <= position) index++;
      return index;
    };
    const spans = texts.map((text, index) => mayContainLatex(text) ? [index, index] : null).filter(Boolean);
    for (const match of scanLatex(texts.join('\r')))
      spans.push([paragraphAt(match.offset), paragraphAt(match.offset + match.length - 1)]);
    spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    for (const [first, last] of spans) {
      const previous = groups[groups.length - 1];
      if (previous && previous[0] === region && first <= previous[2]) previous[2] = Math.max(previous[2], last);
      else groups.push([region, first, last]);
    }
  }
  return groups;
}

// Paragraph text -------------------------------------------------------------------

const isW = (node, name) => node?.nodeType === 1 && node.namespaceURI === NS.w && node.localName === name;
const childElements = node => [...node.childNodes].filter(child => child.nodeType === 1);
const ZERO_WIDTH = new Set(['bookmarkStart', 'bookmarkEnd', 'proofErr', 'permStart', 'permEnd',
  'lastRenderedPageBreak', 'commentRangeStart', 'commentRangeEnd']);

function styleNames(document) {
  const names = new Map();
  for (const style of elements(document, NS.w, 'style')) {
    const name = childElements(style).find(child => isW(child, 'name'));
    names.set(style.getAttributeNS(NS.w, 'styleId'), String(name?.getAttributeNS(NS.w, 'val') || ''));
  }
  return names;
}

function isCodeParagraph(paragraph, names) {
  const properties = childElements(paragraph).find(child => isW(child, 'pPr'));
  const style = properties && childElements(properties).find(child => isW(child, 'pStyle'));
  if (!style) return false;
  const id = style.getAttributeNS(NS.w, 'val');
  return CODE_STYLES.has((names.get(id) || id).trim().toLowerCase());
}

/**
 * The scannable text of consecutive paragraphs, one atom per character. Atoms
 * point back at the w:t / w:tab / w:br they came from; anything that is not
 * plain run text becomes a single hard boundary.
 */
export function paragraphText(paragraphs, names, markers = {}) {
  let text = '';
  const atoms = [];
  let selectionStart = null;
  let selectionEnd = null;
  let comments = 0;
  let fields = 0;
  const push = (character, atom) => { text += character; atoms.push(atom); };
  const unsafe = paragraph => {
    if (text[text.length - 1] !== UNSAFE || atoms[atoms.length - 1]?.paragraph !== paragraph)
      push(UNSAFE, {kind: 'unsafe', paragraph});
  };
  for (const [index, paragraph] of paragraphs.entries()) {
    if (index) push('\r', {kind: 'paragraph', paragraph});
    if (isCodeParagraph(paragraph, names)) { unsafe(paragraph); continue; }
    for (const child of childElements(paragraph)) {
      if (isW(child, 'pPr')) continue;
      if (isW(child, 'bookmarkStart')) {
        const name = child.getAttributeNS(NS.w, 'name');
        if (name === markers.start) selectionStart = text.length;
        if (name === markers.end) selectionEnd = text.length;
        continue;
      }
      if (isW(child, 'commentRangeStart')) { comments++; unsafe(paragraph); continue; }
      if (isW(child, 'commentRangeEnd')) { comments = Math.max(0, comments - 1); continue; }
      if (child.namespaceURI === NS.w && ZERO_WIDTH.has(child.localName)) continue;
      if (!isW(child, 'r')) { unsafe(paragraph); continue; }
      for (const item of childElements(child)) {
        if (isW(item, 'rPr')) continue;
        if (isW(item, 'fldChar')) {
          const type = item.getAttributeNS(NS.w, 'fldCharType');
          if (type === 'begin') fields++;
          else if (type === 'end') fields = Math.max(0, fields - 1);
          unsafe(paragraph);
          continue;
        }
        if (fields || comments) { unsafe(paragraph); continue; }
        if (isW(item, 't')) {
          for (let offset = 0; offset < item.textContent.length; offset++)
            push(item.textContent[offset], {kind: 'text', node: item, offset, run: child});
        } else if (isW(item, 'tab')) {
          push('\t', {kind: 'element', node: item, run: child});
        } else if (isW(item, 'br') || isW(item, 'cr')) {
          push('\v', {kind: 'element', node: item, run: child});
        } else {
          unsafe(paragraph);
        }
      }
    }
  }
  return {text, atoms, selectionStart, selectionEnd};
}

// Applying candidates ----------------------------------------------------------------

const paragraphOf = node => {
  let current = node;
  while (current && !isW(current, 'p')) current = current.parentNode;
  return current;
};

/** Splits the run so that a new top-level run starts at `atom`; returns it. */
function splitBefore(atom) {
  const run = atom.node.parentNode;
  const items = childElements(run).filter(child => !isW(child, 'rPr'));
  const position = items.indexOf(atom.node);
  if (position === 0 && (atom.kind !== 'text' || atom.offset === 0)) return run;
  const clone = run.cloneNode(false);
  const properties = childElements(run).find(child => isW(child, 'rPr'));
  if (properties) clone.appendChild(properties.cloneNode(true));
  if (atom.kind === 'text' && atom.offset > 0) {
    const tail = atom.node.cloneNode(false);
    const value = atom.node.textContent;
    tail.textContent = value.slice(atom.offset);
    atom.node.textContent = value.slice(0, atom.offset);
    for (const node of [tail, atom.node]) node.setAttribute('xml:space', 'preserve');
    clone.appendChild(tail);
    for (const item of items.slice(position + 1)) clone.appendChild(item);
  } else {
    for (const item of items.slice(position)) clone.appendChild(item);
  }
  run.parentNode.insertBefore(clone, run.nextSibling);
  return clone;
}

/** The top-level node right after `atom`, splitting its run if needed (null = paragraph end). */
function boundaryAfter(atom) {
  const run = atom.node.parentNode;
  const items = childElements(run).filter(child => !isW(child, 'rPr'));
  const last = items[items.length - 1] === atom.node
    && (atom.kind !== 'text' || atom.offset === atom.node.textContent.length - 1);
  if (last) return run.nextSibling;
  const next = atom.kind === 'text' && atom.offset < atom.node.textContent.length - 1
    ? {kind: 'text', node: atom.node, offset: atom.offset + 1}
    : {kind: 'element', node: items[items.indexOf(atom.node) + 1]};
  return splitBefore(next);
}

const isContentNode = node => node.nodeType === 1 && !isW(node, 'pPr')
  && !(node.namespaceURI === NS.w && ZERO_WIDTH.has(node.localName));

function visibleText(nodes) {
  return nodes.some(node => isContentNode(node) && !(isW(node, 'r') && childElements(node)
    .every(item => isW(item, 'rPr') || (isW(item, 't') && !dotnetTrim(item.textContent)))));
}

/** Moves bookmarks out of nodes that are replaced; drops everything else. */
function removeKeepingMarkup(nodes, before, after) {
  for (const node of nodes) {
    const markup = node.nodeType === 1 && !isContentNode(node);
    if (markup && !isW(node, 'proofErr')) (isW(node, 'bookmarkStart') ? before : after).push(node);
    node.parentNode?.removeChild(node);
  }
}

function replaceInline(start, endAtom, sdtXml) {
  const after = boundaryAfter(endAtom);
  const first = splitBefore(start);
  const paragraph = paragraphOf(first);
  const nodes = [];
  for (let node = first; node && node !== after; node = node.nextSibling) nodes.push(node);
  const [sdt] = importNodes(paragraph.ownerDocument, sdtXml);
  paragraph.insertBefore(sdt, after);
  const starts = [];
  const ends = [];
  removeKeepingMarkup(nodes, starts, ends);
  for (const node of starts) paragraph.insertBefore(node, sdt);
  for (const node of ends) paragraph.insertBefore(node, sdt.nextSibling);
}

/**
 * Replaces a display candidate, which may span paragraphs. Visible text before
 * and after it stays in paragraphs of its own (PrepareParsedFormulaTarget);
 * whitespace-only remainders are replaced together with the formula.
 */
function replaceDisplay(start, endAtom, paragraphXml) {
  const after = boundaryAfter(endAtom);
  const endParagraph = paragraphOf(endAtom.node);
  const first = splitBefore(start);
  const startParagraph = paragraphOf(first);
  const children = paragraph => [...paragraph.childNodes].filter(child => !isW(child, 'pPr'));
  const leading = children(startParagraph).slice(0, children(startParagraph).indexOf(first));
  const endChildren = children(endParagraph);
  const trailing = after ? endChildren.slice(endChildren.indexOf(after)) : [];
  const [replacement] = importNodes(startParagraph.ownerDocument, paragraphXml);
  const between = [];
  for (let paragraph = startParagraph; ; paragraph = paragraph.nextSibling) {
    if (!isW(paragraph, 'p')) continue;
    for (const node of children(paragraph)) if (!leading.includes(node) && !trailing.includes(node)) between.push(node);
    if (paragraph === endParagraph) break;
  }
  const starts = [];
  const ends = [];
  removeKeepingMarkup(between, starts, ends);
  const content = childElements(replacement).find(child => !isW(child, 'pPr')) || null;
  for (const node of starts) replacement.insertBefore(node, content);
  for (const node of ends) replacement.appendChild(node);
  // Merge the end paragraph's remainder into the start paragraph, then isolate.
  for (const node of trailing) startParagraph.appendChild(node);
  const endProperties = childElements(endParagraph).find(child => isW(child, 'pPr'));
  if (endParagraph !== startParagraph) {
    const startProperties = childElements(startParagraph).find(child => isW(child, 'pPr'));
    const section = endProperties && childElements(endProperties).find(child => isW(child, 'sectPr'));
    if (section) (startProperties || startParagraph.insertBefore(endProperties.cloneNode(false), startParagraph.firstChild))
      .appendChild(section);
    for (let paragraph = startParagraph.nextSibling; paragraph;) {
      const next = paragraph.nextSibling;
      const last = paragraph === endParagraph;
      if (isW(paragraph, 'p')) paragraph.parentNode.removeChild(paragraph);
      if (last) break;
      paragraph = next;
    }
  }
  const keepLeading = visibleText(leading);
  const keepTrailing = visibleText(trailing);
  if (!keepLeading) for (const node of leading) if (isContentNode(node)) startParagraph.removeChild(node);
  if (!keepTrailing) for (const node of trailing) if (isContentNode(node)) startParagraph.removeChild(node);
  const anchor = trailing.find(node => node.parentNode === startParagraph) || null;
  isolateParagraph(startParagraph, anchor, replacement);
}

/**
 * Finds delimited LaTeX in a group of paragraphs. With selection markers
 * (temporary bookmarks at the selection's ends) only text between them is
 * read, so only formulas entirely inside the selection are found.
 */
export function findCandidates(packageXml, markers = {}) {
  const document = parseXml(packageXml);
  const body = packageBody(document);
  const paragraphs = childElements(body).filter(child => isW(child, 'p'));
  const {text, atoms, selectionStart, selectionEnd} = paragraphText(paragraphs, styleNames(document), markers);
  const from = selectionStart ?? 0;
  const to = selectionEnd ?? text.length;
  const sizes = fontSizes(document);
  return scanLatex(text.slice(from, Math.max(from, to))).map(match => {
    const start = from + match.offset;
    const covered = atoms.slice(start, start + match.length);
    return {...match, offset: start, fontSizePoints: uniformSize(covered, sizes)};
  });
}

/**
 * Replaces every candidate that has `xml` ({sdt} for inline, {paragraph} for
 * display formulas) and removes the selection markers. Candidates come from
 * findCandidates on the same package and are applied last to first.
 */
export function applyCandidates(packageXml, candidates, markers = {}) {
  const document = parseXml(packageXml);
  const body = packageBody(document);
  const paragraphs = childElements(body).filter(child => isW(child, 'p'));
  const {atoms} = paragraphText(paragraphs, styleNames(document), markers);
  for (const candidate of [...candidates].sort((a, b) => b.offset - a.offset)) {
    if (!candidate.xml) continue;
    const start = atoms[candidate.offset];
    const end = atoms[candidate.offset + candidate.length - 1];
    if (candidate.display) replaceDisplay(start, end, candidate.xml.paragraph);
    else replaceInline(start, end, candidate.xml.sdt);
  }
  for (const marker of elements(body, NS.w, 'bookmarkStart')) {
    const name = marker.getAttributeNS(NS.w, 'name');
    if (name !== markers.start && name !== markers.end) continue;
    const id = marker.getAttributeNS(NS.w, 'id');
    for (const end of elements(body, NS.w, 'bookmarkEnd'))
      if (end.getAttributeNS(NS.w, 'id') === id) end.parentNode.removeChild(end);
    marker.parentNode.removeChild(marker);
  }
  return serializeXml(document);
}

// Font size -------------------------------------------------------------------------

function fontSizes(document) {
  const styles = new Map();
  for (const style of elements(document, NS.w, 'style')) styles.set(style.getAttributeNS(NS.w, 'styleId'), style);
  const sizeOf = properties => {
    const size = properties && childElements(properties).find(child => isW(child, 'sz'));
    return size ? Number(size.getAttributeNS(NS.w, 'val')) / 2 : 0;
  };
  const styleSize = (id, seen = new Set()) => {
    const style = styles.get(id);
    if (!style || seen.has(id)) return 0;
    seen.add(id);
    const own = sizeOf(childElements(style).find(child => isW(child, 'rPr')));
    if (own) return own;
    const based = childElements(style).find(child => isW(child, 'basedOn'));
    return based ? styleSize(based.getAttributeNS(NS.w, 'val'), seen) : 0;
  };
  const defaults = elements(document, NS.w, 'rPrDefault')[0];
  const defaultSize = sizeOf(defaults && childElements(defaults).find(child => isW(child, 'rPr'))) || 10;
  return run => {
    const properties = childElements(run).find(child => isW(child, 'rPr'));
    const own = sizeOf(properties);
    if (own) return own;
    const runStyle = properties && childElements(properties).find(child => isW(child, 'rStyle'));
    const fromRunStyle = runStyle ? styleSize(runStyle.getAttributeNS(NS.w, 'val')) : 0;
    if (fromRunStyle) return fromRunStyle;
    const paragraphProperties = childElements(paragraphOf(run)).find(child => isW(child, 'pPr'));
    const paragraphStyle = paragraphProperties && childElements(paragraphProperties).find(child => isW(child, 'pStyle'));
    return styleSize(paragraphStyle ? paragraphStyle.getAttributeNS(NS.w, 'val') : 'Normal') || defaultSize;
  };
}

/** ReadPointSize of the candidate's text: one size, or 0 when mixed. */
function uniformSize(atoms, sizeOfRun) {
  const sizes = new Set(atoms.filter(atom => atom.run).map(atom => sizeOfRun(atom.run)));
  const [size] = sizes;
  return sizes.size === 1 && size >= 1 && size <= 1638 ? size : 0;
}
