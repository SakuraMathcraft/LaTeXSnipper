const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    backendTitle: "公式插入方式",
    backendHint: "默认使用 OLE 公式对象，也可切换为 PNG 图片。",
    backendOle: "OLE 对象",
    backendPng: "PNG 图片",
    formulaDefaultsTitle: "公式默认属性",
    formulaDefaultsHint: "这些设置应用于新插入公式和格式化命令。",
    colorLabel: "字体颜色",
    resetColor: "恢复黑色",
    fontStyleLabel: "默认字形",
    fontSizeLabel: "公式字号（pt）",
    symbolFontLabel: "符号字体",
    numberFontLabel: "数字字体",
    cjkFontLabel: "汉字字体",
    followSymbolFont: "跟随符号字体",
    presetTitle: "全局公式预设",
    presetHint: "导入会替换当前宿主的公式默认属性；导出时用 JSON 文件名命名预设。编辑器内调整只作用于当前公式。",
    importPreset: "导入 JSON",
    exportPreset: "导出 JSON",
    importedPreset: "已导入：",
    exportedPreset: "已导出：",
    followHostSize: "新建时跟随文字字号（无有效选区时使用上述字号）",
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
    backendHint: "OLE formula objects are the default. PNG image insertion is also available.",
    backendOle: "OLE Object",
    backendPng: "PNG Image",
    formulaDefaultsTitle: "Default Formula Properties",
    formulaDefaultsHint: "These settings apply to new formulas and formatting commands.",
    colorLabel: "Font color",
    resetColor: "Reset to black",
    fontStyleLabel: "Default math style",
    fontSizeLabel: "Formula size (pt)",
    symbolFontLabel: "Symbol font",
    numberFontLabel: "Number font",
    cjkFontLabel: "CJK font",
    followSymbolFont: "Follow symbol font",
    presetTitle: "Global formula preset",
    presetHint: "Import replaces this host's formula defaults. The JSON filename names the preset. Editor changes apply to the current formula.",
    importPreset: "Import JSON",
    exportPreset: "Export JSON",
    importedPreset: "Imported: ",
    exportedPreset: "Exported: ",
    followHostSize: "Follow text size for new formulas (use the size above when unavailable)",
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

function populateFonts(payload) {
  const setOptions = (select, values, selected) => {
    select.replaceChildren();
    for (const value of [...new Set([...values, selected])]) {
      if (value === undefined || value === null) continue;
      select.add(new Option(value || strings().followSymbolFont, value));
    }
    select.value = selected;
  };
  setOptions(symbolFontInput, payload.symbolFonts, symbolFontId);
  setOptions(numberFontInput, ["", ...payload.systemFonts], numberFontFamily);
  setOptions(cjkFontInput, payload.cjkFonts, cjkFontFamily);
}

function populateMathStyles(styles) {
  formulaMathStyleSelect.replaceChildren();
  for (const style of styles) {
    formulaMathStyleSelect.add(new Option(locale.startsWith("zh") ? style.zh : style.en, style.id));
  }
}

function populateFontSizes(payload) {
  formulaFontSizePointsInput.replaceChildren();
  for (const size of payload.namedSizes) {
    formulaFontSizePointsInput.add(new Option(size.name, String(size.points)));
  }
  for (const points of payload.commonPointSizes) {
    formulaFontSizePointsInput.add(new Option(String(points), String(points)));
  }
  if (![...formulaFontSizePointsInput.options].some((option) => Number(option.value) === formulaFontSizePoints)) {
    formulaFontSizePointsInput.add(new Option(String(formulaFontSizePoints), String(formulaFontSizePoints)));
  }
}

function strings() {
  return locale.startsWith("zh") ? TEXT.zh : TEXT.en;
}

function applyText() {
  const dict = strings();
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
  insertionBackend = payload?.insertionBackend === "PowerPointPng"
    ? "PowerPointPng"
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
  populateFontSizes(payload);
  applyText();
  populateMathStyles(payload.mathStyles);
  populateFonts(payload);
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
