// MathJax SVG renderer with LaTeXSnipper typography, shared by the task pane
// runtime and the editor dialog. It loads the same MathJax profile and
// MathJaxTypographyAdapter.js as the Windows WebView2 host; only system-font
// glyph outlines come from the add-in host (CoreText) instead of GDI+.
import {api} from './api.mjs';

const MATHJAX_ROOT = new URL('/mathjax', location.origin).href;
const ADAPTER = '/renderer/typography-adapter.js';
const STARTUP_TIMEOUT_MS = 15000;
const CACHE_LIMIT = 128;
let startup = null;
const cache = new Map();

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.onload = resolve;
    script.onerror = () => reject(new Error('无法加载公式渲染资源：' + src));
    document.head.appendChild(script);
  });
}

async function waitForMathJax() {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const runtime = globalThis.LaTeXSnipperMathJax;
    if (runtime?.ready) return;
    if (runtime?.error) throw new Error('MathJax startup failed: ' + runtime.error);
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  throw new Error('MathJax 启动超时。');
}

export function startRenderer() {
  startup ||= (async () => {
    await loadScript(`${MATHJAX_ROOT}/config.js`);
    await loadScript(`${MATHJAX_ROOT}/runtime.js`);
    await loadScript(`${MATHJAX_ROOT}/office.js`);
    globalThis.LaTeXSnipperMathJax.configure({root: MATHJAX_ROOT, output: 'svg', typeset: false});
    await loadScript(`${MATHJAX_ROOT}/startup.js`);
    await waitForMathJax();
    // MathJax 4 splits inline math into sibling SVGs by default; Office needs one image.
    MathJax.startup.document.outputJax.options.linebreaks.inline = false;
    await loadScript(ADAPTER);
    if (!globalThis.LaTeXSnipperOfficeTypography) throw new Error('字体适配器加载失败。');
  })().catch(error => { startup = null; throw error; });
  return startup;
}

function adapterLatex(latex) {
  return String(latex || '').trim().replace(/\\bm(?=\s*\{)/g, '\\boldsymbol');
}

function adapterInput(latex, display, typography) {
  return {
    latex: adapterLatex(latex),
    displayMode: display ? 'Display' : 'Inline',
    typography: {
      SymbolFontId: typography.symbolFontId,
      NumberFontFamily: typography.numberFontFamily || null,
      CjkFontFamily: typography.cjkFontFamily,
      DefaultMathStyle: typography.defaultMathStyle,
      FontSizePoints: Number(typography.fontSizePoints),
      Color: String(typography.color || '#000000').toUpperCase(),
      TypographyVersion: Number(typography.typographyVersion || 1),
    },
  };
}

/** Semantic MathML with the formula's default style cascade, for Word OMML. */
export async function renderMathMl(latex, display, typography) {
  await startRenderer();
  const plan = await LaTeXSnipperOfficeTypography.prepare(adapterInput(latex, display, typography));
  return plan.mathml;
}

/** Natural-size SVG: {svg, widthPoints, heightPoints, baselinePoints, warnings}. */
export async function renderSvg(latex, display, typography) {
  await startRenderer();
  const input = adapterInput(latex, display, typography);
  const plan = await LaTeXSnipperOfficeTypography.prepare(input);
  const warnings = new Set(plan.warnings || []);
  let outlines = {};
  if (plan.runs.length) {
    const response = await api('/api/font-outlines', {
      method: 'POST',
      body: {runs: plan.runs.map(({key, text, family, style}) => ({key, text, family, style}))},
    });
    outlines = response.outlines;
    for (const run of Object.values(outlines)) if (run.Warning) warnings.add(run.Warning);
  }
  // Like the Windows cache, identity includes the measured fonts, so a font
  // change can never reuse stale geometry.
  const key = JSON.stringify([MathJax.version, input, outlines]);
  if (cache.has(key)) return cache.get(key);
  const result = await LaTeXSnipperOfficeTypography.render(input, outlines);
  for (const warning of result.warnings || []) warnings.add(warning);
  const rendered = {
    svg: officeSvg(result.svg, input.typography.Color, result.widthPoints, result.heightPoints),
    widthPoints: result.widthPoints,
    heightPoints: result.heightPoints,
    baselinePoints: result.baselinePoints,
    warnings: [...warnings],
  };
  if (!(rendered.widthPoints > 0) || !(rendered.heightPoints > 0) || !Number.isFinite(rendered.baselinePoints))
    throw new Error('字体渲染返回了无效的自然尺寸。');
  if (cache.size >= CACHE_LIMIT) cache.clear();
  cache.set(key, rendered);
  return rendered;
}

/**
 * Makes MathJax SVG self-contained for Office: Office's SVG renderer has no
 * CSS context, so `currentColor` would paint nothing, and it ignores CSS
 * sizing. Local \\textcolor fills are explicit and stay untouched.
 */
export function officeSvg(svg, color, widthPoints, heightPoints) {
  const document = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const root = document.documentElement;
  if (root.nodeName !== 'svg' || document.querySelector('parsererror')) throw new Error('公式 SVG 无效。');
  for (const element of [root, ...root.querySelectorAll('*')]) {
    for (const name of ['fill', 'stroke', 'color'])
      if (element.getAttribute(name) === 'currentColor') element.setAttribute(name, color);
  }
  root.removeAttribute('style');
  root.removeAttribute('role');
  root.removeAttribute('focusable');
  // 1pt = 4/3 CSS px; the picture extent in the document carries the exact size.
  root.setAttribute('width', String(+(widthPoints * 4 / 3).toFixed(3)));
  root.setAttribute('height', String(+(heightPoints * 4 / 3).toFixed(3)));
  return new XMLSerializer().serializeToString(root);
}

export function svgDataUrl(svg) {
  return 'data:image/svg+xml;base64,' + base64Utf8(svg);
}

export function base64Utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(binary);
}

// SvgPngRasterizer and PowerPointImageFileStore: 300 DPI, 1.5 pt / 0.5 pt
// padding, and pictures wider than 420 pt shown at 420 pt.
const PICTURE_DPI = 300;
const PADDING_X_POINTS = 1.5;
const PADDING_Y_POINTS = 0.5;
const MAX_PICTURE_WIDTH_POINTS = 420;
const pixels = points => Math.ceil(points / 72 * PICTURE_DPI);

/** The picture's natural size in points, the size Format restores. */
export function pictureSize(rendered) {
  const width = rendered.widthPoints + 2 * PADDING_X_POINTS;
  const height = rendered.heightPoints + 2 * PADDING_Y_POINTS;
  const scale = width > MAX_PICTURE_WIDTH_POINTS ? MAX_PICTURE_WIDTH_POINTS / width : 1;
  return {widthPoints: width * scale, heightPoints: height * scale};
}

/** A transparent 300 DPI PNG (base64) of the rendered formula, padded like Windows. */
export async function rasterizePicture(rendered) {
  const image = new Image();
  const loaded = new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error('公式图片生成失败。'));
  });
  image.src = svgDataUrl(rendered.svg);
  await loaded;
  const paddingX = pixels(PADDING_X_POINTS);
  const paddingY = pixels(PADDING_Y_POINTS);
  const width = Math.max(1, pixels(rendered.widthPoints));
  const height = Math.max(1, pixels(rendered.heightPoints));
  const canvas = document.createElement('canvas');
  canvas.width = width + 2 * paddingX;
  canvas.height = height + 2 * paddingY;
  canvas.getContext('2d').drawImage(image, paddingX, paddingY, width, height);
  return canvas.toDataURL('image/png').slice('data:image/png;base64,'.length);
}

/** The rendered SVG with the same padding as the PNG, so both formats share one natural size. */
export function paddedSvg(rendered) {
  const document = new DOMParser().parseFromString(rendered.svg, 'image/svg+xml');
  const root = document.documentElement;
  const [x, y, width, height] = String(root.getAttribute('viewBox')).trim().split(/[\s,]+/).map(Number);
  const unitsX = width / rendered.widthPoints * PADDING_X_POINTS;
  const unitsY = height / rendered.heightPoints * PADDING_Y_POINTS;
  root.setAttribute('viewBox', [x - unitsX, y - unitsY, width + 2 * unitsX, height + 2 * unitsY].join(' '));
  const size = {widthPoints: rendered.widthPoints + 2 * PADDING_X_POINTS, heightPoints: rendered.heightPoints + 2 * PADDING_Y_POINTS};
  root.setAttribute('width', String(+(size.widthPoints * 4 / 3).toFixed(3)));
  root.setAttribute('height', String(+(size.heightPoints * 4 / 3).toFixed(3)));
  return new XMLSerializer().serializeToString(root);
}
