import test from "node:test";
import assert from "node:assert/strict";

import { formatInlineFormula, normalizeLatexInput } from "../src/latex.js";

test("normalizeLatexInput trims surrounding whitespace", () => {
  assert.equal(normalizeLatexInput("  x^2 + y^2  \n"), "x^2 + y^2");
});

test("formatInlineFormula wraps LaTeX in inline delimiters", () => {
  assert.equal(formatInlineFormula("x^2"), "\\( x^2 \\)");
});

test("formatInlineFormula trims LaTeX before wrapping", () => {
  assert.equal(formatInlineFormula("  \\frac{a}{b}\n"), "\\( \\frac{a}{b} \\)");
});

test("formatInlineFormula rejects empty input", () => {
  assert.throws(
    () => formatInlineFormula("  \n"),
    /Enter LaTeX before inserting/,
  );
});
