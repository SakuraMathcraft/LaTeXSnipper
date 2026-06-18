import { formatInlineFormula, normalizeLatexInput } from "../latex.js";
import {
  createVisualFormulaHtml,
  renderLatexToSvg,
} from "../render/mathjaxRenderer.js";

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

function setSelectedData({ data, documentApi, officeApi, type }) {
  return new Promise((resolve, reject) => {
    if (!documentApi?.setSelectedDataAsync || !officeApi?.CoercionType?.[type]) {
      reject(new Error(WORD_NOT_READY_MESSAGE));
      return;
    }

    documentApi.setSelectedDataAsync(
      data,
      { coercionType: officeApi.CoercionType[type] },
      (result) => {
        if (result.status === officeApi.AsyncResultStatus.Succeeded) {
          resolve();
          return;
        }

        reject(new Error(result.error?.message || "Word insertion failed."));
      },
    );
  });
}

async function insertTextFormula({
  documentApi,
  latex,
  manualNumber,
  mode,
  officeApi,
}) {
  const text = formatFormulaForInsertion({ latex, mode, manualNumber });
  await setSelectedData({
    data: text,
    documentApi,
    officeApi,
    type: "Text",
  });
  return { insertedAs: "text", text };
}

async function insertVisualFormula({
  documentApi,
  latex,
  manualNumber,
  mode,
  officeApi,
  renderSvg,
}) {
  const svg = await renderSvg({ latex, mode });
  const html = createVisualFormulaHtml({ latex, manualNumber, mode, svg });
  await setSelectedData({
    data: html,
    documentApi,
    officeApi,
    type: "Html",
  });
  return { html, insertedAs: "visual" };
}

export async function insertFormula({
  latex,
  mode = "inline",
  manualNumber = "",
  documentApi = globalThis.Office?.context?.document,
  officeApi = globalThis.Office,
  renderSvg = renderLatexToSvg,
  visual = false,
} = {}) {
  if (!visual) {
    return insertTextFormula({
      documentApi,
      latex,
      manualNumber,
      mode,
      officeApi,
    });
  }

  try {
    return await insertVisualFormula({
      documentApi,
      latex,
      manualNumber,
      mode,
      officeApi,
      renderSvg,
    });
  } catch (visualError) {
    const textResult = await insertTextFormula({
      documentApi,
      latex,
      manualNumber,
      mode,
      officeApi,
    });
    return {
      ...textResult,
      insertedAs: "text-fallback",
      visualError,
    };
  }
}
