const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    backendTitle: "公式插入方式",
    backendHint: "默认使用 OLE 公式对象；也可切换为 Word OMML。",
    backendOle: "OLE 对象",
    backendOmml: "Word OMML",
    numberingTitle: "带编号公式默认布局",
    numberRight: "右编号",
    numberLeft: "左编号",
    numberingHint: "此设置只影响新插入的编号公式，以及之后被自动编号的普通公式。",
    enclosureLabel: "外框",
    enclosureNone: "无",
    includeChapter: "包含章编号",
    includeSection: "包含节编号",
    hideChapterBoundary: "隐藏章分隔符",
    hideSectionBoundary: "隐藏节分隔符",
    separatorLabel: "层级分隔符",
    formulaDefaultsTitle: "公式默认属性",
    formulaDefaultsHint: "这些设置应用于新插入公式和格式化命令。",
    colorLabel: "字体颜色",
    resetToBlack: "恢复黑色",
    resetToWhite: "恢复白色",
    fontStyleLabel: "默认数学样式",
    fontSizeLabel: "公式字号（pt）",
    followHostSize: "新建时跟随文字字号（无有效选区时使用上述字号）",
    fontTeX: "自动数学样式",
    fontRomanUpright: "罗马正体",
    fontBold: "粗体符号",
    fontBoldItalic: "粗斜体",
    fontItalic: "斜体",
    fontSansSerif: "无衬线",
    fontSansSerifBold: "无衬线粗体",
    fontSansSerifItalic: "无衬线斜体",
    fontSansSerifBoldItalic: "无衬线粗斜体",
    fontTypewriter: "等宽",
    fontCalligraphic: "花体",
    fontScript: "手写体",
    fontFraktur: "哥特体",
    fontBlackboard: "黑板粗体",
    editorTitle: "编辑器键盘行为",
    acceptShortcut: "插入或更新当前公式",
    newlineShortcut: "新建数学行",
    fractionShortcut: "插入分式",
    rootShortcut: "插入根号",
    superscriptShortcut: "插入上标",
    subscriptShortcut: "插入下标",
    scriptsShortcut: "插入上下标",
    cancelShortcut: "收回 MathLive 虚拟键盘",
  },
  en: {
    title: "LaTeXSnipper Office Plugin Settings",
    backendTitle: "Formula Insertion",
    backendHint: "OLE formula objects are the default. Word OMML insertion is also available.",
    backendOle: "OLE Object",
    backendOmml: "Word OMML",
    numberingTitle: "Default Numbered Formula Layout",
    numberRight: "Number on the right",
    numberLeft: "Number on the left",
    numberingHint: "This setting applies to newly inserted numbered formulas and ordinary formulas numbered later.",
    enclosureLabel: "Enclosure",
    enclosureNone: "None",
    includeChapter: "Include chapter number",
    includeSection: "Include section number",
    hideChapterBoundary: "Hide chapter boundaries",
    hideSectionBoundary: "Hide section boundaries",
    separatorLabel: "Level separator",
    formulaDefaultsTitle: "Default Formula Properties",
    formulaDefaultsHint: "These settings apply to new formulas and formatting commands.",
    colorLabel: "Font color",
    resetToBlack: "Reset to black",
    resetToWhite: "Reset to white",
    fontStyleLabel: "Default math style",
    fontSizeLabel: "Formula size (pt)",
    followHostSize: "Follow text size for new formulas (use the size above when unavailable)",
    fontTeX: "Automatic",
    fontRomanUpright: "Roman Upright",
    fontBold: "Bold Symbol",
    fontBoldItalic: "Bold Italic",
    fontItalic: "Italic",
    fontSansSerif: "Sans Serif",
    fontSansSerifBold: "Sans Serif Bold",
    fontSansSerifItalic: "Sans Serif Italic",
    fontSansSerifBoldItalic: "Sans Serif Bold Italic",
    fontTypewriter: "Monospace",
    fontCalligraphic: "Calligraphic",
    fontScript: "Script",
    fontFraktur: "Fraktur",
    fontBlackboard: "Blackboard Bold",
    editorTitle: "Editor Keyboard Behavior",
    acceptShortcut: "insert or update the current formula",
    newlineShortcut: "start a new math row",
    fractionShortcut: "insert a fraction",
    rootShortcut: "insert a square root",
    superscriptShortcut: "insert a superscript",
    subscriptShortcut: "insert a subscript",
    scriptsShortcut: "insert superscript and subscript",
    cancelShortcut: "hide the MathLive virtual keyboard",
  },
};
const FONT_STYLE_VALUES = Object.freeze([
  "Automatic",
  "Upright",
  "Bold",
  "BoldItalic",
  "Italic",
  "SansSerif",
  "SansSerifBold",
  "SansSerifItalic",
  "SansSerifBoldItalic",
  "Monospace",
  "Calligraphic",
  "Script",
  "Fraktur",
  "Blackboard",
]);

let locale = "zh";
let platform = "word";
let numberPlacement = "Right";
let insertionBackend = "Ole";
let numberEnclosure = "Parentheses";
let includeChapter = false;
let includeSection = false;
let hideChapterBoundary = false;
let hideSectionBoundary = false;
let numberSeparator = "-";
let formulaColor = "#000000";
let defaultFormulaColor = "#000000";
let useSystemFormulaColor = true;
let formulaMathStyle = "Automatic";
let formulaFontSizePoints = 12;
let followHostFontSize = false;
const followHostFontSizeInput = document.getElementById("followHostFontSize");
followHostFontSizeInput.addEventListener("change", () => { followHostFontSize = followHostFontSizeInput.checked; save(); });

const numberingPanel = document.getElementById("numberingPanel");
const buttons = Array.from(document.querySelectorAll("[data-placement]"));
const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const numberEnclosureSelect = document.getElementById("numberEnclosure");
const includeChapterInput = document.getElementById("includeChapter");
const includeSectionInput = document.getElementById("includeSection");
const hideChapterBoundaryInput = document.getElementById("hideChapterBoundary");
const hideSectionBoundaryInput = document.getElementById("hideSectionBoundary");
const numberSeparatorInput = document.getElementById("numberSeparator");
const formulaColorInput = document.getElementById("formulaColor");
const resetFormulaColorButton = document.getElementById("resetFormulaColor");
const formulaMathStyleSelect = document.getElementById("formulaMathStyle");
const formulaFontSizePointsInput = document.getElementById("formulaFontSizePoints");
const formulaFontSizePointsValue = document.getElementById("formulaFontSizePointsValue");

function strings() {
  return locale.startsWith("zh") ? TEXT.zh : TEXT.en;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function applyText() {
  const dict = strings();
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = dict[node.dataset.i18n] || node.textContent;
  });
}

function applyPlatform() {
  const isWord = platform === "word";
  numberingPanel.style.display = isWord ? "" : "none";
}

function renderPlacement() {
  buttons.forEach((button) => {
    button.classList.toggle("active", button.dataset.placement === numberPlacement);
  });
}

function renderBackend() {
  backendButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.backend === insertionBackend);
  });
}

function renderNumberOptions() {
  numberEnclosureSelect.value = numberEnclosure;
  includeChapterInput.checked = includeChapter;
  includeSectionInput.checked = includeSection;
  hideChapterBoundaryInput.checked = hideChapterBoundary;
  hideSectionBoundaryInput.checked = hideSectionBoundary;
  numberSeparatorInput.value = numberSeparator;
  formulaColorInput.value = formulaColor;
  resetFormulaColorButton.textContent = defaultFormulaColor === "#FFFFFF"
    ? strings().resetToWhite
    : strings().resetToBlack;
  formulaMathStyleSelect.value = formulaMathStyle;
  followHostFontSizeInput.checked = followHostFontSize;
  formulaFontSizePointsInput.value = String(formulaFontSizePoints);
  formulaFontSizePointsValue.textContent = "pt";
}

function save() {
  send({
    type: "save",
    numberPlacement,
    insertionBackend,
    numberEnclosure,
    includeChapter,
    includeSection,
    hideChapterBoundary,
    hideSectionBoundary,
    numberSeparator,
    formulaColor,
    useSystemFormulaColor,
    formulaMathStyle,
    formulaFontSizePoints,
    followHostFontSize,
  });
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  platform = payload?.platform || "word";
  numberPlacement = payload?.numberPlacement === "Left" ? "Left" : "Right";
  insertionBackend = payload?.insertionBackend === "WordOmml" ? "WordOmml" : "Ole";
  numberEnclosure = ["Parentheses", "SquareBrackets", "Braces", "None"].includes(payload?.numberEnclosure)
    ? payload.numberEnclosure
    : "Parentheses";
  includeChapter = Boolean(payload?.includeChapter);
  includeSection = Boolean(payload?.includeSection);
  hideChapterBoundary = Boolean(payload?.hideChapterBoundary);
  hideSectionBoundary = Boolean(payload?.hideSectionBoundary);
  numberSeparator = ["-", ".", "·", ":", "/"].includes(payload?.numberSeparator)
    ? payload.numberSeparator
    : "-";
  defaultFormulaColor = String(payload?.defaultFormulaColor || "#000000").toUpperCase();
  useSystemFormulaColor = payload?.useSystemFormulaColor !== false;
  formulaColor = useSystemFormulaColor
    ? defaultFormulaColor
    : String(payload?.formulaColor || defaultFormulaColor).toUpperCase();
  formulaMathStyle = FONT_STYLE_VALUES.includes(payload?.formulaMathStyle)
    ? payload.formulaMathStyle
    : "Automatic";
  formulaFontSizePoints = Number(payload?.formulaFontSizePoints ?? 12);
  followHostFontSize = Boolean(payload?.followHostFontSize);
  applyText();
  applyPlatform();
  renderPlacement();
  renderBackend();
  renderNumberOptions();
}

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    numberPlacement = button.dataset.placement;
    renderPlacement();
    save();
  });
});

backendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    insertionBackend = button.dataset.backend;
    renderBackend();
    save();
  });
});

numberEnclosureSelect.addEventListener("change", () => {
  numberEnclosure = numberEnclosureSelect.value;
  save();
});

includeChapterInput.addEventListener("change", () => { includeChapter = includeChapterInput.checked; save(); });
includeSectionInput.addEventListener("change", () => { includeSection = includeSectionInput.checked; save(); });
hideChapterBoundaryInput.addEventListener("change", () => { hideChapterBoundary = hideChapterBoundaryInput.checked; save(); });
hideSectionBoundaryInput.addEventListener("change", () => { hideSectionBoundary = hideSectionBoundaryInput.checked; save(); });
numberSeparatorInput.addEventListener("change", () => { numberSeparator = numberSeparatorInput.value || "-"; save(); });
formulaColorInput.addEventListener("change", () => {
  formulaColor = formulaColorInput.value.toUpperCase();
  useSystemFormulaColor = false;
  save();
});
resetFormulaColorButton.addEventListener("click", () => {
  formulaColor = defaultFormulaColor;
  useSystemFormulaColor = true;
  formulaColorInput.value = formulaColor;
  save();
});
formulaMathStyleSelect.addEventListener("change", () => { formulaMathStyle = formulaMathStyleSelect.value; save(); });
formulaFontSizePointsInput.addEventListener("change", () => {
  if (!formulaFontSizePointsInput.reportValidity()) return;
  formulaFontSizePoints = Number(formulaFontSizePointsInput.value);
  save();
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({
    locale: navigator.language,
    numberPlacement,
    insertionBackend,
    numberEnclosure,
    includeChapter,
    includeSection,
    hideChapterBoundary,
    hideSectionBoundary,
    numberSeparator,
    formulaColor,
    useSystemFormulaColor,
    formulaMathStyle,
    formulaFontSizePoints,
    followHostFontSize,
  });
}
