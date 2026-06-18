import test from "node:test";
import assert from "node:assert/strict";

import { formatInlineFormula, normalizeLatexInput } from "../src/latex.js";
import {
  formatDisplayFormula,
  formatFormulaForInsertion,
  formatNumberedFormula,
} from "../src/office/wordInsert.js";

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

test("formatFormulaForInsertion formats inline fallback text", () => {
  assert.equal(
    formatFormulaForInsertion({ latex: "\\frac{a}{b}", mode: "inline" }),
    "\\( \\frac{a}{b} \\)",
  );
});

test("formatDisplayFormula formats display fallback text", () => {
  assert.equal(
    formatDisplayFormula("x^2 + y^2 = z^2"),
    "\n\\[ x^2 + y^2 = z^2 \\]\n",
  );
});

test("formatNumberedFormula formats manual number fallback text", () => {
  assert.equal(
    formatNumberedFormula("\\int_0^1 x dx", "2.1"),
    "\n\\[ \\int_0^1 x dx \\]    (2.1)\n",
  );
});

test("formatNumberedFormula uses placeholder when manual number is empty", () => {
  assert.equal(
    formatFormulaForInsertion({ latex: "E=mc^2", mode: "numbered", manualNumber: "" }),
    "\n\\[ E=mc^2 \\]    (#)\n",
  );
});
