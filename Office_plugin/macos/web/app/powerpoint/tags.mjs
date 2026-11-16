// PowerPointFormulaMetadataStore: schema 3 formula metadata in shape tags, so a
// picture formula inserted on either platform loads on the other. PNG pictures
// are exactly the Windows "Image" formulas. SVG pictures are the same tags plus
// the Mac-only LaTeXSnipperImageFormat=Svg, which Windows ignores (it treats
// them as pictures it can re-render).
import {MetadataError, newId, validateTypography} from '../metadata.mjs';

export const SCHEMA_VERSION = 3;
export const TAG = {
  documentId: 'LaTeXSnipperDocumentId',
  equationId: 'LaTeXSnipperEquationId',
  schemaVersion: 'LaTeXSnipperSchemaVersion',
  renderEngine: 'LaTeXSnipperRenderEngine',
  latexPrefix: 'LaTeXSnipperLatex',
  displayMode: 'LaTeXSnipperDisplayMode',
  typographyPrefix: 'LaTeXSnipperTypography',
  naturalWidth: 'LaTeXSnipperNaturalWidthPoints',
  naturalHeight: 'LaTeXSnipperNaturalHeightPoints',
  imageFormat: 'LaTeXSnipperImageFormat',
};
export const DOCUMENT_ID_PROPERTY = 'LaTeXSnipper.DocumentId';
export const ALT_TEXT_PREFIX = 'LaTeXSnipper formula ';
export const FORMATS = ['Png', 'Svg'];
const CHUNK = 200;
const MAX_CHUNKS = 10000;
const missing = () => new MetadataError('无法找到所选公式的元数据。');

export function createFormula({documentId, latex, typography, format, naturalWidthPoints, naturalHeightPoints,
  equationId = newId()}) {
  return validateFormula({schemaVersion: SCHEMA_VERSION, documentId, equationId, latex, displayMode: 'Display',
    renderEngine: 'Image', typography, format, naturalWidthPoints, naturalHeightPoints});
}

function validateFormula(value) {
  if (value.schemaVersion !== SCHEMA_VERSION || !value.documentId || !value.equationId) throw missing();
  if (typeof value.latex !== 'string' || !FORMATS.includes(value.format)) throw missing();
  for (const name of ['naturalWidthPoints', 'naturalHeightPoints'])
    if (!(Number(value[name]) > 0 && Number.isFinite(Number(value[name])))) throw missing();
  let typography;
  try { typography = validateTypography(value.typography); } catch { throw missing(); }
  return {...value, typography, naturalWidthPoints: Number(value.naturalWidthPoints),
    naturalHeightPoints: Number(value.naturalHeightPoints)};
}

function encodeChunks(prefix, text) {
  const bytes = new TextEncoder().encode(text);
  let hex = '';
  for (const byte of bytes) hex += byte.toString(16).toUpperCase().padStart(2, '0');
  const payload = hex || '0';
  const count = Math.ceil(payload.length / CHUNK);
  const tags = [[prefix + 'Bytes', String(bytes.length)], [prefix + 'Chunks', String(count)]];
  for (let index = 0; index < count; index++)
    tags.push([prefix + String(index).padStart(4, '0'), payload.slice(index * CHUNK, (index + 1) * CHUNK)]);
  return tags;
}

function decodeChunks(prefix, read) {
  const length = Number.parseInt(read(prefix + 'Bytes'), 10);
  const count = Number.parseInt(read(prefix + 'Chunks'), 10);
  if (!(length >= 0) || !(count > 0) || count > MAX_CHUNKS) throw missing();
  let hex = '';
  for (let index = 0; index < count; index++) {
    const chunk = read(prefix + String(index).padStart(4, '0'));
    if (!chunk.trim()) throw missing();
    hex += chunk;
  }
  if (length === 0) return '';
  if (hex.length !== length * 2 || !/^[0-9A-Fa-f]*$/.test(hex)) throw missing();
  const bytes = new Uint8Array(length);
  for (let index = 0; index < length; index++) bytes[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  try { return new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch { throw missing(); }
}

/** Tag pairs in the order Windows writes them (the temp-file path tag has no Mac equivalent). */
export function formulaTags(formula) {
  return [
    [TAG.documentId, formula.documentId],
    [TAG.equationId, formula.equationId],
    [TAG.schemaVersion, String(SCHEMA_VERSION)],
    [TAG.renderEngine, 'Image'],
    ...encodeChunks(TAG.latexPrefix, formula.latex),
    [TAG.displayMode, 'Display'],
    ...encodeChunks(TAG.typographyPrefix, JSON.stringify(formula.typography)),
    // Windows writes these as single-precision floats.
    [TAG.naturalWidth, String(Math.fround(formula.naturalWidthPoints).toPrecision(7) * 1)],
    [TAG.naturalHeight, String(Math.fround(formula.naturalHeightPoints).toPrecision(7) * 1)],
    [TAG.imageFormat, formula.format],
  ];
}

const tagReader = entries => {
  const values = new Map(entries.map(([key, value]) => [String(key).toUpperCase(), String(value ?? '')]));
  return name => values.get(name.toUpperCase());
};

/** Reads tags case-insensitively: PowerPoint stores tag names in upper case. */
export function formulaFromTags(entries) {
  const get = tagReader(entries);
  const read = name => {
    const value = get(name);
    if (value === undefined) throw missing();
    return value;
  };
  if (String(read(TAG.displayMode)).toLowerCase() !== 'display') throw missing();
  if (String(read(TAG.renderEngine)).toLowerCase() !== 'image') throw missing();
  let typography;
  try { typography = JSON.parse(decodeChunks(TAG.typographyPrefix, read)); } catch { throw missing(); }
  return validateFormula({
    schemaVersion: Number.parseInt(read(TAG.schemaVersion), 10),
    documentId: read(TAG.documentId),
    equationId: read(TAG.equationId),
    latex: decodeChunks(TAG.latexPrefix, read),
    displayMode: 'Display',
    renderEngine: 'Image',
    typography,
    format: get(TAG.imageFormat) === 'Svg' ? 'Svg' : 'Png',
    naturalWidthPoints: read(TAG.naturalWidth),
    naturalHeightPoints: read(TAG.naturalHeight),
  });
}

/** IsManagedFormula: any shape with a non-blank equation id tag. */
export const isFormulaTagSet = entries => Boolean(tagReader(entries)(TAG.equationId)?.trim());

/** Windows OLE formulas carry the same tags with RenderEngine MathJaxSvg; Mac never edits them. */
export const isOleFormulaTagSet = entries =>
  isFormulaTagSet(entries) && String(tagReader(entries)(TAG.renderEngine)).toLowerCase() === 'mathjaxsvg';
