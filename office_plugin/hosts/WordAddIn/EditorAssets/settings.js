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
    formatLabel: "编号格式",
    formatArabic: "1",
    formatLowerRoman: "i",
    formatUpperRoman: "I",
    formatLowerLetter: "a",
    formatUpperLetter: "A",
    enclosureLabel: "外框",
    enclosureNone: "无",
    includeChapter: "包含章编号",
    includeSection: "包含节编号",
    hideChapterBoundary: "隐藏章分隔符",
    hideSectionBoundary: "隐藏节分隔符",
    separatorLabel: "层级分隔符",
    formulaDefaultsTitle: "公式默认属性",
    formulaDefaultsHint: "这些设置仅影响新插入的公式。",
    colorLabel: "字体颜色",
    resetToBlack: "恢复黑色",
    resetToWhite: "恢复白色",
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
    backendHint: "OLE formula objects are the default. Word OMML insertion is also available.",
    backendOle: "OLE Object",
    backendOmml: "Word OMML",
    numberingTitle: "Default Numbered Formula Layout",
    numberRight: "Number on the right",
    numberLeft: "Number on the left",
    numberingHint: "This setting applies to newly inserted numbered formulas and ordinary formulas numbered later.",
    formatLabel: "Number format",
    formatArabic: "1",
    formatLowerRoman: "i",
    formatUpperRoman: "I",
    formatLowerLetter: "a",
    formatUpperLetter: "A",
    enclosureLabel: "Enclosure",
    enclosureNone: "None",
    includeChapter: "Include chapter number",
    includeSection: "Include section number",
    hideChapterBoundary: "Hide chapter boundaries",
    hideSectionBoundary: "Hide section boundaries",
    separatorLabel: "Level separator",
    formulaDefaultsTitle: "Default Formula Properties",
    formulaDefaultsHint: "These settings apply only to newly inserted formulas.",
    colorLabel: "Font color",
    resetToBlack: "Reset to black",
    resetToWhite: "Reset to white",
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
let platform = "word";
let numberPlacement = "Right";
let insertionBackend = "Ole";
let numberFormat = "Arabic";
let numberEnclosure = "Parentheses";
let includeChapter = false;
let includeSection = false;
let hideChapterBoundary = false;
let hideSectionBoundary = false;
let numberSeparator = "-";
let formulaColor = "#000000";
let defaultFormulaColor = "#000000";
let useSystemFormulaColor = true;
let formulaFontStyle = "TeX";
let formulaFontScale = 1;

const numberingPanel = document.getElementById("numberingPanel");
const buttons = Array.from(document.querySelectorAll("[data-placement]"));
const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const numberFormatSelect = document.getElementById("numberFormat");
const numberEnclosureSelect = document.getElementById("numberEnclosure");
const includeChapterInput = document.getElementById("includeChapter");
const includeSectionInput = document.getElementById("includeSection");
const hideChapterBoundaryInput = document.getElementById("hideChapterBoundary");
const hideSectionBoundaryInput = document.getElementById("hideSectionBoundary");
const numberSeparatorInput = document.getElementById("numberSeparator");
const formulaColorInput = document.getElementById("formulaColor");
const resetFormulaColorButton = document.getElementById("resetFormulaColor");
const formulaFontStyleSelect = document.getElementById("formulaFontStyle");
const formulaFontScaleInput = document.getElementById("formulaFontScale");
const formulaFontScaleValue = document.getElementById("formulaFontScaleValue");

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
  numberFormatSelect.value = numberFormat;
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
  formulaFontStyleSelect.value = formulaFontStyle;
  formulaFontScaleInput.value = String(scaleToPercent(formulaFontScale));
  formulaFontScaleValue.textContent = `+${scaleToPercent(formulaFontScale)}%`;
}

function save() {
  send({
    type: "save",
    numberPlacement,
    insertionBackend,
    numberFormat,
    numberEnclosure,
    includeChapter,
    includeSection,
    hideChapterBoundary,
    hideSectionBoundary,
    numberSeparator,
    formulaColor,
    useSystemFormulaColor,
    formulaFontStyle,
    formulaFontScale,
  });
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
  platform = payload?.platform || "word";
  numberPlacement = payload?.numberPlacement === "Left" ? "Left" : "Right";
  insertionBackend = payload?.insertionBackend === "WordOmml" ? "WordOmml" : "Ole";
  numberFormat = ["Arabic", "LowerRoman", "UpperRoman", "LowerLetter", "UpperLetter"].includes(payload?.numberFormat)
    ? payload.numberFormat
    : "Arabic";
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
  formulaFontStyle = ["TeX", "RomanUpright", "Bold", "Italic"].includes(payload?.formulaFontStyle)
    ? payload.formulaFontStyle
    : "TeX";
  formulaFontScale = clampScale(payload?.formulaFontScale);
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

numberFormatSelect.addEventListener("change", () => {
  numberFormat = numberFormatSelect.value;
  save();
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
formulaFontStyleSelect.addEventListener("change", () => { formulaFontStyle = formulaFontStyleSelect.value; save(); });
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
  init({ locale: navigator.language, numberPlacement, insertionBackend, numberFormat, numberEnclosure, formulaFontScale });
}
