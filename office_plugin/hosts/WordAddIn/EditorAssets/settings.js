import {populateTypographyOptions} from 'https://latexsnipper-editor-shared.officeplugin.local/settings-typography.mjs';

const TEXT = {
  zh: {
    title: "LaTeXSnipper Word 插件设置",
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
    fontStyleLabel: "默认字形",
    fontSizeLabel: "公式字号",
    symbolFontLabel: "符号字体",
    numberFontLabel: "数字字体",
    cjkFontLabel: "汉字字体",
    presetTitle: "全局公式预设",
    presetHint: "导入会替换当前宿主的公式默认属性；导出时用 JSON 文件名命名预设。编辑器内调整只作用于当前公式。",
    importPreset: "导入 JSON",
    exportPreset: "导出 JSON",
    importedPreset: "已导入：",
    exportedPreset: "已导出：",
    followHostSize: "新建时跟随文字字号（无有效选区时使用上述字号）",
    editorTitle: "编辑器键盘行为",
    acceptShortcut: "插入或更新当前公式",
    fractionShortcut: "插入分式",
    rootShortcut: "插入根号",
    superscriptShortcut: "插入上标",
    subscriptShortcut: "插入下标",
    scriptsShortcut: "插入上下标",
  },
  en: {
    title: "LaTeXSnipper Word Plugin Settings",
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
    fontStyleLabel: "Default math style",
    fontSizeLabel: "Formula size",
    symbolFontLabel: "Symbol font",
    numberFontLabel: "Number font",
    cjkFontLabel: "CJK font",
    presetTitle: "Global formula preset",
    presetHint: "Import replaces this host's formula defaults. The JSON filename names the preset. Editor changes apply to the current formula.",
    importPreset: "Import JSON",
    exportPreset: "Export JSON",
    importedPreset: "Imported: ",
    exportedPreset: "Exported: ",
    followHostSize: "Follow text size for new formulas (use the size above when unavailable)",
    editorTitle: "Editor Keyboard Behavior",
    acceptShortcut: "insert or update the current formula",
    fractionShortcut: "insert a fraction",
    rootShortcut: "insert a square root",
    superscriptShortcut: "insert a superscript",
    subscriptShortcut: "insert a subscript",
    scriptsShortcut: "insert superscript and subscript",
  },
};


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
let formulaMathStyle = "Automatic";
let formulaFontSizePoints = 12;
let followHostFontSize = false;
let symbolFontId = "mathjax-tex";
let numberFontFamily = "";
let cjkFontFamily = "Microsoft YaHei";
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
const symbolFontInput = document.getElementById("symbolFontId");
const numberFontInput = document.getElementById("numberFontFamily");
const cjkFontInput = document.getElementById("cjkFontFamily");
const presetStatus = document.getElementById("presetStatus");

function strings() {
  return locale.startsWith("zh") ? TEXT.zh : TEXT.en;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function applyText() {
  const dict = strings();
  document.title = dict.title;
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
  resetFormulaColorButton.textContent = strings().resetToBlack;
  formulaMathStyleSelect.value = formulaMathStyle;
  followHostFontSizeInput.checked = followHostFontSize;
  formulaFontSizePointsInput.value = String(formulaFontSizePoints);
  symbolFontInput.value = symbolFontId;
  numberFontInput.value = numberFontFamily;
  cjkFontInput.value = cjkFontFamily;
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
    formulaMathStyle,
    formulaFontSizePoints,
    followHostFontSize,
    symbolFontId,
    numberFontFamily,
    cjkFontFamily,
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
  formulaColor = String(payload?.formulaColor || "#000000").toUpperCase();
  formulaMathStyle = payload.mathStyles.some(style => style.id === payload.formulaMathStyle)
    ? payload.formulaMathStyle
    : "Automatic";
  formulaFontSizePoints = Number(payload?.formulaFontSizePoints ?? 12);
  followHostFontSize = Boolean(payload?.followHostFontSize);
  symbolFontId = String(payload?.symbolFontId || "mathjax-tex");
  numberFontFamily = String(payload?.numberFontFamily || "");
  cjkFontFamily = String(payload?.cjkFontFamily || "Microsoft YaHei");
  applyText();
  populateTypographyOptions(payload, {symbolFontId, numberFontFamily, cjkFontFamily, formulaFontSizePoints}, locale);
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
  save();
});
resetFormulaColorButton.addEventListener("click", () => {
  formulaColor = "#000000";
  formulaColorInput.value = formulaColor;
  save();
});
formulaMathStyleSelect.addEventListener("change", () => { formulaMathStyle = formulaMathStyleSelect.value; save(); });
formulaFontSizePointsInput.addEventListener("change", () => {
  formulaFontSizePoints = Number(formulaFontSizePointsInput.value);
  save();
});
symbolFontInput.addEventListener("change", () => { symbolFontId = symbolFontInput.value; save(); });
numberFontInput.addEventListener("change", () => { numberFontFamily = numberFontInput.value; save(); });
cjkFontInput.addEventListener("change", () => { cjkFontFamily = cjkFontInput.value; save(); });
document.getElementById("importTypography").addEventListener("click", () => send({type: "importTypography"}));
document.getElementById("exportTypography").addEventListener("click", () => send({type: "exportTypography"}));
function presetResult(result) {
  presetStatus.textContent = result?.error || `${strings()[result?.kind === "import" ? "importedPreset" : "exportedPreset"]}${result?.name || ""}`;
  presetStatus.classList.toggle("error", Boolean(result?.error));
}

window.LaTeXSnipperSettings = { init, presetResult };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
}
