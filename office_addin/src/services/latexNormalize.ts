const INTEGRAL_OPERATORS = [
  "\\\\iiiint",
  "\\\\iiint",
  "\\\\iint",
  "\\\\oint",
  "\\\\int"
].join("|");

const SCRIPT = String.raw`(?:\s*[_^]\s*(?:\{[^{}]*\}|[^\s_^{}\\]+))`;
const INTEGRAL_WITH_SCRIPTS = new RegExp(String.raw`(${INTEGRAL_OPERATORS}${SCRIPT}*)\s*(?=([A-Za-z\\]))`, "g");

export function normalizeOfficeLatex(latex: string): string {
  return latex
    .trim()
    .replace(/\u00a0/g, " ")
    .replace(INTEGRAL_WITH_SCRIPTS, "$1 ")
    .replace(/\\,\s*/g, "\\, ")
    .replace(/\s+/g, " ");
}
