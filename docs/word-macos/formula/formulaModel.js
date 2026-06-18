import { normalizeLatexInput } from "../latex.js";

export const FORMULA_MODES = Object.freeze(["inline", "display", "numbered"]);

export function isFormulaMode(value) {
  return FORMULA_MODES.includes(value);
}

export function normalizeFormulaMode(value) {
  return isFormulaMode(value) ? value : "inline";
}

export function createFormulaId() {
  return `formula-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

export function createFormulaModel({
  latex = "",
  mode = "inline",
  manualNumber = "",
  now = () => new Date().toISOString(),
  idFactory = createFormulaId,
} = {}) {
  const timestamp = now();

  return {
    id: idFactory(),
    latex: normalizeLatexInput(latex),
    mode: normalizeFormulaMode(mode),
    manualNumber: normalizeLatexInput(manualNumber),
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}
