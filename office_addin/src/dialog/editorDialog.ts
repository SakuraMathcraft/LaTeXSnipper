import "../styles/dialog.css";

import { configureLocale, displayMessage, localizeDocument, t } from "../services/i18n";
import { MathLiveCore } from "../taskpane/mathliveEditor";

type DialogInitArgs = {
  mode: "insert" | "update";
  latex?: string;
  equationId?: string;
  bridgeUrl: string;
  bridgeToken: string;
  display?: boolean;
  autoNumber?: boolean;
  manualNumber?: string;
  numberValue?: string;
  host: "word" | "powerpoint";
  requireManualNumber?: boolean;
  locale?: string;
};

type EquationDraft = {
  latex: string;
  display: boolean;
  numbering: "none" | "auto" | "manual";
  manualNumber?: string;
  numberValue?: string;
};

type DialogMessage =
  | { type: "insert"; draft: EquationDraft; equationId?: string }
  | { type: "close" };

type SymbolItem = {
  label: string;
  latex: string;
  variant?: "struct" | "bmatrix" | "pmatrix" | "vmatrix" | "cases";
};

type MatrixEnv = "bmatrix" | "pmatrix" | "vmatrix" | "cases";

const SYMBOL_GROUPS: { id: string; items: SymbolItem[] }[] = [
  {
    id: "symbolGreekLower",
    items: [
      { label: "α", latex: "\\alpha" }, { label: "β", latex: "\\beta" },
      { label: "γ", latex: "\\gamma" }, { label: "δ", latex: "\\delta" },
      { label: "ε", latex: "\\epsilon" }, { label: "ζ", latex: "\\zeta" },
      { label: "η", latex: "\\eta" }, { label: "θ", latex: "\\theta" },
      { label: "ι", latex: "\\iota" }, { label: "κ", latex: "\\kappa" },
      { label: "λ", latex: "\\lambda" }, { label: "μ", latex: "\\mu" },
      { label: "ν", latex: "\\nu" }, { label: "ξ", latex: "\\xi" },
      { label: "π", latex: "\\pi" }, { label: "ρ", latex: "\\rho" },
      { label: "σ", latex: "\\sigma" }, { label: "τ", latex: "\\tau" },
      { label: "υ", latex: "\\upsilon" }, { label: "φ", latex: "\\phi" },
      { label: "χ", latex: "\\chi" }, { label: "ψ", latex: "\\psi" },
      { label: "ω", latex: "\\omega" },
      { label: "ε", latex: "\\varepsilon" }, { label: "ϑ", latex: "\\vartheta" },
      { label: "ϖ", latex: "\\varpi" }, { label: "ϱ", latex: "\\varrho" },
      { label: "ς", latex: "\\varsigma" }, { label: "φ", latex: "\\varphi" },
      { label: "ϝ", latex: "\\digamma" },
    ],
  },
  {
    id: "symbolGreekUpper",
    items: [
      { label: "Γ", latex: "\\Gamma" }, { label: "Δ", latex: "\\Delta" },
      { label: "Θ", latex: "\\Theta" }, { label: "Λ", latex: "\\Lambda" },
      { label: "Ξ", latex: "\\Xi" }, { label: "Π", latex: "\\Pi" },
      { label: "Σ", latex: "\\Sigma" }, { label: "Υ", latex: "\\Upsilon" },
      { label: "Φ", latex: "\\Phi" }, { label: "Ψ", latex: "\\Psi" },
      { label: "Ω", latex: "\\Omega" },
    ],
  },
  {
    id: "symbolOperators",
    items: [
      { label: "±", latex: "\\pm" }, { label: "∓", latex: "\\mp" },
      { label: "×", latex: "\\times" }, { label: "÷", latex: "\\div" },
      { label: "·", latex: "\\cdot" }, { label: "∗", latex: "\\ast" },
      { label: "⋆", latex: "\\star" }, { label: "∘", latex: "\\circ" },
      { label: "•", latex: "\\bullet" }, { label: "†", latex: "\\dagger" },
      { label: "‡", latex: "\\ddagger" }, { label: "∖", latex: "\\setminus" },
      { label: "⊕", latex: "\\oplus" }, { label: "⊖", latex: "\\ominus" },
      { label: "⊗", latex: "\\otimes" }, { label: "⊘", latex: "\\oslash" },
      { label: "⊙", latex: "\\odot" }, { label: "⊞", latex: "\\boxplus" },
      { label: "⊟", latex: "\\boxminus" }, { label: "⊠", latex: "\\boxtimes" },
      { label: "∩", latex: "\\cap" }, { label: "∪", latex: "\\cup" },
      { label: "∨", latex: "\\vee" }, { label: "∧", latex: "\\wedge" },
      { label: "∖", latex: "\\setminus" }, { label: "⨿", latex: "\\amalg" },
      { label: "△", latex: "\\bigtriangleup" }, { label: "▽", latex: "\\bigtriangledown" },
      { label: "◃", latex: "\\triangleleft" }, { label: "▹", latex: "\\triangleright" },
    ],
  },
  {
    id: "symbolBigOps",
    items: [
      { label: "∑", latex: "\\sum" }, { label: "∏", latex: "\\prod" },
      { label: "∐", latex: "\\coprod" }, { label: "∫", latex: "\\int" },
      { label: "∬", latex: "\\iint" }, { label: "∭", latex: "\\iiint" },
      { label: "⨌", latex: "\\iiiint" }, { label: "∮", latex: "\\oint" },
      { label: "∯", latex: "\\oiint" }, { label: "∰", latex: "\\oiiint" },
      { label: "⋀", latex: "\\bigwedge" }, { label: "⋁", latex: "\\bigvee" },
      { label: "⋂", latex: "\\bigcap" }, { label: "⋃", latex: "\\bigcup" },
      { label: "⨃", latex: "\\bigsqcup" },
      { label: "⨁", latex: "\\bigoplus" }, { label: "⨂", latex: "\\bigotimes" },
      { label: "⨄", latex: "\\biguplus" },
    ],
  },
  {
    id: "symbolRelations",
    items: [
      { label: "≤", latex: "\\leq" }, { label: "≥", latex: "\\geq" },
      { label: "⩽", latex: "\\leqslant" }, { label: "⩾", latex: "\\geqslant" },
      { label: "≠", latex: "\\neq" }, { label: "≈", latex: "\\approx" },
      { label: "≡", latex: "\\equiv" }, { label: "≅", latex: "\\cong" },
      { label: "≃", latex: "\\simeq" }, { label: "∼", latex: "\\sim" },
      { label: "∝", latex: "\\propto" }, { label: "≍", latex: "\\asymp" },
      { label: "≐", latex: "\\doteq" }, { label: "≑", latex: "\\Doteq" },
      { label: "≪", latex: "\\ll" }, { label: "≫", latex: "\\gg" },
      { label: "≺", latex: "\\prec" }, { label: "≻", latex: "\\succ" },
      { label: "⪯", latex: "\\preceq" }, { label: "⪰", latex: "\\succeq" },
      { label: "⊏", latex: "\\sqsubset" }, { label: "⊐", latex: "\\sqsupset" },
      { label: "⊑", latex: "\\sqsubseteq" }, { label: "⊒", latex: "\\sqsupseteq" },
      { label: "∥", latex: "\\parallel" }, { label: "⊥", latex: "\\perp" },
      { label: "∣", latex: "\\mid" }, { label: "∤", latex: "\\nmid" },
      { label: "⋈", latex: "\\bowtie" }, { label: "⊢", latex: "\\vdash" },
      { label: "⊣", latex: "\\dashv" }, { label: "⊨", latex: "\\models" },
    ],
  },
  {
    id: "symbolSets",
    items: [
      { label: "∈", latex: "\\in" }, { label: "∉", latex: "\\notin" },
      { label: "∋", latex: "\\ni" }, { label: "⊂", latex: "\\subset" },
      { label: "⊃", latex: "\\supset" }, { label: "⊆", latex: "\\subseteq" },
      { label: "⊇", latex: "\\supseteq" }, { label: "⊊", latex: "\\subsetneq" },
      { label: "⊋", latex: "\\supsetneq" },
      { label: "∪", latex: "\\cup" }, { label: "∩", latex: "\\cap" },
      { label: "∅", latex: "\\emptyset" }, { label: "∅", latex: "\\varnothing" },
      { label: "∀", latex: "\\forall" }, { label: "∃", latex: "\\exists" },
      { label: "∄", latex: "\\nexists" }, { label: "¬", latex: "\\neg" },
      { label: "∧", latex: "\\land" }, { label: "∨", latex: "\\lor" },
      { label: "⇒", latex: "\\Rightarrow" }, { label: "⇐", latex: "\\Leftarrow" },
      { label: "⇔", latex: "\\Leftrightarrow" }, { label: "⟹", latex: "\\implies" },
      { label: "⟸", latex: "\\impliedby" }, { label: "⟺", latex: "\\iff" },
      { label: "⊤", latex: "\\top" }, { label: "⊥", latex: "\\bot" },
      { label: "ℵ", latex: "\\aleph" }, { label: "ℶ", latex: "\\beth" },
    ],
  },
  {
    id: "symbolNumberSets",
    items: [
      { label: "ℕ", latex: "\\mathbb{N}" }, { label: "ℤ", latex: "\\mathbb{Z}" },
      { label: "ℚ", latex: "\\mathbb{Q}" }, { label: "ℝ", latex: "\\mathbb{R}" },
      { label: "ℂ", latex: "\\mathbb{C}" }, { label: "ℙ", latex: "\\mathbb{P}" },
      { label: "𝔽", latex: "\\mathbb{F}" }, { label: "ℍ", latex: "\\mathbb{H}" },
    ],
  },
  {
    id: "symbolArrows",
    items: [
      { label: "→", latex: "\\rightarrow" }, { label: "←", latex: "\\leftarrow" },
      { label: "↑", latex: "\\uparrow" }, { label: "↓", latex: "\\downarrow" },
      { label: "↔", latex: "\\leftrightarrow" }, { label: "↕", latex: "\\updownarrow" },
      { label: "↗", latex: "\\nearrow" }, { label: "↘", latex: "\\searrow" },
      { label: "↙", latex: "\\swarrow" }, { label: "↖", latex: "\\nwarrow" },
      { label: "⇒", latex: "\\Rightarrow" }, { label: "⇐", latex: "\\Leftarrow" },
      { label: "⇑", latex: "\\Uparrow" }, { label: "⇓", latex: "\\Downarrow" },
      { label: "⇔", latex: "\\Leftrightarrow" }, { label: "⇕", latex: "\\Updownarrow" },
      { label: "↦", latex: "\\mapsto" }, { label: "↩", latex: "\\hookleftarrow" },
      { label: "↪", latex: "\\hookrightarrow" }, { label: "⇌", latex: "\\rightleftharpoons" },
      { label: "⇝", latex: "\\leadsto" }, { label: "⤳", latex: "\\dashrightarrow" },
      { label: "⇜", latex: "\\dashleftarrow" },
      { label: "⟶", latex: "\\longrightarrow" }, { label: "⟵", latex: "\\longleftarrow" },
      { label: "⟹", latex: "\\Longrightarrow" }, { label: "⟸", latex: "\\Longleftarrow" },
      { label: "⟺", latex: "\\Longleftrightarrow" }, { label: "⟼", latex: "\\longmapsto" },
    ],
  },
  {
    id: "symbolDelimiters",
    items: [
      { label: "( )", latex: "\\left( #? \\right)" },
      { label: "[ ]", latex: "\\left[ #? \\right]" },
      { label: "{ }", latex: "\\left\\{ #? \\right\\}" },
      { label: "⌈ ⌉", latex: "\\left\\lceil #? \\right\\rceil" },
      { label: "⌊ ⌋", latex: "\\left\\lfloor #? \\right\\rfloor" },
      { label: "⟨ ⟩", latex: "\\langle #? \\rangle" },
      { label: "‖ ‖", latex: "\\left\\| #? \\right\\|" },
      { label: "| |", latex: "\\left| #? \\right|" },
    ],
  },
  {
    id: "symbolFunctions",
    items: [
      { label: "sin", latex: "\\sin" }, { label: "cos", latex: "\\cos" },
      { label: "tan", latex: "\\tan" }, { label: "csc", latex: "\\csc" },
      { label: "sec", latex: "\\sec" }, { label: "cot", latex: "\\cot" },
      { label: "arcsin", latex: "\\arcsin" }, { label: "arccos", latex: "\\arccos" },
      { label: "arctan", latex: "\\arctan" }, { label: "sinh", latex: "\\sinh" },
      { label: "cosh", latex: "\\cosh" }, { label: "tanh", latex: "\\tanh" },
      { label: "log", latex: "\\log" }, { label: "ln", latex: "\\ln" },
      { label: "lg", latex: "\\lg" }, { label: "exp", latex: "\\exp" },
      { label: "lim", latex: "\\lim" }, { label: "sup", latex: "\\sup" },
      { label: "inf", latex: "\\inf" }, { label: "max", latex: "\\max" },
      { label: "min", latex: "\\min" }, { label: "arg", latex: "\\arg" },
      { label: "deg", latex: "\\deg" }, { label: "gcd", latex: "\\gcd" },
      { label: "det", latex: "\\det" }, { label: "dim", latex: "\\dim" },
      { label: "ker", latex: "\\ker" }, { label: "Pr", latex: "\\Pr" },
      { label: "hom", latex: "\\hom" },
    ],
  },
  {
    id: "symbolAccents",
    items: [
      { label: "x̂", latex: "\\hat{x}" }, { label: "x̃", latex: "\\tilde{x}" },
      { label: "x̄", latex: "\\bar{x}" }, { label: "x⃗", latex: "\\vec{x}" },
      { label: "ẋ", latex: "\\dot{x}" }, { label: "ẍ", latex: "\\ddot{x}" },
      { label: "x̌", latex: "\\check{x}" }, { label: "x̆", latex: "\\breve{x}" },
      { label: "x̂", latex: "\\widehat{x}" }, { label: "x̃", latex: "\\widetilde{x}" },
      { label: "x̲", latex: "\\underline{x}" }, { label: "x̅", latex: "\\overline{x}" },
      { label: "x⃗", latex: "\\overrightarrow{x}" }, { label: "x⃖", latex: "\\overleftarrow{x}" },
      { label: "x⏞", latex: "\\overbrace{x}" }, { label: "x⏟", latex: "\\underbrace{x}" },
    ],
  },
  {
    id: "symbolFonts",
    items: [
      { label: "ℝ", latex: "\\mathbb{#?}", variant: "struct" },
      { label: "ℱ", latex: "\\mathcal{#?}", variant: "struct" },
      { label: "𝖌", latex: "\\mathfrak{#?}", variant: "struct" },
      { label: "𝐱", latex: "\\mathbf{#?}", variant: "struct" },
      { label: "x", latex: "\\mathrm{#?}", variant: "struct" },
      { label: "x", latex: "\\mathit{#?}", variant: "struct" },
      { label: "𝐱", latex: "\\mathsf{#?}", variant: "struct" },
      { label: "𝚡", latex: "\\mathtt{#?}", variant: "struct" },
      { label: "x", latex: "\\text{#?}", variant: "struct" },
    ],
  },
  {
    id: "symbolMisc",
    items: [
      { label: "∞", latex: "\\infty" }, { label: "∂", latex: "\\partial" },
      { label: "∇", latex: "\\nabla" }, { label: "ℏ", latex: "\\hbar" },
      { label: "ℓ", latex: "\\ell" }, { label: "ℜ", latex: "\\Re" },
      { label: "ℑ", latex: "\\Im" }, { label: "℧", latex: "\\mho" },
      { label: "℘", latex: "\\wp" },
      { label: "∠", latex: "\\angle" }, { label: "∡", latex: "\\measuredangle" },
      { label: "△", latex: "\\triangle" }, { label: "□", latex: "\\Box" },
      { label: "◇", latex: "\\Diamond" }, { label: "▽", latex: "\\triangledown" },
      { label: "…", latex: "\\dots" }, { label: "⋯", latex: "\\cdots" },
      { label: "⋮", latex: "\\vdots" }, { label: "⋱", latex: "\\ddots" },
      { label: "∎", latex: "\\blacksquare" }, { label: "★", latex: "\\bigstar" },
      { label: "♮", latex: "\\natural" }, { label: "♭", latex: "\\flat" },
      { label: "♯", latex: "\\sharp" }, { label: "ı", latex: "\\imath" },
      { label: "ȷ", latex: "\\jmath" }, { label: "Ⅎ", latex: "\\Finv" },
      { label: "ð", latex: "\\eth" }, { label: "ℷ", latex: "\\gimel" },
    ],
  },
  {
    id: "symbolStructures",
    items: [
      { label: "Fraction", latex: "\\frac{#?}{#?}", variant: "struct" },
      { label: "Superscript", latex: "^{#?}", variant: "struct" },
      { label: "Subscript", latex: "_{#?}", variant: "struct" },
      { label: "Square root", latex: "\\sqrt{#?}", variant: "struct" },
      { label: "Sub + Sup", latex: "_{#?}^{#?}", variant: "struct" },
      { label: "Sum", latex: "\\sum_{#?}^{#?}", variant: "struct" },
      { label: "Integral", latex: "\\int_{#?}^{#?} #?\\,d#?", variant: "struct" },
      { label: "Limit", latex: "\\lim_{#? \\to #?}", variant: "struct" },
      { label: "Bmatrix", latex: "", variant: "bmatrix" },
      { label: "Pmatrix", latex: "", variant: "pmatrix" },
      { label: "Determinant", latex: "", variant: "vmatrix" },
      { label: "Cases", latex: "", variant: "cases" },
      { label: "Aligned", latex: "\\begin{aligned} #? &= #? \\\\ #? &= #? \\end{aligned}", variant: "struct" },
      { label: "Binomial", latex: "\\binom{#?}{#?}", variant: "struct" },
      { label: "Nth root", latex: "\\sqrt[#?]{#?}", variant: "struct" },
      { label: "Product", latex: "\\prod_{#?}^{#?}", variant: "struct" },
      { label: "Gather", latex: "\\begin{gathered} #? \\\\ #? \\end{gathered}", variant: "struct" },
    ],
  },
];

const MATRIX_ENV_NAMES: Record<MatrixEnv, { name: string; env: string }> = {
  bmatrix: { name: "Bmatrix", env: "bmatrix" },
  pmatrix: { name: "Pmatrix", env: "pmatrix" },
  vmatrix: { name: "Determinant", env: "vmatrix" },
  cases: { name: "Cases", env: "cases" },
};

let core: MathLiveCore;
let initArgs: DialogInitArgs;
let updatingFromMathLive = false;

Office.onReady(async () => {
  initArgs = readInitArgs();
  configureLocale(initArgs.locale || Office.context.displayLanguage);
  localizeDocument();

  const elements = {
    mathfieldHost: requiredElement("mathfieldHost", HTMLElement),
    insertButton: requiredElement("insertButton", HTMLButtonElement),
    symbolsToggle: requiredElement("symbolsToggle", HTMLButtonElement),
    symbolPanel: requiredElement("symbolPanel", HTMLElement),
    displayMode: requiredElement("displayMode", HTMLInputElement),
    autoNumber: requiredElement("autoNumber", HTMLInputElement),
    manualNumber: requiredElement("manualNumber", HTMLInputElement),
    latexSource: requiredElement("latexSource", HTMLTextAreaElement),
    latexPanel: requiredElement("latexPanel", HTMLElement),
    latexPanelToggle: requiredElement("latexPanelToggle", HTMLElement),
    dialogStatus: requiredElement("dialogStatus", HTMLElement),
    displayOption: requiredElement("displayOption", HTMLElement),
    autoNumberOption: requiredElement("autoNumberOption", HTMLElement),
  };
  const isPowerPoint = initArgs.host === "powerpoint";
  elements.displayOption.hidden = isPowerPoint;
  elements.autoNumberOption.hidden = isPowerPoint;
  elements.autoNumber.disabled = isPowerPoint;

  try {
    core = await MathLiveCore.create(elements.mathfieldHost);
  } catch (error: unknown) {
    setStatus(displayMessage(error instanceof Error ? error.message : String(error)), true);
    return;
  }
  buildSymbolPanel();

  if (initArgs.latex) {
    core.setLatex(initArgs.latex);
    elements.latexSource.value = initArgs.latex;
  }

  if (initArgs.mode === "update") {
    elements.insertButton.textContent = t("update");
    if (initArgs.display !== undefined) elements.displayMode.checked = initArgs.display;
    if (initArgs.autoNumber) {
      elements.autoNumber.checked = true;
      elements.manualNumber.value = "";
    } else if (initArgs.numberValue) {
      elements.manualNumber.value = initArgs.numberValue;
      elements.autoNumber.checked = false;
    } else {
      elements.autoNumber.checked = false;
      if (initArgs.manualNumber !== undefined) elements.manualNumber.value = initArgs.manualNumber;
    }
    setStatus(t("editingEquation"));
  }
  if (isPowerPoint) {
    elements.autoNumber.checked = false;
  }

  elements.manualNumber.addEventListener("input", () => {
    if (elements.manualNumber.value.trim()) {
      elements.autoNumber.checked = false;
    }
  });
  elements.autoNumber.addEventListener("change", () => {
    if (elements.autoNumber.checked) {
      elements.manualNumber.value = "";
    }
  });

  core.onLatexChange((latex) => {
    updatingFromMathLive = true;
    elements.latexSource.value = latex;
    updatingFromMathLive = false;
  });

  let latexSourceTimer: ReturnType<typeof setTimeout> | null = null;
  elements.latexSource.addEventListener("input", () => {
    if (updatingFromMathLive) return;
    if (latexSourceTimer !== null) clearTimeout(latexSourceTimer);
    latexSourceTimer = setTimeout(() => {
      core.setLatex(elements.latexSource.value);
      core.focus();
    }, 250);
  });

  elements.latexPanelToggle.addEventListener("click", () => {
    elements.latexPanel.classList.toggle("collapsed");
  });

  elements.symbolsToggle.addEventListener("click", () => {
    elements.symbolPanel.classList.toggle("collapsed");
    elements.symbolsToggle.classList.toggle("active", !elements.symbolPanel.classList.contains("collapsed"));
  });

  elements.insertButton.addEventListener("click", () => void handleInsert(elements));
  Office.context.ui.addHandlerAsync(Office.EventType.DialogParentMessageReceived, (arg: { message?: string }) => {
    handleParentMessage(elements, arg.message);
  });
  window.addEventListener("keydown", (event) => handleKeyboard(event, elements));

  core.focus();
  setStatus(initArgs.requireManualNumber ? t("pptManualNumberPrompt") : t("ready"));
});

function buildSymbolPanel(): void {
  for (const group of SYMBOL_GROUPS) {
    const grid = document.getElementById(group.id);
    if (!grid) continue;
    for (const item of group.items) {
      if (item.variant === "bmatrix" || item.variant === "pmatrix" || item.variant === "vmatrix" || item.variant === "cases") {
        buildMatrixControl(grid, item.variant);
        continue;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = localizeStructureLabel(item.label);
      btn.title = item.latex;
      if (item.variant === "struct") btn.className = "struct-btn";
      btn.addEventListener("click", () => {
        core.mathfield.insert(item.latex, { format: "latex" });
        core.focus();
      });
      grid.appendChild(btn);
    }
  }
}

function buildMatrixControl(grid: HTMLElement, variant: MatrixEnv): void {
  const { name, env } = MATRIX_ENV_NAMES[variant];
  const isCases = variant === "cases";

  const row = document.createElement("div");
  row.className = "matrix-row";

  const selRows = document.createElement("select");
  selRows.title = t("rows");
  for (let i = 1; i <= 10; i++) {
    selRows.appendChild(new Option(String(i), String(i), i === 2, i === 2));
  }

  let selCols: HTMLSelectElement | null = null;
  if (!isCases) {
    selCols = document.createElement("select");
    selCols.title = t("columns");
    for (let i = 1; i <= 10; i++) {
      selCols.appendChild(new Option(String(i), String(i), i === 2, i === 2));
    }
  }

  const insertBtn = document.createElement("button");
  insertBtn.type = "button";
  insertBtn.textContent = localizeStructureLabel(name);
  insertBtn.className = "struct-btn";
  insertBtn.style.cssText = "flex:1;min-width:0;";

  insertBtn.addEventListener("click", () => {
    const r = parseInt(selRows.value) || 2;
    const c = isCases ? 2 : (parseInt(selCols!.value) || 2);
    const rowStrs: string[] = [];
    for (let i = 0; i < r; i++) {
      rowStrs.push(new Array(c).fill("#?").join(" & "));
    }
    core.mathfield.insert(`\\begin{${env}} ${rowStrs.join(" \\\\ ")} \\end{${env}}`, { format: "latex" });
    core.focus();
  });

  row.appendChild(selRows);
  if (selCols) row.appendChild(selCols);
  row.appendChild(insertBtn);
  grid.appendChild(row);
}

function readInitArgs(): DialogInitArgs {
  const params = new URLSearchParams(window.location.search);
  return {
    mode: (params.get("mode") as "insert" | "update") || "insert",
    latex: params.get("latex") || undefined,
    equationId: params.get("equationId") || undefined,
    bridgeUrl: params.get("bridgeUrl") || "http://127.0.0.1:8765",
    bridgeToken: params.get("bridgeToken") || "",
    display: params.has("display") ? params.get("display") === "true" : undefined,
    autoNumber: params.has("autoNumber") ? params.get("autoNumber") === "true" : undefined,
    manualNumber: params.get("manualNumber") || undefined,
    numberValue: params.get("numberValue") || undefined,
    host: params.get("host") === "powerpoint" ? "powerpoint" : "word",
    requireManualNumber: params.get("requireManualNumber") === "true",
    locale: params.get("locale") || undefined,
  };
}

function readDraft(elements: {
  latexSource: HTMLTextAreaElement;
  displayMode: HTMLInputElement;
  autoNumber: HTMLInputElement;
  manualNumber: HTMLInputElement;
}): EquationDraft {
  let latex = elements.latexSource.value.trim();
  if (!latex) throw new Error(t("latexRequired"));
  latex = latex.replace(/#\?/g, "0").replace(/\\placeholder\{\}/g, "0");
  const numbering = elements.autoNumber.checked ? "auto"
    : elements.manualNumber.value.trim() ? "manual" : "none";
  const originalNumbering = initArgs.autoNumber ? "auto"
    : initArgs.numberValue ? "manual" : "none";
  return {
    latex,
    display: elements.displayMode.checked,
    numbering,
    manualNumber: elements.manualNumber.value || undefined,
    numberValue: numbering === originalNumbering ? initArgs.numberValue : undefined,
  };
}

function sendMessage(message: DialogMessage): void {
  Office.context.ui.messageParent(JSON.stringify(message));
}

function handleParentMessage(
  elements: { latexSource: HTMLTextAreaElement; insertButton: HTMLButtonElement },
  raw?: string
): void {
  if (!raw) {
    return;
  }
  let message: { type?: string; message?: string; latex?: string };
  try {
    message = JSON.parse(raw) as typeof message;
  } catch {
    return;
  }
  if (message.type === "insertFailed") {
    elements.insertButton.disabled = false;
    setStatus(message.message || t("ready"), true);
    return;
  }
  if (message.type === "ocrResult" && message.latex) {
    core.setLatex(message.latex);
    elements.latexSource.value = message.latex;
    core.focus();
    setStatus(t("ocrLoaded"));
  }
}

async function handleInsert(elements: {
  latexSource: HTMLTextAreaElement;
  displayMode: HTMLInputElement; autoNumber: HTMLInputElement;
  manualNumber: HTMLInputElement; insertButton: HTMLButtonElement;
}): Promise<void> {
  try {
    const draft = readDraft(elements);
    if (initArgs.host === "powerpoint" && initArgs.requireManualNumber && draft.numbering !== "manual") {
      throw new Error("PowerPoint numbered images require a manual number.");
    }
    elements.insertButton.disabled = true;
    sendMessage({ type: "insert", draft, equationId: initArgs.equationId });
    setStatus(t("inserting"));
  } catch (error) {
    setStatus(displayMessage(error instanceof Error ? error.message : String(error)), true);
    elements.insertButton.disabled = false;
  }
}

function handleKeyboard(
  event: KeyboardEvent,
  _elements: {
    displayMode: HTMLInputElement; autoNumber: HTMLInputElement;
    manualNumber: HTMLInputElement; insertButton: HTMLButtonElement;
  }
): void {
  if (event.key === "Escape") {
    event.preventDefault();
    if (core.getLatex().trim() && !window.confirm(t("discardFormula"))) return;
    sendMessage({ type: "close" });
  }
}

function requiredElement<T extends HTMLElement>(id: string, ctor: { new (...args: never[]): T }): T {
  const el = document.getElementById(id);
  if (!(el instanceof ctor)) throw new Error(`Missing dialog element: ${id}`);
  return el;
}

function setStatus(message: string, isError = false): void {
  const el = document.getElementById("dialogStatus");
  if (!el) return;
  el.textContent = message;
  el.className = `dialog-status${isError ? " error" : ""}`;
}

function localizeStructureLabel(label: string): string {
  const keys: Record<string, Parameters<typeof t>[0]> = {
    Fraction: "fraction",
    Superscript: "superscript",
    Subscript: "subscript",
    "Square root": "squareRoot",
    "Sub + Sup": "subSup",
    Sum: "sum",
    Integral: "integral",
    Limit: "limit",
    Determinant: "determinant",
    Cases: "cases",
    Aligned: "aligned",
    Binomial: "binomial",
    "Nth root": "nthRoot",
    Product: "product",
    Gather: "gather"
  };
  return keys[label] ? t(keys[label]) : label;
}
