import { describe, expect, it } from "vitest";

import {
  createFormulaDraft,
  createFormulaMetadata,
  FormulaValidationError,
  MAX_LATEX_LENGTH,
  normalizeFormulaMode,
  normalizeLatexInput,
  validateLatex,
} from "../src/domain/formula";

describe("formula domain", () => {
  it("normalizes whitespace and line endings without changing formula content", () => {
    expect(normalizeLatexInput("  a\r\n+ b\r  ")).toBe("a\n+ b");
  });

  it("falls back to inline for unknown modes", () => {
    expect(normalizeFormulaMode("display")).toBe("display");
    expect(normalizeFormulaMode("unexpected")).toBe("inline");
  });

  it("rejects empty and overlong LaTeX", () => {
    expect(() => validateLatex("  ")).toThrowError(FormulaValidationError);
    expect(() => validateLatex("x".repeat(MAX_LATEX_LENGTH + 1))).toThrowError(
      /不能超过/,
    );
  });

  it("creates stable cross-platform metadata semantics with an injected id", () => {
    const metadata = createFormulaMetadata(
      createFormulaDraft({ latex: " x^2 ", mode: "numbered", manualNumber: " (7) " }),
      "document-1",
      () => "equation-1",
    );

    expect(metadata).toEqual({
      schemaVersion: 1,
      documentId: "document-1",
      equationId: "equation-1",
      latex: "x^2",
      displayMode: "Display",
      numberingMode: "Manual",
      numberText: "(7)",
      renderEngine: "MathJax-3.2.2",
      fontScale: 1,
    });
  });
});
