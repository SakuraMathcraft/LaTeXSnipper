const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    subtitle: "配置公式插入方式和编辑器键盘行为。",
    backendTitle: "公式插入方式",
    backendHint: "默认使用 OLE 公式对象；需要兼容旧演示文稿时可切换为旧 PNG 方式。",
    backendOle: "OLE 对象",
    backendLegacy: "旧 PNG",
    oleScaleTitle: "OLE 公式缩放",
    oleScaleHint: "只影响新插入的 OLE 公式尺寸。",
    oleScaleRange: "范围：大于 0，且不超过 5。无效输入会恢复为当前有效倍率。",
    oleScaleInvalid: "OLE 公式缩放必须大于 0 且不超过 5。",
    editorTitle: "编辑器键盘行为",
    newlineShortcut: "在公式编辑器中换行",
    cancelShortcut: "关闭编辑器，不应用更改",
  },
  en: {
    title: "LaTeXSnipper Office Plugin Settings",
    subtitle: "Configure formula insertion and editor keyboard behavior.",
    backendTitle: "Formula Insertion",
    backendHint: "OLE formula objects are the default. Switch to legacy PNG only for compatibility.",
    backendOle: "OLE Object",
    backendLegacy: "Legacy PNG",
    oleScaleTitle: "OLE Formula Scale",
    oleScaleHint: "Applies only to newly inserted OLE formulas.",
    oleScaleRange: "Range: greater than 0 and no more than 5. Invalid input restores the current valid scale.",
    oleScaleInvalid: "OLE formula scale must be greater than 0 and no more than 5.",
    editorTitle: "Editor Keyboard Behavior",
    newlineShortcut: "insert a line break in the formula editor",
    cancelShortcut: "close the editor without applying changes",
  },
};

let locale = "zh";
let insertionBackend = "Ole";
let oleScale = 1;
const MIN_OLE_SCALE = 0;
const MAX_OLE_SCALE = 5;

const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));
const oleScaleInput = document.getElementById("oleScale");

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

function isValidOleScale(value) {
  return Number.isFinite(value) && value > MIN_OLE_SCALE && value <= MAX_OLE_SCALE;
}

function renderBackend() {
  backendButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.backend === insertionBackend);
  });
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  insertionBackend = payload?.insertionBackend === "PowerPointCompatibility" ? "PowerPointCompatibility" : "Ole";
  const loadedOleScale = Number(payload?.oleScale);
  oleScale = isValidOleScale(loadedOleScale) ? loadedOleScale : 1;
  oleScaleInput.value = String(oleScale);
  applyText();
  renderBackend();
}

backendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    insertionBackend = button.dataset.backend;
    renderBackend();
    send({ type: "save", insertionBackend, oleScale });
  });
});

oleScaleInput.addEventListener("change", () => {
  const value = Number(oleScaleInput.value);
  if (!isValidOleScale(value)) {
    window.alert(strings().oleScaleInvalid);
    oleScaleInput.value = String(oleScale);
    return;
  }

  oleScale = value;
  oleScaleInput.value = String(oleScale);
  send({ type: "save", insertionBackend, oleScale });
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, insertionBackend });
}
