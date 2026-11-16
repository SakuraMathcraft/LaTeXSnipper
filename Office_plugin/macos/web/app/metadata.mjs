// Formula typography (FormulaTypographyFields, typography version 1), shared by
// the Word and PowerPoint contracts.
export const TYPOGRAPHY_VERSION = 1;
const MATH_STYLES = ['Automatic', 'Upright', 'Bold', 'Italic', 'BoldItalic', 'SansSerif', 'SansSerifBold',
  'SansSerifItalic', 'SansSerifBoldItalic', 'Monospace', 'Calligraphic', 'BoldCalligraphic', 'Script',
  'BoldScript', 'Fraktur', 'BoldFraktur', 'Blackboard'];

export const DEFAULT_LATEX = 'e^{i\\pi}+1=0';

export class MetadataError extends Error {}

/** MathLiveLatexStyleNormalizer for new and edited formulas; an empty source becomes the default formula. */
export function normalizeLatex(latex) {
  const trimmed = String(latex ?? '').trim();
  return trimmed ? trimmed.replace(/\\bm(?=\s*\{)/g, '\\boldsymbol') : DEFAULT_LATEX;
}

/** Guid.NewGuid().ToString("N"). */
export function newId() {
  return crypto.randomUUID().replaceAll('-', '');
}

export function validateTypography(fields) {
  const fail = message => { throw new MetadataError(message); };
  if (!fields || typeof fields !== 'object') fail('缺少公式样式。');
  for (const name of ['typographyVersion', 'symbolFontId', 'numberFontFamily', 'cjkFontFamily',
    'defaultMathStyle', 'fontSizePoints', 'color'])
    if (fields[name] === undefined || fields[name] === null) fail('缺少公式样式字段：' + name);
  if (String(fields.typographyVersion) !== String(TYPOGRAPHY_VERSION)) fail('不支持的公式样式版本。');
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(fields.symbolFontId)) fail('数学字体必须使用稳定的字体方案 ID。');
  if (!MATH_STYLES.includes(fields.defaultMathStyle)) fail('无效的数学样式。');
  const points = Number(fields.fontSizePoints);
  if (!(points >= 1 && points <= 1638)) fail('公式字号必须在 1–1638 pt 之间。');
  if (!/^#[0-9a-fA-F]{6}$/.test(fields.color)) fail('颜色必须为 #RRGGBB 格式。');
  if (!String(fields.cjkFontFamily).trim()) fail('字体家族不能为空。');
  return {
    typographyVersion: TYPOGRAPHY_VERSION,
    symbolFontId: fields.symbolFontId,
    numberFontFamily: String(fields.numberFontFamily || '').trim(),
    cjkFontFamily: String(fields.cjkFontFamily).trim(),
    defaultMathStyle: fields.defaultMathStyle,
    fontSizePoints: points,
    color: fields.color.toUpperCase(),
  };
}

/** FormulaTypography.Equals: font families compare case-insensitively. */
export function sameTypography(a, b) {
  const family = value => String(value || '').toLowerCase();
  return a.symbolFontId === b.symbolFontId && family(a.numberFontFamily) === family(b.numberFontFamily)
    && family(a.cjkFontFamily) === family(b.cjkFontFamily) && a.defaultMathStyle === b.defaultMathStyle
    && Number(a.fontSizePoints) === Number(b.fontSizePoints) && a.color === b.color;
}
