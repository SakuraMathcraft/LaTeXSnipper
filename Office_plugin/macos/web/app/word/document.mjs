// Office.js access to a Word document for the Windows formula contract.
/* global Word */
import {api} from '../api.mjs';
import {newId} from '../metadata.mjs';
import {
  BOUNDARY_TAGS, DOCUMENT_ID_VARIABLE, EQUATION_TITLE, FormulaMetadataMissing, SEQUENCE_MARKER, buildTag,
  equationIdFromTag, isBoundaryTag, isOleFormulaProgId, loadFormula, newRevision, serializeFormula, variableName,
} from './contract.mjs';
import {cellTextWidthPoints, readVariables, sectionTextWidthPoints} from './ooxml.mjs';

export class WordCommandError extends Error {}

/**
 * The document's variables for one command. Reads come from the document's
 * OOXML; writes are collected and sent to the add-in host in one AppleScript
 * call, addressed to this document by a temporary hidden bookmark.
 */
export class Variables {
  static async load(context) {
    // Any range's package carries settings.xml; a collapsed range has no OOXML on Mac.
    const ooxml = context.document.body.paragraphs.getFirst().getOoxml();
    await context.sync();
    return new Variables(readVariables(ooxml.value));
  }

  constructor(values) {
    this.values = values;
    this.pending = new Map();
  }

  documentId() {
    let id = this.values.get(DOCUMENT_ID_VARIABLE);
    if (!id) {
      id = newId();
      this.set(DOCUMENT_ID_VARIABLE, id);
    }
    return id;
  }

  set(name, value) {
    this.values.set(name, value);
    this.pending.set(name, value);
  }

  /** Stores a new revision of the formula's metadata and returns its tag. */
  save(formula) {
    if (formula.documentId !== this.documentId()) throw new FormulaMetadataMissing('无法找到所选公式的元数据。');
    const revision = newRevision();
    this.set(variableName(formula.equationId, revision), serializeFormula(formula));
    return buildTag(formula.equationId, revision);
  }

  load(tag) {
    return loadFormula(tag, this.values);
  }

  async flush(context) {
    if (!this.pending.size) return;
    const marker = '_LSLink' + newId().slice(0, 24);
    context.document.body.getRange('Start').insertBookmark(marker);
    await context.sync();
    try {
      await api('/api/word/variables', {method: 'POST', body: {marker, values: Object.fromEntries(this.pending)}});
      this.pending.clear();
    } finally {
      context.document.deleteBookmark(marker);
      await context.sync();
    }
  }
}

// Content controls -----------------------------------------------------------------

async function loaded(context, controls) {
  controls.load('items/id,items/tag,items/title');
  await context.sync();
  return controls.items;
}

/** Managed formulas and numbering boundaries of the body, in document order. */
export async function bodyControls(context) {
  return loaded(context, context.document.body.contentControls);
}

export const isFormulaControl = control => Boolean(equationIdFromTag(control.tag));
export const isBoundaryControl = control => isBoundaryTag(control.tag);
export const boundaryKind = control => control.tag === BOUNDARY_TAGS.chapter ? 'chapter' : 'section';

/** CollectSelectedFormulas: the selection's own managed control first, then those inside it. */
export async function selectedFormulaControls(context) {
  const selection = context.document.getSelection();
  const parent = selection.parentContentControlOrNullObject;
  parent.load('id,tag,title');
  const inside = selection.contentControls;
  inside.load('items/id,items/tag,items/title');
  await context.sync();
  const controls = [];
  const seen = new Set();
  for (const control of [...(parent.isNullObject ? [] : [parent]), ...inside.items]) {
    const id = equationIdFromTag(control.tag);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    controls.push(control);
  }
  return controls;
}

/**
 * LaTeXSnipper OLE formulas (Windows only) in a range. They are found by their
 * ProgID in the range's OOXML, or by the formula tag the Windows add-in puts
 * in their alternative text: when the object alone is selected, Word for Mac
 * exports it as a plain picture without the ProgID. Mac never inserts Word
 * picture formulas, so a tagged inline picture is always a Windows OLE formula.
 */
export async function oleFormulaCount(context, range) {
  range.load('isEmpty');
  const pictures = range.inlinePictures;
  pictures.load('items/altTextDescription');
  await context.sync();
  const tagged = pictures.items.filter(picture => equationIdFromTag(picture.altTextDescription)).length;
  // A collapsed range (a caret) has no OOXML on Word for Mac.
  if (range.isEmpty) return tagged;
  const ooxml = range.getOoxml();
  await context.sync();
  const progIds = [...ooxml.value.matchAll(/<o:OLEObject\b[^>]*\bProgID="([^"]+)"/g)].map(match => match[1]);
  return Math.max(tagged, progIds.filter(isOleFormulaProgId).length);
}

export async function countFormulasWithId(context, equationId) {
  return (await bodyControls(context)).filter(control => equationIdFromTag(control.tag) === equationId).length;
}

/** Applies a saved tag and the Windows chrome to an inserted or updated control. */
export function styleControl(control, tag, fontSizePoints) {
  control.tag = tag;
  control.title = EQUATION_TITLE;
  control.appearance = Word.ContentControlAppearance.boundingBox;
  if (fontSizePoints > 0) control.font.size = fontSizePoints;
}

export async function controlByTag(context, tag) {
  const controls = context.document.contentControls.getByTag(tag);
  return (await loaded(context, controls))[0] || null;
}

// Paragraphs -----------------------------------------------------------------------

/** GetEquationContentWidthPoints for the paragraph's cell or section column. */
export async function textWidthPoints(context, paragraph) {
  const cell = paragraph.parentTableCellOrNullObject;
  cell.load('columnWidth');
  const ooxml = paragraph.getOoxml();
  await context.sync();
  if (cell.isNullObject) return sectionTextWidthPoints(ooxml.value);
  const left = cell.getCellPadding(Word.CellPaddingLocation.left);
  const right = cell.getCellPadding(Word.CellPaddingLocation.right);
  await context.sync();
  return cellTextWidthPoints(cell.columnWidth, left.value, right.value);
}

/**
 * A paragraph's own package, or that of consecutive body paragraphs. A table
 * cell paragraph must use its own methods: its whole range is the table.
 */
const target = (first, last) => last === first ? first : first.getRange('Whole').expandTo(last.getRange('Whole'));

export async function paragraphOoxml(context, first, last = first) {
  const ooxml = target(first, last).getOoxml();
  await context.sync();
  return ooxml.value;
}

/** Replaces the paragraphs by those of `packageXml`, a rewritten copy of their own package. */
export async function replaceParagraphs(context, first, last, packageXml) {
  target(first, last).insertOoxml(packageXml, Word.InsertLocation.replace);
  await context.sync();
}

/** Whether OOXML holds an embedded object (Windows OLE formulas and others), which rewriting could lose. */
export const containsEmbeddedObject = xml => /<w:object\b|<o:OLEObject\b/.test(xml);

// Fields ---------------------------------------------------------------------------

export async function sequenceFields(context, range) {
  const fields = range.fields;
  fields.load('items/code');
  await context.sync();
  return fields.items.filter(field => field.code.includes(SEQUENCE_MARKER));
}

