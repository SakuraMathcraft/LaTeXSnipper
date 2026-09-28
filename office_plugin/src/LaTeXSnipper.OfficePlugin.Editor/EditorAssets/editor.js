import { MathfieldElement } from "./vendor/mathlive.min.mjs";
import { SourceEditor } from "./source-editor.bundle.js";
import { SourceSync, formatVisualLatex } from "./source-sync.mjs";

import {STRINGS, CATALOG, COMMANDS} from './template-catalog.mjs';
import {mountEditor} from './editor-layout.mjs';
import {SymbolPanel} from './symbol-panel.mjs';
import {TemplateInsertion} from './template-insertion.mjs';
import {configureMathfield, configureMathfieldMenu} from './mathfield-input.mjs';

import {DraftPreview} from './draft-preview.mjs';
import {TypographyPanel} from './typography-panel.mjs';
import {formulaColor, hasFormulaContent, initialFormulaColor, withFormulaColor} from './formula-color.mjs';

mountEditor();
let session = null;
let display = true;
let typographyPanel = null;
let preview = null;
let mathfield = null;
let locale = "zh";
let mode = "insert";
let submitting = false;
let pendingInit = null;
let symbolPanel = null;
let insertion = null;
let sourceEditor = null;
let sourceSync = null;
let bindMathfieldInput = null;
let initialFocusPending = false;
let caretVisibilityFrame = 0;
let sourcePaneHeight = 150;
let sourceResizePointerId = null;
let sourceResizeStartY = 0;
let sourceResizeStartHeight = 150;

const SOURCE_PANE_MIN_HEIGHT = 96;
const FORMULA_PANE_MIN_HEIGHT = 80;
const SOURCE_PANE_KEYBOARD_STEP = 16;

const workspace = document.querySelector(".workspace");
const host = document.getElementById("mathfieldHost");
const latexSource = document.getElementById("latexSource");
const sourceResizeHandle = document.getElementById("sourceResizeHandle");
const statusText = document.getElementById("statusText");
const cancelButton = document.getElementById("cancelButton");
const acceptButton = document.getElementById("acceptButton");

function strings() {
  return locale.startsWith("zh") ? STRINGS.zh : STRINGS.en;
}

function send(message) {
  window.chrome?.webview?.postMessage(message);
}

function setStatus(text) {
  statusText.textContent = text || "";
}

function setSubmitting(value) {
  submitting = Boolean(value);
  acceptButton.disabled = submitting;
  cancelButton.disabled = submitting;
  sourceSync?.setLocked(submitting);
  typographyPanel?.setLocked(submitting);
  symbolPanel?.updateCurrentFavorite();
  preview?.setLocked(submitting);
  document.getElementById('undoButton').disabled = submitting;
  document.getElementById('redoButton').disabled = submitting;
}

function maximumSourcePaneHeight() {
  const available = Math.max(0, workspace.clientHeight - sourceResizeHandle.offsetHeight);
  return available - Math.min(FORMULA_PANE_MIN_HEIGHT, Math.floor(available * 2 / 3));
}

function setSourcePaneHeight(height) {
  const maximum = maximumSourcePaneHeight();
  const minimum = Math.min(SOURCE_PANE_MIN_HEIGHT, maximum);
  sourcePaneHeight = Math.min(maximum, Math.max(minimum, Math.round(height)));
  workspace.style.setProperty("--source-pane-height", `${sourcePaneHeight}px`);
  sourceResizeHandle.setAttribute("aria-valuemax", String(maximum));
  sourceResizeHandle.setAttribute("aria-valuemin", String(minimum));
  sourceResizeHandle.setAttribute("aria-valuenow", String(sourcePaneHeight));
}

function finishSourcePaneResize(event) {
  if (event.pointerId !== sourceResizePointerId) {
    return;
  }

  sourceResizePointerId = null;
  sourceResizeHandle.classList.remove("dragging");
  if (sourceResizeHandle.hasPointerCapture(event.pointerId)) {
    sourceResizeHandle.releasePointerCapture(event.pointerId);
  }
}

function initializeSourcePaneResize() {
  setSourcePaneHeight(sourcePaneHeight);
  sourceResizeHandle.addEventListener("pointerdown", event => {
    if (event.button !== 0 || sourceResizePointerId !== null) {
      return;
    }

    event.preventDefault();
    sourceResizePointerId = event.pointerId;
    sourceResizeStartY = event.clientY;
    sourceResizeStartHeight = sourcePaneHeight;
    sourceResizeHandle.classList.add("dragging");
    sourceResizeHandle.setPointerCapture(event.pointerId);
  });
  sourceResizeHandle.addEventListener("pointermove", event => {
    if (event.pointerId !== sourceResizePointerId) {
      return;
    }

    setSourcePaneHeight(sourceResizeStartHeight + sourceResizeStartY - event.clientY);
  });
  sourceResizeHandle.addEventListener("pointerup", finishSourcePaneResize);
  sourceResizeHandle.addEventListener("pointercancel", finishSourcePaneResize);
  sourceResizeHandle.addEventListener("lostpointercapture", event => {
    if (event.pointerId === sourceResizePointerId) {
      sourceResizePointerId = null;
      sourceResizeHandle.classList.remove("dragging");
    }
  });
  sourceResizeHandle.addEventListener("keydown", event => {
    const step = event.shiftKey ? SOURCE_PANE_KEYBOARD_STEP * 3 : SOURCE_PANE_KEYBOARD_STEP;
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSourcePaneHeight(sourcePaneHeight + step);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setSourcePaneHeight(sourcePaneHeight - step);
    } else if (event.key === "Home") {
      event.preventDefault();
      setSourcePaneHeight(SOURCE_PANE_MIN_HEIGHT);
    } else if (event.key === "End") {
      event.preventDefault();
      setSourcePaneHeight(maximumSourcePaneHeight());
    }
  });

  new ResizeObserver(() => setSourcePaneHeight(sourcePaneHeight)).observe(workspace);
}

function currentLatex() {
  return sourceEditor?.value || "";
}

function mathfieldLatex() {
  return mathfield?.getValue("latex") || "";
}

function setLatex(latex) {
  sourceSync.load(String(latex || ""));
  syncColorFromSource();
  symbolPanel?.updateCurrentFavorite();
}

function syncColorFromSource() {
  if (!typographyPanel) return;
  typographyPanel.fields.color.value = formulaColor(currentLatex());
  applyVisualColor();
}

function updateFormulaColor() {
  const color = typographyPanel.fields.color.value;
  const value = withFormulaColor(currentLatex(), color);
  if (value !== currentLatex()) {
    sourceEditor.replace(value, 'visual');
    sourceSync.refresh();
  }
  applyVisualColor();
  preview.update();
}

function setSourceMode(reason) {
  const messages = locale.startsWith("zh") ? {
    sourceOnly: "可视化编辑器会改写这段源码；请在源码区编辑，或主动采用上方结果。",
    invalid: "源码结构有误或包含不支持的命令；请在源码区修正。",
    mathml: "当前为 MathML 源码，请在源码区编辑。",
    updating: "正在更新参考预览…", composing: ""
  } : {
    sourceOnly: "Visual editing would rewrite this source. Edit below or explicitly use the result above.",
    invalid: "The source has invalid structure or unsupported commands; fix it below.",
    mathml: "MathML source: edit in the source pane.",
    updating: "Updating reference view…", composing: ""
  };
  document.getElementById('sourceModeNote').hidden = !reason;
  document.getElementById('sourceModeMessage').textContent = messages[reason] || '';
  const adopt = document.getElementById('adoptVisualButton');
  adopt.hidden = reason !== 'sourceOnly';
  adopt.textContent = locale.startsWith('zh') ? '用上方结果替换源码（可撤销）' : 'Replace source with result (undoable)';
}

function scheduleCaretVisibility() {
  if (caretVisibilityFrame) {
    return;
  }

  caretVisibilityFrame = window.requestAnimationFrame(() => {
    caretVisibilityFrame = 0;
    const caret = mathfield?.shadowRoot?.querySelector(".ML__caret, .ML__latex-caret");
    if (!caret) {
      return;
    }

    const viewport = host.getBoundingClientRect();
    const caretRect = caret.getBoundingClientRect();
    const padding = 20;
    if (caretRect.bottom > viewport.bottom - padding) {
      host.scrollTop += caretRect.bottom - viewport.bottom + padding;
    } else if (caretRect.top < viewport.top + padding) {
      host.scrollTop -= viewport.top - caretRect.top + padding;
    }

    if (caretRect.right > viewport.right - padding) {
      host.scrollLeft += caretRect.right - viewport.right + padding;
    } else if (caretRect.left < viewport.left + padding) {
      host.scrollLeft -= viewport.left - caretRect.left + padding;
    }
  });
}

function accept() {
  if (submitting || sourceEditor.composing || sourceSync.visualComposing || typographyPanel.composing) {
    return;
  }
  sourceSync.visualInput();
  const latex = currentLatex();
  if (!hasFormulaContent(latex)) {
    setStatus(strings().latexRequired);
    return;
  }

  const typography = typographyPanel.snapshot();
  if (!typography) {
    document.getElementById('fontSizePoints').reportValidity();
    setStatus(locale.startsWith('zh') ? '请检查字体和字号设置。' : 'Check typography settings.');
    return;
  }
  typography.color = formulaColor(latex);
  setSubmitting(true);
  send({ type: "accept", session, revision: preview.revision, latex, display, typography });
}

function hideVirtualKeyboard() {
  window.mathVirtualKeyboard?.hide();
}

function configureMathfieldText(field) {
  field.setAttribute('aria-label', locale.startsWith('zh') ? '可视化公式编辑器' : 'Visual formula editor');
  field.setAttribute('aria-description', locale.startsWith('zh') ? '按 Escape 后再按 Tab 离开编辑器。' : 'Press Escape then Tab to leave the editor.');
  configureMathfieldMenu(field, locale, action => sourceSync?.performVisual(action));
}

function applyVisualColor() {
  if (mathfield) mathfield.style.color = typographyPanel?.fields.color.value || '#000000';
}

function createMathfield() {
  const field = new MathfieldElement();
  field.smartFence = true;
  field.mathVirtualKeyboardPolicy = 'manual';
  field.onScrollIntoView = scheduleCaretVisibility;
  field.addEventListener('beforeinput', event => sourceSync?.beforeVisualInput(event));
  field.addEventListener('input', () => { sourceSync?.visualInput(); scheduleCaretVisibility(); });
  field.addEventListener('compositionstart', () => { sourceSync?.visualComposition(true); updatePreviewComposition(); });
  field.addEventListener('compositionend', () => { sourceSync?.visualComposition(false); updatePreviewComposition(); });
  field.addEventListener('keydown', event => {
    if (!submitting && (event.ctrlKey || event.metaKey) && !event.altKey && !event.isComposing
        && (event.key.toLowerCase() === 'z' || event.key.toLowerCase() === 'y')) {
      event.preventDefault(); event.stopImmediatePropagation();
      sourceSync.history(event.shiftKey || event.key.toLowerCase() === 'y');
    }
  }, true);
  host.appendChild(field);
  configureMathfieldText(field);
  applyVisualColor();
  return field;
}

function recreateMathfield() {
  const previous = mathfield;
  mathfield = createMathfield();
  insertion.bindMathfield(mathfield);
  bindMathfieldInput(mathfield);
  previous.remove();
  return mathfield;
}

function focusInitialEditor() {
  if (!initialFocusPending || !insertion || !sourceSync) return;
  if (sourceSync.visualEnabled) insertion.focusVisual();
  else sourceEditor.focus();
}

function configureText() {
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  cancelButton.textContent = strings().cancel;
  acceptButton.textContent = mode === "update" ? strings().acceptUpdate : strings().acceptInsert;
  setStatus(strings().ready);
  for (const [id, zh, en] of [['undoButton', '撤销', 'Undo'], ['redoButton', '重做', 'Redo']]) {
    const button = document.getElementById(id);
    button.setAttribute('aria-label', locale.startsWith('zh') ? zh : en);
    button.title = `${locale.startsWith('zh') ? zh : en} (${id === 'undoButton' ? 'Ctrl+Z' : 'Ctrl+Y'})`;
  }
  configureMathfieldText(mathfield);
  symbolPanel.configure(locale);
}

function applyInit(payload) {
  locale = String(payload?.locale || "zh").toLowerCase();
  mode = payload?.mode === "update" ? "update" : "insert";
  session = payload.session;
  display = payload.display !== false;
  preview.configure(session);
  typographyPanel.configure(payload);
  setSubmitting(false);
  configureText();
  setLatex(initialFormulaColor(payload?.latex || "", payload?.typography?.color));
  insertion.reset();
  initialFocusPending = true;
  requestAnimationFrame(focusInitialEditor);
  scheduleCaretVisibility();
}

async function bootstrap() {
  initializeSourcePaneResize();
  document.addEventListener('contextmenu', event => {
    if (!event.composedPath().includes(mathfield)) event.preventDefault();
  }, true);
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", import.meta.url).href;
  MathfieldElement.soundsDirectory = null;
  mathfield = createMathfield();
  sourceEditor = new SourceEditor(latexSource, {
    commands: COMMANDS,
    completeTemplate: (entry, range) => insertion.insert(entry, {range}),
    onChange: (_value, change) => { sourceSync?.sourceChanged(change); syncColorFromSource(); preview?.update(); symbolPanel?.updateCurrentFavorite(); },
    onComposition: active => { sourceSync?.composition(active); updatePreviewComposition(); }
  });
  sourceSync = new SourceSync({source: sourceEditor, mathfield, readVisual: mathfieldLatex,
    recreateMathfield, onMode: setSourceMode});
  document.getElementById('adoptVisualButton').addEventListener('click', () => {
    if (insertion.blocked) return;
    sourceEditor.replace(formatVisualLatex(mathfieldLatex()), 'visual');
    sourceSync.refresh();
    if (sourceSync.visualEnabled) insertion.focusVisual();
  });
  insertion = new TemplateInsertion({source: sourceEditor, sync: sourceSync, mathfield, sourceHost: latexSource,
    onInsert: scheduleCaretVisibility, isComposing: () => Boolean(typographyPanel?.composing)});
  symbolPanel = new SymbolPanel(insertion, currentLatex);
  const image = document.getElementById('previewImage');
  const previewStatus = document.getElementById('previewStatus');
  preview = new DraftPreview({send,
    snapshot: () => {
      const typography = typographyPanel.snapshot();
      if (!typography || !hasFormulaContent(currentLatex())) {
        previewStatus.textContent = locale.startsWith('zh') ? '请输入公式及有效字号。' : 'Enter a formula and valid size.';
        return null;
      }
      return {latex: currentLatex(), display, typography: {...typography, color: formulaColor(currentLatex())}};
    },
    changed: () => {
      image.hidden = true; image.removeAttribute('src');
      previewStatus.textContent = locale.startsWith('zh') ? '正在更新预览…' : 'Updating preview…';
    },
    result: response => {
      previewStatus.textContent = response.error || (response.warnings || []).join(' ');
      if (response.error) return;
      image.style.width = `${response.widthPoints}pt`;
      image.style.height = `${response.heightPoints}pt`;
      image.src = response.image; image.hidden = false;
    }
  });
  typographyPanel = new TypographyPanel({onChange: input => {
    if (input.id === 'color') updateFormulaColor();
    else preview.update();
  },
    onComposition: updatePreviewComposition,
    blocked: () => insertion.blocked,
    onMode: active => {
      sourceSync.visualInput(); insertion.setPreview(active); preview.setActive(active);
    }});
  const shortcuts = new Map(CATALOG.filter(entry => entry.shortcut).map(entry => [entry.shortcut, entry]));
  bindMathfieldInput = configureMathfield(mathfield, {onAccept: accept, insert: entry => insertion.insert(entry), shortcuts,
    performEdit: action => sourceSync.performVisual(action)});
  for (const [id, redo] of [['undoButton', false], ['redoButton', true]]) {
    document.getElementById(id).addEventListener('click', () => {
      if (insertion.blocked) return;
      sourceSync.history(redo); insertion.restoreFocus();
    });
  }
  for (const event of ['pointerdown', 'keydown'])
    document.addEventListener(event, () => { initialFocusPending = false; }, true);
  document.addEventListener('focusin', event => {
    if (!initialFocusPending || event.target === mathfield || event.target === sourceEditor.view.contentDOM) return;
    if (event.target === document.getElementById('undoButton')) requestAnimationFrame(focusInitialEditor);
    else initialFocusPending = false;
  }, true);
  window.addEventListener('focus', () => requestAnimationFrame(focusInitialEditor));
  cancelButton.addEventListener("click", () => { preview.stop(); send({ type: "cancel", session }); });
  window.addEventListener("pagehide", () => preview.stop());
  acceptButton.addEventListener("click", accept);
  window.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.isComposing || !window.mathVirtualKeyboard?.visible) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    hideVirtualKeyboard();
    queueMicrotask(() => mathfield.focus());
  }, true);
  window.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
    const browserCommand = (event.ctrlKey || event.metaKey) && !event.altKey
      && ['f', 'p', 'r', '+', '=', '-', '0'].includes(event.key.toLowerCase());
    if (browserCommand || event.key === 'F3' || event.key === 'F5') {
      event.preventDefault();
      return;
    }
    if (event.key === "Escape" && !event.isComposing) {
      event.preventDefault();
      hideVirtualKeyboard();
      return;
    }

    if (event.key === "Enter" && event.shiftKey && !event.isComposing && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      accept();
    }
  });
  configureText();
  sourceSync.load("");
  if (pendingInit || window.__latexSnipperPendingInit) {
    applyInit(pendingInit || window.__latexSnipperPendingInit);
    pendingInit = null;
    window.__latexSnipperPendingInit = null;
  }
}

function updatePreviewComposition() {
  preview?.setComposing(Boolean(sourceEditor?.composing || sourceSync?.visualComposing || typographyPanel?.composing));
}

window.LaTeXSnipperEditor = {
  init(payload) {
    pendingInit = payload;
    if (insertion) {
      applyInit(payload);
      pendingInit = null;
    }
  },
  setStatus,
  setSubmitting,
  previewResult: response => preview?.receive(response),
};

bootstrap().catch((error) => setStatus(String(error)));
