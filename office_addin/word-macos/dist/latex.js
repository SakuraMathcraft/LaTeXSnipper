const EMPTY_LATEX_MESSAGE = "Enter LaTeX before inserting.";

export function normalizeLatexInput(value) {
  return String(value ?? "").trim();
}

export function formatInlineFormula(value) {
  const latex = normalizeLatexInput(value);
  if (!latex) {
    throw new Error(EMPTY_LATEX_MESSAGE);
  }
  return `\\( ${latex} \\)`;
}
