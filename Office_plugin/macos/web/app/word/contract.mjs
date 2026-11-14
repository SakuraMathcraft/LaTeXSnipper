// The Windows Word document contract (WordFormulaMetadataStore,
// WordDocumentIdentityStore, WordEquationNumbering). Formulas written on either
// platform must load, edit and renumber on the other, so every name and format
// here is fixed by the Windows add-in.
import {MetadataError, newId, normalizeLatex, validateTypography} from '../metadata.mjs';

export const EQUATION_TITLE = 'LaTeXSnipper Equation';
export const TAG_PREFIX = 'latexsnipper-eq-';
export const DOCUMENT_ID_VARIABLE = 'LaTeXSnipper.DocumentId';
export const BOUNDARY_TITLE = 'LaTeXSnipper Numbering Boundary';
export const BOUNDARY_TAGS = {
  chapter: 'latexsnipper-number-boundary-chapter',
  section: 'latexsnipper-number-boundary-section',
};
export const SEQUENCE_NAME = 'LaTeXSnipperEquation';
export const SEQUENCE_MARKER = 'SEQ ' + SEQUENCE_NAME;
export const BOOKMARK_PREFIX = 'LaTeXSnipperEq_';
export const REFERENCE_MARKER = 'REF ' + BOOKMARK_PREFIX;
const MAX_TAG_LENGTH = 64;
// Word stores at most 40 characters of a bookmark name. The Windows add-in asks
// for LaTeXSnipperEq_<32 hex>, and Word keeps the first 40; REF fields keep the
// full name and still resolve, so both forms are written exactly like Windows.
const MAX_BOOKMARK_LENGTH = 40;
const VARIABLE_PREFIX = 'LS.E.';
const SCHEMA_VERSION = 3;
const DISPLAY_MODES = ['Inline', 'Display'];
const NUMBERING_MODES = ['None', 'Automatic', 'Manual'];
const OLE_PROG_IDS = new Set(['latexsnipper.formula', 'latexsnipper.formula.1']);

export class FormulaMetadataMissing extends MetadataError {}

export function equationIdFromTag(tag) {
  if (typeof tag !== 'string' || !tag.startsWith(TAG_PREFIX)) return '';
  const rest = tag.slice(TAG_PREFIX.length);
  const separator = rest.indexOf('|');
  return (separator < 0 ? rest : rest.slice(0, separator)).trim();
}

export function revisionFromTag(tag) {
  const separator = typeof tag === 'string' ? tag.indexOf('|') : -1;
  return separator < 0 ? '' : tag.slice(separator + 1);
}

export function buildTag(equationId, revision = '') {
  const tag = TAG_PREFIX + equationId + (revision ? '|' + revision : '');
  if (tag.length > MAX_TAG_LENGTH) throw new MetadataError('Word 公式标记超过 64 个字符的限制。');
  return tag;
}

export const isBoundaryTag = tag => tag === BOUNDARY_TAGS.chapter || tag === BOUNDARY_TAGS.section;
export const isOleFormulaProgId = progId => OLE_PROG_IDS.has(String(progId || '').toLowerCase());
export const newRevision = () => newId().slice(0, 10);
export const variableName = (equationId, revision) => VARIABLE_PREFIX + equationId + '.' + revision;
export const bookmarkName = equationId => (BOOKMARK_PREFIX + equationId).slice(0, MAX_BOOKMARK_LENGTH);
export const referenceCode = equationId => ` REF ${BOOKMARK_PREFIX}${equationId} \\h `;

export function createFormula({documentId, latex, display, numberingMode = 'None', numberText = '', typography,
  equationId = newId()}) {
  const manual = numberingMode === 'Manual' ? String(numberText).trim() : '';
  const mode = numberingMode === 'Manual' && !manual ? 'None' : numberingMode;
  return validateFormula({
    schemaVersion: SCHEMA_VERSION,
    documentId,
    equationId,
    latex: normalizeLatex(latex),
    displayMode: display || mode !== 'None' ? 'Display' : 'Inline',
    numberingMode: mode,
    numberText: mode === 'Manual' ? manual : '',
    renderEngine: 'Omml',
    typography,
  });
}

function validateFormula(value) {
  const missing = () => { throw new FormulaMetadataMissing('无法找到所选公式的元数据。'); };
  if (!value || typeof value !== 'object') missing();
  if (Number.parseInt(String(value.schemaVersion), 10) !== SCHEMA_VERSION) missing();
  if (!String(value.documentId || '').trim() || !String(value.equationId || '').trim()) missing();
  if (typeof value.latex !== 'string' || typeof value.numberText !== 'string') missing();
  const displayMode = canonical(DISPLAY_MODES, value.displayMode) ?? missing();
  const numberingMode = canonical(NUMBERING_MODES, value.numberingMode) ?? missing();
  if (String(value.renderEngine).toLowerCase() !== 'omml') missing();
  let typography;
  try { typography = validateTypography(value.typography); } catch { missing(); }
  return {schemaVersion: SCHEMA_VERSION, documentId: value.documentId, equationId: value.equationId,
    latex: value.latex, displayMode, numberingMode, numberText: value.numberText, renderEngine: 'Omml', typography};
}

const canonical = (names, value) => names.find(name => name.toLowerCase() === String(value).toLowerCase());

/** The LS.E.<id>.<revision> variable value, with the key order Windows writes. */
export function serializeFormula(formula) {
  const {typography: t} = formula;
  return JSON.stringify({
    schemaVersion: SCHEMA_VERSION,
    documentId: formula.documentId,
    equationId: formula.equationId,
    latex: formula.latex,
    displayMode: formula.displayMode,
    numberingMode: formula.numberingMode,
    numberText: formula.numberText,
    renderEngine: 'Omml',
    typography: {
      typographyVersion: 1,
      symbolFontId: t.symbolFontId,
      numberFontFamily: t.numberFontFamily || '',
      cjkFontFamily: t.cjkFontFamily,
      defaultMathStyle: t.defaultMathStyle,
      fontSizePoints: t.fontSizePoints,
      color: t.color,
    },
  });
}

/** Resolves a content-control tag through the document variables, like WordFormulaMetadataStore.Load. */
export function loadFormula(tag, variables) {
  const equationId = equationIdFromTag(tag);
  const revision = revisionFromTag(tag);
  const raw = equationId && revision ? variables.get(variableName(equationId, revision)) : undefined;
  if (raw === undefined) throw new FormulaMetadataMissing('无法找到所选公式的元数据。');
  let parsed;
  try { parsed = JSON.parse(raw); } catch { throw new FormulaMetadataMissing('无法找到所选公式的元数据。'); }
  const formula = validateFormula(parsed);
  if (formula.equationId !== equationId) throw new FormulaMetadataMissing('无法找到所选公式的元数据。');
  return formula;
}

// Numbering ----------------------------------------------------------------------

const ENCLOSURES = {Parentheses: ['(', ')'], SquareBrackets: ['[', ']'], Braces: ['{', '}'], None: ['', '']};
export const enclosureOf = name => ENCLOSURES[name] ?? ENCLOSURES.Parentheses;

export function numberPrefix(settings, chapter, section) {
  const parts = [];
  if (settings.includeChapter) parts.push(String(chapter));
  if (settings.includeSection) parts.push(String(section));
  return parts.length ? parts.join(settings.numberSeparator) + settings.numberSeparator : '';
}

const quotePicture = value => value ? "'" + value.replaceAll("'", "''") + "'" : '';

export function sequenceCode({reset, prefix, enclosure}) {
  const [left, right] = enclosureOf(enclosure);
  const before = left + prefix;
  const picture = before || right ? quotePicture(before) + '0' + quotePicture(right) : '';
  return ' ' + SEQUENCE_MARKER + (reset ? ' \\r 1' : '') + (picture ? ` \\# "${picture}"` : '') + ' ';
}

/** The text Word shows for an automatic number, before Word updates the field. */
export function sequenceResult({prefix, enclosure}, value) {
  const [left, right] = enclosureOf(enclosure);
  return left + prefix + value + right;
}

export function manualNumberText(numberText, enclosure) {
  const [left, right] = enclosureOf(enclosure);
  return left + numberText + right;
}

/**
 * BuildEquationNumberStates: walks formulas and numbering boundaries in
 * document order. A chapter boundary starts the next chapter and resets the
 * section; any boundary restarts the count, even when prefixes are off.
 * Returns the state of every item of kind "formula", keyed by its position.
 */
export function numberStates(timeline, settings) {
  let chapter = 1;
  let section = 1;
  let resetNext = true;
  let value = 0;
  const states = new Map();
  for (const [index, item] of timeline.entries()) {
    if (item.kind === 'chapter') { chapter++; section = 1; resetNext = true; continue; }
    if (item.kind === 'section') { section++; resetNext = true; continue; }
    value = resetNext ? 1 : value + 1;
    states.set(index, {prefix: numberPrefix(settings, chapter, section), reset: resetNext,
      enclosure: settings.numberEnclosure, value});
    resetNext = false;
  }
  return states;
}

/** BuildEquationNumberStateAtPosition: the state a new automatic formula gets after `before`. */
export function numberStateAfter(before, settings) {
  const states = numberStates([...before, {kind: 'formula'}], settings);
  return states.get(before.length);
}
