import { MathfieldElement } from "./vendor/mathlive.min.mjs";

const DEFAULT_LATEX = "e^{i\\pi}+1=0";

const state = {
  latex: DEFAULT_LATEX,
  busy: false,
  ocrActive: false,
  strings: {},
};

const els = {
  hostLabel: document.getElementById("hostLabel"),
  connectButton: document.getElementById("connectButton"),
  statusBanner: document.getElementById("statusBanner"),
  statusText: document.getElementById("statusText"),
  equationLabel: document.getElementById("equationLabel"),
  previewHost: document.getElementById("previewHost"),
  latexSource: document.getElementById("latexSource"),
  ocrButton: document.getElementById("ocrButton"),
  insertButton: document.getElementById("insertButton"),
};

let previewField = null;
let applying = false;
let syncingFromMathfield = false;
let syncingFromSource = false;

function post(message) {
  window.chrome?.webview?.postMessage(message);
}

function readState() {
  return {
    latex: els.latexSource.value,
  };
}

function emitState() {
  if (applying) return;
  Object.assign(state, readState());
  post({ type: "state", ...readState() });
}

function setLatex(latex) {
  state.latex = latex || "";
  els.latexSource.value = state.latex;
  previewField.setValue(state.latex, { silenceNotifications: true });
  resizePreview();
}

function resizePreview() {
  if (!previewField) return;
  window.requestAnimationFrame(() => {
    const fieldHeight = Math.ceil(previewField.scrollHeight || previewField.getBoundingClientRect().height || 44);
    const nextHeight = Math.max(66, Math.min(220, fieldHeight + 24));
    els.previewHost.style.height = `${nextHeight}px`;
  });
}

function applyLabels(strings) {
  if (!strings) return;
  els.hostLabel.textContent = strings.officePlugin || els.hostLabel.textContent;
  els.connectButton.textContent = strings.connect || els.connectButton.textContent;
  els.equationLabel.textContent = strings.equation || els.equationLabel.textContent;
  els.ocrButton.textContent = strings.screenshotOcr || els.ocrButton.textContent;
  state.strings = { ...state.strings, ...strings };
  els.insertButton.textContent = strings.insert || els.insertButton.textContent;
}

function applyState(payload) {
  applying = true;
  try {
    applyLabels(payload.strings);
    document.documentElement.lang = String(payload.locale || "").toLowerCase().startsWith("zh") ? "zh-CN" : "en";
    setLatex(payload.latex || DEFAULT_LATEX);
  } finally {
    applying = false;
  }
}

function applyStatus(payload) {
  state.busy = Boolean(payload.busy);
  state.ocrActive = Boolean(payload.ocrActive);
  const kind = payload.kind || "info";
  els.statusBanner.className = `status-banner ${state.ocrActive ? "pending" : kind === "success" ? "success" : kind === "error" ? "error" : ""}`.trim();
  els.statusText.textContent = payload.message || "";
  els.ocrButton.textContent = state.ocrActive
    ? state.strings.cancelOcr || "Cancel OCR"
    : state.strings.screenshotOcr || els.ocrButton.textContent;
  const busyButtons = [els.connectButton, els.insertButton];
  for (const button of busyButtons) {
    button.disabled = state.busy;
  }
  els.ocrButton.disabled = false;
  els.ocrButton.classList.toggle("active", state.ocrActive);
}

function apply(payload) {
  if (!payload || !payload.type) return;
  if (payload.type === "state") {
    applyState(payload);
  } else if (payload.type === "status") {
    applyStatus(payload);
  }
}

function initEvents() {
  previewField.addEventListener("input", () => {
    if (applying || syncingFromSource) return;
    syncingFromMathfield = true;
    els.latexSource.value = previewField.getValue("latex-expanded").trim();
    syncingFromMathfield = false;
    resizePreview();
    emitState();
  });
  els.latexSource.addEventListener("input", () => {
    if (syncingFromMathfield) {
      emitState();
      return;
    }
    syncingFromSource = true;
    previewField.setValue(els.latexSource.value, { silenceNotifications: true });
    syncingFromSource = false;
    resizePreview();
    emitState();
  });
  els.connectButton.addEventListener("click", () => post({ type: "connect", ...readState() }));
  els.ocrButton.addEventListener("click", () => post({ type: "ocr", ...readState() }));
  els.insertButton.addEventListener("click", () => post({ type: "insert", ...readState() }));
}

function flushPending() {
  const pending = window.__latexSnipperTaskPanePending || [];
  window.__latexSnipperTaskPanePending = [];
  for (const payload of pending) {
    apply(payload);
  }
}

async function bootstrap() {
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", window.location.href).href;
  previewField = new MathfieldElement();
  previewField.mathVirtualKeyboardPolicy = "manual";
  previewField.defaultMode = "math";
  els.previewHost.appendChild(previewField);
  initEvents();
  setLatex(DEFAULT_LATEX);
  window.LaTeXSnipperTaskPane = { apply };
  flushPending();
  post({ type: "state", ...readState() });
}

bootstrap().catch((error) => {
  els.statusBanner.className = "status-banner error";
  els.statusText.textContent = String(error);
});
