import { formatInlineFormula, normalizeLatexInput } from "../latex.js";

const EMPTY_LATEX_MESSAGE = "Enter LaTeX before inserting.";
const WORD_NOT_READY_MESSAGE = "Word is not ready yet.";

export function formatDisplayFormula(value) {
  const latex = normalizeLatexInput(value);
  if (!latex) {
    throw new Error(EMPTY_LATEX_MESSAGE);
  }
  return `\n\\[ ${latex} \\]\n`;
}

export function formatNumberedFormula(value, manualNumber) {
  const latex = normalizeLatexInput(value);
  if (!latex) {
    throw new Error(EMPTY_LATEX_MESSAGE);
  }

  const number = normalizeLatexInput(manualNumber) || "#";
  return `\n\\[ ${latex} \\]    (${number})\n`;
}

export function formatFormulaForInsertion({
  latex,
  mode = "inline",
  manualNumber = "",
} = {}) {
  if (mode === "display") {
    return formatDisplayFormula(latex);
  }

  if (mode === "numbered") {
    return formatNumberedFormula(latex, manualNumber);
  }

  return formatInlineFormula(latex);
}

export async function insertFormula({
  latex,
  mode = "inline",
  manualNumber = "",
  documentApi = globalThis.Office?.context?.document,
  officeApi = globalThis.Office,
} = {}) {
  const text = formatFormulaForInsertion({ latex, mode, manualNumber });

  return new Promise((resolve, reject) => {
    if (!documentApi?.setSelectedDataAsync || !officeApi?.CoercionType?.Text) {
      reject(new Error(WORD_NOT_READY_MESSAGE));
      return;
    }

    documentApi.setSelectedDataAsync(
      text,
      { coercionType: officeApi.CoercionType.Text },
      (result) => {
        if (result.status === officeApi.AsyncResultStatus.Succeeded) {
          resolve({ text });
          return;
        }

        reject(new Error(result.error?.message || "Word insertion failed."));
      },
    );
  });
}
