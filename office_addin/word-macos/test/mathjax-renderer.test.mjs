import test from "node:test";
import assert from "node:assert/strict";

import {
  createVisualFormulaHtml,
  encodeSvgDataUri,
  renderLatexToSvg,
} from "../src/render/mathjaxRenderer.js";

test("renderLatexToSvg renders display math through MathJax", async () => {
  const calls = [];
  const mathJax = {
    startup: {
      promise: Promise.resolve(),
    },
    tex2svgPromise: async (latex, options) => {
      calls.push({ latex, options });
      return {
        querySelector: (selector) =>
          selector === "svg"
            ? { outerHTML: '<svg role="img"><text>x</text></svg>' }
            : null,
      };
    },
  };

  const svg = await renderLatexToSvg({
    latex: "x^2",
    mathJax,
    mode: "display",
  });

  assert.equal(svg, '<svg role="img"><text>x</text></svg>');
  assert.equal(calls[0].latex, "x^2");
  assert.equal(calls[0].options.display, true);
});

test("renderLatexToSvg reports a clear fallback reason when MathJax is unavailable", async () => {
  await assert.rejects(
    () => renderLatexToSvg({ latex: "x^2", mathJax: null }),
    /MathJax unavailable/,
  );
});

test("encodeSvgDataUri creates an SVG image data URI", () => {
  const uri = encodeSvgDataUri("<svg><text>π</text></svg>");

  assert.match(uri, /^data:image\/svg\+xml;base64,/);
});

test("createVisualFormulaHtml formats inline visual insertion as an image", () => {
  const html = createVisualFormulaHtml({
    latex: "\\frac{a}{b}",
    mode: "inline",
    svg: "<svg></svg>",
  });

  assert.match(html, /<img /);
  assert.match(html, /data:image\/svg\+xml;base64,/);
  assert.match(html, /LaTeX formula: \\frac\{a\}\{b\}/);
});

test("createVisualFormulaHtml formats numbered display insertion with manual number", () => {
  const html = createVisualFormulaHtml({
    latex: "E=mc^2",
    manualNumber: "2.1",
    mode: "numbered",
    svg: "<svg></svg>",
  });

  assert.match(html, /<table/);
  assert.match(html, /\(2.1\)/);
});
