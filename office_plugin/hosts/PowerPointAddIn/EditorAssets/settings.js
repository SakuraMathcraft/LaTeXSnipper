const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    subtitle: "配置公式插入方式和编辑器键盘行为。",
    backendTitle: "公式插入方式",
    backendHint: "默认使用 OLE 公式对象；需要兼容旧演示文稿时可切换为旧 PNG 方式。",
    backendOle: "OLE 对象",
    backendLegacy: "旧 PNG",
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
    editorTitle: "Editor Keyboard Behavior",
    newlineShortcut: "insert a line break in the formula editor",
    cancelShortcut: "close the editor without applying changes",
  },
};

let locale = "zh";
let insertionBackend = "Ole";

const backendButtons = Array.from(document.querySelectorAll("[data-backend]"));

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

function renderBackend() {
  backendButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.backend === insertionBackend);
  });
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  insertionBackend = payload?.insertionBackend === "PowerPointCompatibility" ? "PowerPointCompatibility" : "Ole";
  applyText();
  renderBackend();
}

backendButtons.forEach((button) => {
  button.addEventListener("click", () => {
    insertionBackend = button.dataset.backend;
    renderBackend();
    send({ type: "save", insertionBackend });
  });
});

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, insertionBackend });
}
