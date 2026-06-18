import { normalizeLatexInput } from "../latex.js";

const EMPTY_LATEX_MESSAGE = "Enter LaTeX before inserting.";
const MATHJAX_UNAVAILABLE_MESSAGE = "MathJax unavailable; using text fallback";

export function getMathJaxUnavailableMessage() {
  return MATHJAX_UNAVAILABLE_MESSAGE;
}

function escapeAttribute(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function encodeBase64(value, globalScope = globalThis) {
  if (typeof globalScope.btoa === "function") {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return globalScope.btoa(binary);
  }

  if (typeof Buffer !== "undefined") {
    return Buffer.from(value, "utf8").toString("base64");
  }

  throw new Error("Base64 encoding unavailable.");
}

export function encodeSvgDataUri(svg, globalScope = globalThis) {
  return `data:image/svg+xml;base64,${encodeBase64(svg, globalScope)}`;
}

export async function renderLatexToSvg({
  latex,
  mathJax = globalThis.MathJax,
  mode = "inline",
} = {}) {
  const normalizedLatex = normalizeLatexInput(latex);
  if (!normalizedLatex) {
    throw new Error(EMPTY_LATEX_MESSAGE);
  }

  if (!mathJax?.tex2svgPromise) {
    throw new Error(MATHJAX_UNAVAILABLE_MESSAGE);
  }

  await mathJax.startup?.promise;

  const container = await mathJax.tex2svgPromise(normalizedLatex, {
    display: mode !== "inline",
  });
  const svg = container?.querySelector?.("svg") ?? container;
  if (!svg?.outerHTML) {
    throw new Error("MathJax did not return SVG.");
  }

  return svg.outerHTML;
}

export function createVisualFormulaHtml({
  latex,
  manualNumber = "",
  mode = "inline",
  svg,
} = {}) {
  const normalizedLatex = normalizeLatexInput(latex);
  if (!normalizedLatex) {
    throw new Error(EMPTY_LATEX_MESSAGE);
  }

  const src = encodeSvgDataUri(svg);
  const alt = `LaTeX formula: ${normalizedLatex}`;
  const image = `<img src="${src}" alt="${escapeAttribute(
    alt,
  )}" style="max-width:100%;height:auto;vertical-align:middle;">`;

  if (mode === "numbered") {
    const number = normalizeLatexInput(manualNumber) || "#";
    return `<table data-latexsnipper-formula="visual" role="presentation" style="width:100%;border-collapse:collapse;margin:8px 0;"><tr><td style="text-align:center;">${image}</td><td style="text-align:right;white-space:nowrap;padding-left:12px;">(${escapeHtml(
      number,
    )})</td></tr></table>`;
  }

  if (mode === "display") {
    return `<div data-latexsnipper-formula="visual" style="text-align:center;margin:8px 0;">${image}</div>`;
  }

  return `<span data-latexsnipper-formula="visual" style="display:inline-block;vertical-align:middle;">${image}</span>`;
}
