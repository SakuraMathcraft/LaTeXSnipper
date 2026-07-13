export const FORMULA_MODES = ["inline", "display", "numbered"] as const;
export const MAX_LATEX_LENGTH = 16_384;

export type FormulaMode = (typeof FORMULA_MODES)[number];

export interface FormulaDraft {
  readonly latex: string;
  readonly mode: FormulaMode;
  readonly manualNumber: string;
}

export interface FormulaMetadata {
  readonly schemaVersion: 1;
  readonly documentId: string;
  readonly equationId: string;
  readonly latex: string;
  readonly displayMode: "Inline" | "Display";
  readonly numberingMode: "None" | "Manual";
  readonly numberText: string;
  readonly renderEngine: "MathJax-3.2.2";
  readonly fontScale: 1;
}

export class FormulaValidationError extends Error {
  constructor(
    readonly code: "empty" | "too-long",
    message: string,
  ) {
    super(message);
    this.name = "FormulaValidationError";
  }
}

export function normalizeLatexInput(value: unknown): string {
  return String(value ?? "")
    .replace(/\r\n?/g, "\n")
    .trim();
}

export function isFormulaMode(value: unknown): value is FormulaMode {
  return typeof value === "string" && FORMULA_MODES.includes(value as FormulaMode);
}

export function normalizeFormulaMode(value: unknown): FormulaMode {
  return isFormulaMode(value) ? value : "inline";
}

export function validateLatex(value: unknown): string {
  const latex = normalizeLatexInput(value);
  if (!latex) {
    throw new FormulaValidationError("empty", "请先输入 LaTeX 公式。");
  }
  if (latex.length > MAX_LATEX_LENGTH) {
    throw new FormulaValidationError(
      "too-long",
      `LaTeX 不能超过 ${MAX_LATEX_LENGTH.toLocaleString()} 个字符。`,
    );
  }
  return latex;
}

export function createFormulaDraft(
  values: Partial<FormulaDraft> = {},
): FormulaDraft {
  return {
    latex: normalizeLatexInput(values.latex),
    mode: normalizeFormulaMode(values.mode),
    manualNumber: normalizeLatexInput(values.manualNumber),
  };
}

export function createFormulaMetadata(
  draft: FormulaDraft,
  documentId: string,
  idFactory: () => string = () => globalThis.crypto.randomUUID(),
): FormulaMetadata {
  const latex = validateLatex(draft.latex);
  const normalizedDocumentId = normalizeLatexInput(documentId);
  if (!normalizedDocumentId) {
    throw new TypeError("documentId must not be empty.");
  }

  return {
    schemaVersion: 1,
    documentId: normalizedDocumentId,
    equationId: idFactory(),
    latex,
    displayMode: draft.mode === "inline" ? "Inline" : "Display",
    numberingMode: draft.mode === "numbered" ? "Manual" : "None",
    numberText: draft.mode === "numbered" ? normalizeLatexInput(draft.manualNumber) : "",
    renderEngine: "MathJax-3.2.2",
    fontScale: 1,
  };
}
