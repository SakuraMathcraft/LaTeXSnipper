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
    fontStyleLabel: "默认字体",
    fontScaleLabel: "公式大小",
    fontTeX: "TeX 原生字体",
    fontRomanUpright: "罗马正体",
    fontBold: "粗体",
    fontItalic: "斜体",
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
    fontStyleLabel: "Default font",
    fontScaleLabel: "Formula size",
    fontTeX: "Native TeX",
    fontRomanUpright: "Roman Upright",
    fontBold: "Bold",
    fontItalic: "Italic",
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
let formulaFontStyle = "TeX";
let formulaFontScale = 1;

const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const formulaColorInput = document.getElementById("formulaColor");
const resetFormulaColorButton = document.getElementById("resetFormulaColor");
const formulaFontStyleSelect = document.getElementById("formulaFontStyle");
const formulaFontScaleInput = document.getElementById("formulaFontScale");
const formulaFontScaleValue = document.getElementById("formulaFontScaleValue");

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
  formulaFontStyleSelect.value = formulaFontStyle;
  formulaFontScaleInput.value = String(scaleToPercent(formulaFontScale));
  formulaFontScaleValue.textContent = `+${scaleToPercent(formulaFontScale)}%`;
}

function save() {
  send({ type: "save", insertionBackend, formulaColor, formulaFontStyle, formulaFontScale });
}

function clampScale(scale) {
  const value = Number(scale);
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(1.5, Math.max(1, value));
}

function scaleToPercent(scale) {
  return Math.round((clampScale(scale) - 1) * 200);
}

function percentToScale(percent) {
  const value = Number(percent);
  const safePercent = Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 0;
  return 1 + safePercent / 200;
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  insertionBackend = payload?.insertionBackend === "PowerPointPng"
    ? "PowerPointPng"
    : "Ole";
  formulaColor = payload?.formulaColor || "#000000";
  formulaFontStyle = payload?.formulaFontStyle || "TeX";
  formulaFontScale = clampScale(payload?.formulaFontScale);
  applyText();
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

formulaFontStyleSelect.addEventListener("change", () => {
  formulaFontStyle = formulaFontStyleSelect.value;
  save();
});

formulaFontScaleInput.addEventListener("input", () => {
  formulaFontScale = percentToScale(formulaFontScaleInput.value);
  formulaFontScaleValue.textContent = `+${scaleToPercent(formulaFontScale)}%`;
});

formulaFontScaleInput.addEventListener("change", () => {
  formulaFontScale = percentToScale(formulaFontScaleInput.value);
  save();
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, insertionBackend, formulaColor, formulaFontStyle, formulaFontScale });
}
