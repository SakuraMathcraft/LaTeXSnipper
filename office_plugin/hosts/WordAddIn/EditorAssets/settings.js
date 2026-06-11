const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    subtitle: "配置公式插入方式和编号默认值。",
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
    separatorLabel: "层级分隔符",
    formattingTitle: "公式格式化",
    formattingHint: "“格式化”选项卡将这些值应用于所选公式或全文公式。",
    colorLabel: "字体颜色",
    fontStyleLabel: "默认字体",
    fontRomanUpright: "罗马正体",
    fontBold: "粗体",
    fontItalic: "斜体",
    weightLabel: "粗细度",
    scaleLabel: "大小倍率",
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
    subtitle: "Configure formula insertion and numbering defaults.",
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
    separatorLabel: "Level separator",
    formattingTitle: "Formula Formatting",
    formattingHint: "The Formatting tab applies these values to selected formulas or all formulas.",
    colorLabel: "Font color",
    fontStyleLabel: "Default font",
    fontRomanUpright: "Roman Upright",
    fontBold: "Bold",
    fontItalic: "Italic",
    weightLabel: "Weight",
    scaleLabel: "Size scale",
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
let numberSeparator = ".";
let formulaColor = "#000000";
let formulaFontStyle = "Italic";
let formulaScale = 1;
let formulaWeightPercent = 0;

const numberingPanel = document.getElementById("numberingPanel");
const buttons = Array.from(document.querySelectorAll("[data-placement]"));
const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const numberFormatSelect = document.getElementById("numberFormat");
const numberEnclosureSelect = document.getElementById("numberEnclosure");
const includeChapterInput = document.getElementById("includeChapter");
const includeSectionInput = document.getElementById("includeSection");
const numberSeparatorInput = document.getElementById("numberSeparator");
const formulaColorInput = document.getElementById("formulaColor");
const formulaFontStyleSelect = document.getElementById("formulaFontStyle");
const formulaScaleInput = document.getElementById("formulaScale");
const formulaWeightPercentSelect = document.getElementById("formulaWeightPercent");

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
  numberSeparatorInput.value = numberSeparator;
  formulaColorInput.value = formulaColor;
  formulaFontStyleSelect.value = formulaFontStyle;
  formulaScaleInput.value = formulaScale;
  formulaWeightPercentSelect.value = String(formulaWeightPercent);
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
    numberSeparator,
    formulaColor,
    formulaFontStyle,
    formulaScale,
    formulaWeightPercent,
  });
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
  numberSeparator = String(payload?.numberSeparator || ".");
  formulaColor = String(payload?.formulaColor || "#000000");
  formulaFontStyle = ["RomanUpright", "Bold", "Italic"].includes(payload?.formulaFontStyle)
    ? payload.formulaFontStyle
    : "Italic";
  formulaScale = Math.max(0.5, Math.min(5, Number(payload?.formulaScale) || 1));
  formulaWeightPercent = [0, 5, 10, 15].includes(Number(payload?.formulaWeightPercent))
    ? Number(payload.formulaWeightPercent)
    : 0;
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
numberSeparatorInput.addEventListener("change", () => { numberSeparator = numberSeparatorInput.value || "."; save(); });
formulaColorInput.addEventListener("change", () => { formulaColor = formulaColorInput.value; save(); });
formulaFontStyleSelect.addEventListener("change", () => { formulaFontStyle = formulaFontStyleSelect.value; save(); });
formulaWeightPercentSelect.addEventListener("change", () => {
  formulaWeightPercent = Number(formulaWeightPercentSelect.value);
  save();
});
formulaScaleInput.addEventListener("change", () => {
  formulaScale = Math.max(0.5, Math.min(5, Number(formulaScaleInput.value) || 1));
  save();
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, numberPlacement, insertionBackend, numberFormat, numberEnclosure });
}
