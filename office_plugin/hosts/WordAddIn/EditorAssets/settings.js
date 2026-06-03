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
    formatSectionArabic: "1.1",
    formatLowerRoman: "i",
    formatUpperRoman: "I",
    formatLowerLetter: "a",
    formatUpperLetter: "A",
    enclosureLabel: "外框",
    enclosureNone: "无",
    editorTitle: "编辑器键盘行为",
    acceptShortcut: "插入或更新当前公式",
    newlineShortcut: "在公式编辑器中换行",
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
    formatSectionArabic: "1.1",
    formatLowerRoman: "i",
    formatUpperRoman: "I",
    formatLowerLetter: "a",
    formatUpperLetter: "A",
    enclosureLabel: "Enclosure",
    enclosureNone: "None",
    editorTitle: "Editor Keyboard Behavior",
    acceptShortcut: "insert or update the current formula",
    newlineShortcut: "insert a line break in the formula editor",
    cancelShortcut: "hide the MathLive virtual keyboard",
  },
};

let locale = "zh";
let platform = "word";
let numberPlacement = "Right";
let insertionBackend = "Ole";
let numberFormat = "Arabic";
let numberEnclosure = "Parentheses";

const numberingPanel = document.getElementById("numberingPanel");
const buttons = Array.from(document.querySelectorAll("[data-placement]"));
const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const numberFormatSelect = document.getElementById("numberFormat");
const numberEnclosureSelect = document.getElementById("numberEnclosure");

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
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  platform = payload?.platform || "word";
  numberPlacement = payload?.numberPlacement === "Left" ? "Left" : "Right";
  insertionBackend = payload?.insertionBackend === "WordOmml" ? "WordOmml" : "Ole";
  numberFormat = ["Arabic", "SectionArabic", "LowerRoman", "UpperRoman", "LowerLetter", "UpperLetter"].includes(payload?.numberFormat)
    ? payload.numberFormat
    : "Arabic";
  numberEnclosure = ["Parentheses", "SquareBrackets", "Braces", "None"].includes(payload?.numberEnclosure)
    ? payload.numberEnclosure
    : "Parentheses";
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
    send({ type: "save", numberPlacement, insertionBackend, numberFormat, numberEnclosure });
  });
});

backendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    insertionBackend = button.dataset.backend;
    renderBackend();
    send({ type: "save", numberPlacement, insertionBackend, numberFormat, numberEnclosure });
  });
});

numberFormatSelect.addEventListener("change", () => {
  numberFormat = numberFormatSelect.value;
  send({ type: "save", numberPlacement, insertionBackend, numberFormat, numberEnclosure });
});

numberEnclosureSelect.addEventListener("change", () => {
  numberEnclosure = numberEnclosureSelect.value;
  send({ type: "save", numberPlacement, insertionBackend, numberFormat, numberEnclosure });
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, numberPlacement, insertionBackend, numberFormat, numberEnclosure });
}
