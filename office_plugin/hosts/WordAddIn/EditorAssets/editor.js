import { MathfieldElement } from "./vendor/mathlive.min.mjs";

const STRINGS = {
  en: {
    acceptInsert: "Insert",
    acceptUpdate: "Update",
    cancel: "Cancel",
    ready: "Ready",
    latexRequired: "Enter a LaTeX formula first.",
    rows: "Rows",
    columns: "Columns",
    tabs: {
      greek: "Greek",
      structures: "Structures",
      calculus: "Calculus",
      linear: "Linear",
      relations: "Relations",
      operators: "Operators",
      bigops: "Big Ops",
      arrows: "Arrows",
      sets: "Sets",
      functions: "Functions",
      probability: "Probability",
      chemistry: "Chemistry",
      accents: "Accents",
      misc: "Misc",
    },
  },
  zh: {
    acceptInsert: "插入",
    acceptUpdate: "更新",
    cancel: "取消",
    ready: "就绪",
    latexRequired: "请先输入 LaTeX 公式。",
    rows: "行数",
    columns: "列数",
    tabs: {
      greek: "希腊",
      structures: "结构",
      calculus: "微积分",
      linear: "线代",
      relations: "关系",
      operators: "运算",
      bigops: "大型",
      arrows: "箭头",
      sets: "集合",
      functions: "函数",
      probability: "概率",
      chemistry: "化学",
      accents: "字体",
      misc: "其他",
    },
  },
};

const GROUPS = [
  {
    id: "greek",
    items: [
      ["α", "\\alpha"], ["β", "\\beta"], ["γ", "\\gamma"], ["δ", "\\delta"], ["ε", "\\epsilon"], ["ϵ", "\\varepsilon"],
      ["ζ", "\\zeta"], ["η", "\\eta"], ["θ", "\\theta"], ["ϑ", "\\vartheta"], ["ι", "\\iota"], ["κ", "\\kappa"],
      ["λ", "\\lambda"], ["μ", "\\mu"], ["ν", "\\nu"], ["ξ", "\\xi"], ["π", "\\pi"], ["ϖ", "\\varpi"],
      ["ρ", "\\rho"], ["ϱ", "\\varrho"], ["σ", "\\sigma"], ["ς", "\\varsigma"], ["τ", "\\tau"], ["υ", "\\upsilon"],
      ["φ", "\\phi"], ["ϕ", "\\varphi"], ["χ", "\\chi"], ["ψ", "\\psi"], ["ω", "\\omega"],
      ["Γ", "\\Gamma"], ["Δ", "\\Delta"], ["Θ", "\\Theta"], ["Λ", "\\Lambda"], ["Ξ", "\\Xi"], ["Π", "\\Pi"],
      ["Σ", "\\Sigma"], ["Φ", "\\Phi"], ["Ψ", "\\Psi"], ["Ω", "\\Omega"],
    ],
  },
  {
    id: "structures",
    structures: true,
    items: [
      ["分数", "\\frac{#?}{#?}", "Fraction"],
      ["根号", "\\sqrt{#?}", "Square root"],
      ["n 次根", "\\sqrt[#?]{#?}", "Nth root"],
      ["上标", "^{#?}", "Superscript"],
      ["下标", "_{#?}", "Subscript"],
      ["上下标", "_{#?}^{#?}", "Subscript and superscript"],
      ["二项式", "\\binom{#?}{#?}", "Binomial"],
      ["求和", "\\sum_{#?}^{#?} #?", "Summation"],
      ["乘积", "\\prod_{#?}^{#?} #?", "Product"],
      ["积分", "\\int_{#?}^{#?} #?\\,d#?", "Integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["对齐", "\\begin{aligned} #? &= #? \\\\ #? &= #? \\end{aligned}", "Aligned equations"],
      ["分段", "matrix:cases", "Cases"],
      ["矩阵", "matrix:matrix", "Matrix"],
      ["圆括号矩阵", "matrix:pmatrix", "Parenthesized matrix"],
      ["方括号矩阵", "matrix:bmatrix", "Bracketed matrix"],
      ["花括号矩阵", "matrix:Bmatrix", "Braced matrix"],
      ["行列式", "matrix:vmatrix", "Determinant"],
    ],
  },
  {
    id: "calculus",
    structures: true,
    items: [
      ["导数", "\\frac{d}{dx}", "Derivative"],
      ["偏导", "\\frac{\\partial #?}{\\partial #?}", "Partial derivative"],
      ["梯度", "\\nabla #?", "Gradient"],
      ["散度", "\\nabla\\cdot #?", "Divergence"],
      ["旋度", "\\nabla\\times #?", "Curl"],
      ["微分", "#?\\,d#?", "Differential"],
      ["不定积分", "\\int #?\\,d#?", "Indefinite integral"],
      ["定积分", "\\int_{#?}^{#?} #?\\,d#?", "Definite integral"],
      ["曲线积分", "\\oint #?\\,d#?", "Contour integral"],
      ["二重积分", "\\iint_{#?} #?\\,d#?", "Double integral"],
      ["极限", "\\lim_{#? \\to #?} #?", "Limit"],
      ["级数", "\\sum_{n=0}^{\\infty} #?", "Series"],
      ["泰勒", "\\sum_{n=0}^{\\infty} \\frac{#?^{(n)}(#?)}{n!}(x-#?)^n", "Taylor expansion"],
      ["拉普拉斯", "\\mathcal{L}\\{#?\\}", "Laplace transform"],
      ["傅里叶", "\\mathcal{F}\\{#?\\}", "Fourier transform"],
    ],
  },
  {
    id: "linear",
    structures: true,
    items: [
      ["向量列", "\\begin{bmatrix} #? \\\\ #? \\end{bmatrix}", "Column vector"],
      ["点乘", "#? \\cdot #?", "Dot product"],
      ["叉乘", "#? \\times #?", "Cross product"],
      ["转置", "#?^{\\mathsf{T}}", "Transpose"],
      ["逆矩阵", "#?^{-1}", "Inverse"],
      ["范数", "\\left\\| #? \\right\\|", "Norm"],
      ["内积", "\\left\\langle #?, #? \\right\\rangle", "Inner product"],
      ["迹", "\\operatorname{tr}(#?)", "Trace"],
      ["秩", "\\operatorname{rank}(#?)", "Rank"],
      ["零空间", "\\ker(#?)", "Kernel"],
      ["张成", "\\operatorname{span}\\{#?\\}", "Span"],
      ["特征值", "\\lambda", "Eigenvalue"],
      ["特征向量", "\\mathbf{v}", "Eigenvector"],
      ["单位阵", "I_{#?}", "Identity matrix"],
      ["对角阵", "\\operatorname{diag}(#?)", "Diagonal matrix"],
    ],
  },
  {
    id: "relations",
    items: [
      ["=", "="], ["≠", "\\neq"], ["≈", "\\approx"], ["≃", "\\simeq"], ["≡", "\\equiv"], ["≅", "\\cong"],
      ["∼", "\\sim"], ["∝", "\\propto"], ["<", "<"], [">", ">"], ["≤", "\\leq"], ["≥", "\\geq"],
      ["≪", "\\ll"], ["≫", "\\gg"], ["⊂", "\\subset"], ["⊃", "\\supset"], ["⊆", "\\subseteq"], ["⊇", "\\supseteq"],
      ["∈", "\\in"], ["∉", "\\notin"], ["∋", "\\ni"], ["∥", "\\parallel"], ["⊥", "\\perp"], ["⊢", "\\vdash"],
    ],
  },
  {
    id: "operators",
    items: [
      ["+", "+"], ["−", "-"], ["±", "\\pm"], ["∓", "\\mp"], ["×", "\\times"], ["÷", "\\div"],
      ["·", "\\cdot"], ["∗", "\\ast"], ["∘", "\\circ"], ["∙", "\\bullet"], ["∩", "\\cap"], ["∪", "\\cup"],
      ["∧", "\\wedge"], ["∨", "\\vee"], ["⊕", "\\oplus"], ["⊖", "\\ominus"], ["⊗", "\\otimes"], ["⊘", "\\oslash"],
      ["∂", "\\partial"], ["∇", "\\nabla"], ["∞", "\\infty"], ["!", "!"], ["′", "^{\\prime}"],
    ],
  },
  {
    id: "bigops",
    items: [
      ["Σ", "\\sum"], ["Π", "\\prod"], ["∐", "\\coprod"], ["∫", "\\int"], ["∬", "\\iint"], ["∭", "\\iiint"],
      ["∮", "\\oint"], ["∯", "\\oiint"], ["∰", "\\oiiint"], ["⋀", "\\bigwedge"], ["⋁", "\\bigvee"], ["⋂", "\\bigcap"],
      ["⋃", "\\bigcup"], ["⨆", "\\bigsqcup"], ["⨁", "\\bigoplus"], ["⨂", "\\bigotimes"], ["⨄", "\\biguplus"],
    ],
  },
  {
    id: "arrows",
    items: [
      ["←", "\\leftarrow"], ["→", "\\rightarrow"], ["↑", "\\uparrow"], ["↓", "\\downarrow"], ["↔", "\\leftrightarrow"],
      ["⇐", "\\Leftarrow"], ["⇒", "\\Rightarrow"], ["⇔", "\\Leftrightarrow"], ["↦", "\\mapsto"], ["↗", "\\nearrow"],
      ["↘", "\\searrow"], ["↙", "\\swarrow"], ["↖", "\\nwarrow"], ["⟶", "\\longrightarrow"], ["⟵", "\\longleftarrow"],
      ["⟹", "\\Longrightarrow"], ["⟸", "\\Longleftarrow"], ["⟺", "\\Longleftrightarrow"],
    ],
  },
  {
    id: "sets",
    items: [
      ["∅", "\\emptyset"], ["∀", "\\forall"], ["∃", "\\exists"], ["¬", "\\neg"], ["∧", "\\land"], ["∨", "\\lor"],
      ["∴", "\\therefore"], ["∵", "\\because"], ["ℕ", "\\mathbb{N}"], ["ℤ", "\\mathbb{Z}"], ["ℚ", "\\mathbb{Q}"],
      ["ℝ", "\\mathbb{R}"], ["ℂ", "\\mathbb{C}"], ["ℙ", "\\mathbb{P}"], ["ℍ", "\\mathbb{H}"], ["⊤", "\\top"], ["⊥", "\\bot"],
    ],
  },
  {
    id: "functions",
    items: [
      ["sin", "\\sin"], ["cos", "\\cos"], ["tan", "\\tan"], ["sec", "\\sec"], ["csc", "\\csc"], ["cot", "\\cot"],
      ["arcsin", "\\arcsin"], ["arccos", "\\arccos"], ["arctan", "\\arctan"], ["sinh", "\\sinh"], ["cosh", "\\cosh"], ["tanh", "\\tanh"],
      ["log", "\\log"], ["ln", "\\ln"], ["exp", "\\exp"], ["lim", "\\lim"], ["max", "\\max"], ["min", "\\min"],
      ["sup", "\\sup"], ["inf", "\\inf"], ["det", "\\det"], ["dim", "\\dim"], ["gcd", "\\gcd"], ["Pr", "\\Pr"],
      ["arg", "\\arg"], ["deg", "\\deg"], ["ker", "\\ker"], ["hom", "\\hom"], ["rank", "\\operatorname{rank}"], ["span", "\\operatorname{span}"],
    ],
  },
  {
    id: "probability",
    structures: true,
    items: [
      ["概率", "\\mathbb{P}(#?)", "Probability"],
      ["期望", "\\mathbb{E}[#?]", "Expectation"],
      ["方差", "\\operatorname{Var}(#?)", "Variance"],
      ["协方差", "\\operatorname{Cov}(#?,#?)", "Covariance"],
      ["条件", "#? \\mid #?", "Conditional bar"],
      ["独立", "#? \\perp\\!\\!\\!\\perp #?", "Independence"],
      ["正态", "\\mathcal{N}(#?,#?)", "Normal distribution"],
      ["伯努利", "\\operatorname{Bernoulli}(#?)", "Bernoulli distribution"],
      ["二项", "\\operatorname{Bin}(#?,#?)", "Binomial distribution"],
      ["泊松", "\\operatorname{Poisson}(#?)", "Poisson distribution"],
      ["均匀", "\\operatorname{Uniform}(#?,#?)", "Uniform distribution"],
      ["似然", "\\mathcal{L}(#?;#?)", "Likelihood"],
    ],
  },
  {
    id: "chemistry",
    items: [
      ["→", "\\rightarrow"], ["⇌", "\\rightleftharpoons"], ["↑", "\\uparrow"], ["↓", "\\downarrow"],
      ["H₂O", "\\mathrm{H_2O}"], ["CO₂", "\\mathrm{CO_2}"], ["Na⁺", "\\mathrm{Na^+}"], ["Cl⁻", "\\mathrm{Cl^-}"],
      ["ion", "\\mathrm{#?}^{#?}"], ["aq", "\\mathrm{(aq)}"], ["s", "\\mathrm{(s)}"], ["l", "\\mathrm{(l)}"], ["g", "\\mathrm{(g)}"],
    ],
  },
  {
    id: "accents",
    items: [
      ["x̂", "\\hat{x}"], ["x̃", "\\tilde{x}"], ["x̄", "\\bar{x}"], ["x⃗", "\\vec{x}"], ["ẋ", "\\dot{x}"], ["ẍ", "\\ddot{x}"],
      ["x̲", "\\underline{x}"], ["x̅", "\\overline{x}"], ["𝐱", "\\mathbf{#?}"], ["𝑥", "\\mathit{#?}"],
      ["𝔁", "\\mathfrak{#?}"], ["𝓧", "\\mathcal{#?}"], ["ℝ", "\\mathbb{#?}"], ["text", "\\text{#?}"], ["rm", "\\mathrm{#?}"],
    ],
  },
  {
    id: "misc",
    items: [
      ["⋯", "\\cdots"], ["⋮", "\\vdots"], ["⋱", "\\ddots"], ["…", "\\dots"], ["□", "\\Box"], ["◇", "\\Diamond"],
      ["△", "\\triangle"], ["▽", "\\triangledown"], ["★", "\\bigstar"], ["♮", "\\natural"], ["♭", "\\flat"], ["♯", "\\sharp"],
      ["ℏ", "\\hbar"], ["ℓ", "\\ell"], ["ℜ", "\\Re"], ["ℑ", "\\Im"], ["℘", "\\wp"], ["∠", "\\angle"], ["°", "^\\circ"],
    ],
  },
];

let mathfield = null;
let locale = "zh";
let mode = "insert";
let pendingInit = null;

const host = document.getElementById("mathfieldHost");
const latexSource = document.getElementById("latexSource");
const statusText = document.getElementById("statusText");
const cancelButton = document.getElementById("cancelButton");
const acceptButton = document.getElementById("acceptButton");
const tabs = document.getElementById("libraryTabs");
const title = document.getElementById("libraryTitle");
const grid = document.getElementById("symbolGrid");

function strings() {
  return locale.startsWith("zh") ? STRINGS.zh : STRINGS.en;
}

function displayLabel(item) {
  if (locale.startsWith("zh")) {
    return item[0];
  }

  return item[2] || item[0];
}

function groupTitle(group) {
  return strings().tabs[group.id] || group.id;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function setStatus(text) {
  statusText.textContent = text || "";
}

function currentLatex() {
  return mathfield?.getValue("latex-expanded")?.trim() || "";
}

function syncSource() {
  latexSource.value = currentLatex();
}

function setLatex(latex) {
  mathfield.setValue(latex || "", { silenceNotifications: true });
  syncSource();
}

function insertLatex(latex) {
  if (latex.startsWith("matrix:")) {
    insertMatrix(latex.slice("matrix:".length));
    return;
  }

  mathfield.insert(latex, { format: "latex" });
  mathfield.focus();
  syncSource();
}

function insertMatrix(env, rows = 2, cols = 2) {
  if (env === "cases") {
    cols = 2;
  }

  const body = Array.from({ length: rows }, () => Array.from({ length: cols }, () => "#?").join(" & ")).join(" \\\\ ");
  mathfield.insert(`\\begin{${env}} ${body} \\end{${env}}`, { format: "latex" });
  mathfield.focus();
  syncSource();
}

function selectGroup(group) {
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.group === group.id);
  }

  title.textContent = groupTitle(group);
  grid.className = group.structures ? "symbol-grid structures" : "symbol-grid";
  grid.replaceChildren();
  for (const item of group.items) {
    if (group.structures && String(item[1]).startsWith("matrix:")) {
      grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
      continue;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = displayLabel(item);
    button.title = item[2] ? `${item[2]}\n${item[1]}` : item[1];
    button.addEventListener("click", () => insertLatex(item[1]));
    grid.appendChild(button);
  }
}

function createMatrixControl(label, env) {
  const isCases = env === "cases";
  const row = document.createElement("div");
  row.className = isCases ? "matrix-row cases" : "matrix-row";

  const rowSelect = document.createElement("select");
  rowSelect.title = strings().rows;
  for (let i = 1; i <= 10; i++) {
    rowSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
  }
  row.appendChild(rowSelect);

  let colSelect = null;
  if (!isCases) {
    colSelect = document.createElement("select");
    colSelect.title = strings().columns;
    for (let i = 1; i <= 10; i++) {
      colSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
    }
    row.appendChild(colSelect);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.title = `\\begin{${env}}...\\end{${env}}`;
  button.addEventListener("click", () => {
    insertMatrix(env, Number(rowSelect.value), colSelect ? Number(colSelect.value) : 2);
  });
  row.appendChild(button);
  return row;
}

function buildLibrary() {
  tabs.replaceChildren();
  for (const group of GROUPS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab";
    button.dataset.group = group.id;
    button.textContent = groupTitle(group);
    button.title = groupTitle(group);
    button.addEventListener("click", () => selectGroup(group));
    tabs.appendChild(button);
  }

  selectGroup(GROUPS[0]);
}

function accept() {
  const latex = currentLatex();
  if (!latex) {
    setStatus(strings().latexRequired);
    return;
  }

  send({ type: "accept", latex, display: true });
}

function configureText() {
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  cancelButton.textContent = strings().cancel;
  acceptButton.textContent = mode === "update" ? strings().acceptUpdate : strings().acceptInsert;
  setStatus(strings().ready);
  buildLibrary();
}

function applyInit(payload) {
  locale = String(payload?.locale || "zh").toLowerCase();
  mode = payload?.mode === "update" ? "update" : "insert";
  configureText();
  setLatex(payload?.latex || "");
  mathfield?.focus();
}

async function bootstrap() {
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", window.location.href).href;
  mathfield = new MathfieldElement();
  mathfield.smartFence = true;
  mathfield.smartMode = false;
  mathfield.mathVirtualKeyboardPolicy = "onfocus";
  mathfield.defaultMode = "math";
  host.appendChild(mathfield);
  mathfield.addEventListener("input", syncSource);
  latexSource.addEventListener("input", () => {
    mathfield.setValue(latexSource.value || "", { silenceNotifications: true });
    mathfield.focus();
  });
  cancelButton.addEventListener("click", () => send({ type: "cancel" }));
  acceptButton.addEventListener("click", accept);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      send({ type: "cancel" });
    }
  });
  configureText();
  if (pendingInit || window.__latexSnipperPendingInit) {
    applyInit(pendingInit || window.__latexSnipperPendingInit);
    pendingInit = null;
    window.__latexSnipperPendingInit = null;
  }
  mathfield.focus();
}

window.LaTeXSnipperEditor = {
  init(payload) {
    pendingInit = payload;
    if (mathfield) {
      applyInit(payload);
      pendingInit = null;
    }
  },
};

bootstrap().catch((error) => setStatus(String(error)));
