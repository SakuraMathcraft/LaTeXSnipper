const TEXT = {
  zh: {
    title: "LaTeXSnipper Office 插件设置",
    subtitle: "配置编号默认值，并查看已经落地到 Ribbon 的 KeyTip 快捷键。",
    numberingTitle: "带编号公式默认布局",
    numberRight: "右编号",
    numberLeft: "左编号",
    numberingHint: "此设置只影响之后新插入或重新渲染的带编号公式。",
    keytipsTitle: "Ribbon KeyTip 快捷键",
    keytipsHint: "按 Alt 显示 Office KeyTip，然后依次按下表键位。所有主要 Ribbon 操作已在插件中设置真实 KeyTip。",
    inlineTitle: "行内公式",
    inlineDesc: "插入当前侧边栏 LaTeX 为正文行内公式。",
    displayTitle: "行间公式",
    displayDesc: "插入当前侧边栏 LaTeX 为居中行间公式。",
    numberedTitle: "带编号公式",
    numberedDesc: "插入当前侧边栏 LaTeX 为自动编号行间公式。",
    ocrTitle: "截图识别",
    ocrDesc: "等待下一次全局快捷键截图；再次触发可取消。",
    loadTitle: "加载所选",
    loadDesc: "加载选中的受管理公式。",
    deleteTitle: "删除所选",
    deleteDesc: "删除选中的受管理公式及元数据。",
    autoTitle: "自动编号",
    autoDesc: "为选中公式添加自动编号。",
    renumberTitle: "重编号",
    renumberDesc: "按文档顺序更新所有自动编号公式。",
    paneTitle: "状态窗格",
    paneDesc: "显示 LaTeXSnipper 侧边栏。",
    settingsTitle: "设置",
    settingsDesc: "打开此设置窗口。",
    helpTitle: "帮助",
    helpDesc: "打开插件帮助页。",
    editorTitle: "编辑器键盘行为",
    newlineShortcut: "在公式编辑器中换行",
    cancelShortcut: "关闭编辑器，不应用更改",
    ready: "就绪",
    saved: "已保存",
    close: "关闭",
  },
  en: {
    title: "LaTeXSnipper Office Plugin Settings",
    subtitle: "Configure numbering defaults and review real Ribbon KeyTip shortcuts.",
    numberingTitle: "Default Numbered Formula Layout",
    numberRight: "Number on the right",
    numberLeft: "Number on the left",
    numberingHint: "This setting applies to newly inserted or re-rendered numbered formulas.",
    keytipsTitle: "Ribbon KeyTip Shortcuts",
    keytipsHint: "Press Alt to show Office KeyTips, then press the keys shown below. All main Ribbon commands have real plugin KeyTips.",
    inlineTitle: "Inline Formula",
    inlineDesc: "Insert the side pane LaTeX as an inline equation.",
    displayTitle: "Display Formula",
    displayDesc: "Insert the side pane LaTeX as a centered display equation.",
    numberedTitle: "Numbered Formula",
    numberedDesc: "Insert the side pane LaTeX as an automatically numbered display equation.",
    ocrTitle: "Screenshot OCR",
    ocrDesc: "Wait for the next global-hotkey capture; trigger again to cancel.",
    loadTitle: "Load Selected",
    loadDesc: "Load the selected managed formula.",
    deleteTitle: "Delete Selected",
    deleteDesc: "Delete the selected managed formula and metadata.",
    autoTitle: "Auto Number",
    autoDesc: "Add automatic numbering to the selected formula.",
    renumberTitle: "Renumber",
    renumberDesc: "Update all automatic numbers in document order.",
    paneTitle: "Status Pane",
    paneDesc: "Show the LaTeXSnipper side pane.",
    settingsTitle: "Settings",
    settingsDesc: "Open this settings window.",
    helpTitle: "Help",
    helpDesc: "Open plugin help.",
    editorTitle: "Editor Keyboard Behavior",
    newlineShortcut: "insert a line break in the formula editor",
    cancelShortcut: "close the editor without applying changes",
    ready: "Ready",
    saved: "Saved",
    close: "Close",
  },
};

let locale = "zh";
let numberPlacement = "Right";

const statusText = document.getElementById("statusText");
const buttons = Array.from(document.querySelectorAll("[data-placement]"));

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

function renderPlacement() {
  buttons.forEach((button) => {
    button.classList.toggle("active", button.dataset.placement === numberPlacement);
  });
}

function init(payload) {
  locale = String(payload?.locale || navigator.language || "zh").toLowerCase();
  numberPlacement = payload?.numberPlacement === "Left" ? "Left" : "Right";
  applyText();
  renderPlacement();
}

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    numberPlacement = button.dataset.placement;
    renderPlacement();
    send({ type: "save", numberPlacement });
    statusText.textContent = strings().saved;
  });
});

document.getElementById("closeButton").addEventListener("click", () => send({ type: "close" }));

window.LaTeXSnipperSettings = { init };
if (window.__latexSnipperSettingsInit) {
  init(window.__latexSnipperSettingsInit);
  window.__latexSnipperSettingsInit = null;
} else {
  init({ locale: navigator.language, numberPlacement });
}
