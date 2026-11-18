import {populateTypographyOptions} from 'https://latexsnipper-editor-shared.officeplugin.local/settings-typography.mjs';

const TEXT = {
  zh: {
    title: "LaTeXSnipper PowerPoint 插件设置",
    backendTitle: "公式插入方式",
    backendHint: "选择 MathType 时，双击原生 MathType 公式会打开 LaTeXSnipper 编辑器。",
    backendOle: "OLE 对象",
    backendPng: "PNG 图片",
    backendMathType: "MathType",
    formulaDefaultsTitle: "公式默认属性",
    formulaDefaultsHint: "这些设置应用于新插入公式和格式化命令。",
    colorLabel: "字体颜色",
    resetColor: "恢复黑色",
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
    title: "LaTeXSnipper PowerPoint Plugin Settings",
    backendTitle: "Formula Insertion",
    backendHint: "Select MathType to open native MathType equations in LaTeXSnipper when double-clicked.",
    backendOle: "OLE Object",
    backendPng: "PNG Image",
    backendMathType: "MathType",
    formulaDefaultsTitle: "Default Formula Properties",
    formulaDefaultsHint: "These settings apply to new formulas and formatting commands.",
    colorLabel: "Font color",
    resetColor: "Reset to black",
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
let insertionBackend = "Ole";
let formulaColor = "#000000";
let formulaMathStyle = "Automatic";
let formulaFontSizePoints = 12;
let followHostFontSize = false;
let symbolFontId = "mathjax-tex";
let numberFontFamily = "";
let cjkFontFamily = "Microsoft YaHei";
const followHostFontSizeInput = document.getElementById("followHostFontSize");
followHostFontSizeInput.addEventListener("change", () => { followHostFontSize = followHostFontSizeInput.checked; save(); });

const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
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

function applyText() {
  const dict = strings();
  document.title = dict.title;
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = dict[node.dataset.i18n] || node.textContent;
  });
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function render() {
  backendButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.backend === insertionBackend);
  });
  formulaColorInput.value = formulaColor;
  formulaMathStyleSelect.value = formulaMathStyle;
  followHostFontSizeInput.checked = followHostFontSize;
  formulaFontSizePointsInput.value = String(formulaFontSizePoints);
  symbolFontInput.value = symbolFontId;
  numberFontInput.value = numberFontFamily;
  cjkFontInput.value = cjkFontFamily;
}

function save() {
  send({ type: "save", insertionBackend, formulaColor, formulaMathStyle, formulaFontSizePoints, followHostFontSize,
    symbolFontId, numberFontFamily, cjkFontFamily });
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  insertionBackend = ["PowerPointPng", "MathType"].includes(payload?.insertionBackend)
    ? payload.insertionBackend
    : "Ole";
  formulaColor = payload?.formulaColor || "#000000";
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
  render();
}

backendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    insertionBackend = button.dataset.backend;
    render();
    save();
  });
});

formulaColorInput.addEventListener("change", () => {
  formulaColor = formulaColorInput.value;
  save();
});

resetFormulaColorButton.addEventListener("click", () => {
  formulaColor = "#000000";
  render();
  save();
});

formulaMathStyleSelect.addEventListener("change", () => {
  formulaMathStyle = formulaMathStyleSelect.value;
  save();
});

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
