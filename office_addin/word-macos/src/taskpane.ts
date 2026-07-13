import "./taskpane.css";

import { AgentClientError, createSameOriginAgentClient } from "./backend/agentClient";
import { normalizeLatexInput, type FormulaMode } from "./domain/formula";
import {
  mountMathLiveEditor,
  type MathLiveEditorController,
} from "./editor/mathLiveEditor";
import {
  createOfficeJsHostPort,
  OfficeInitializationTimeoutError,
  OfficeJsUnavailableError,
} from "./office/officeHost";
import { FormulaRenderError, MathJaxRenderer } from "./rendering/mathJaxRenderer";
import {
  createInitialAppState,
  StateStore,
  type AgentStatus,
  type AppState,
  type HostStatus,
  type StatusTone,
} from "./state/appState";
import { createDebouncedTask } from "./utils/debounce";

function elementById<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Required taskpane element is missing: ${id}`);
  }
  return element as T;
}

const elements = {
  hostStatus: elementById<HTMLSpanElement>("host-status"),
  agentStatus: elementById<HTMLSpanElement>("agent-status"),
  editorStatus: elementById<HTMLSpanElement>("editor-status"),
  previewStatus: elementById<HTMLSpanElement>("preview-status"),
  editorHost: elementById<HTMLDivElement>("math-editor-host"),
  sourceDetails: elementById<HTMLDetailsElement>("source-details"),
  latexSource: elementById<HTMLTextAreaElement>("latex-source"),
  preview: elementById<HTMLDivElement>("formula-preview"),
  numberField: elementById<HTMLDivElement>("number-field"),
  manualNumber: elementById<HTMLInputElement>("manual-number"),
  insertButton: elementById<HTMLButtonElement>("insert-button"),
  clearButton: elementById<HTMLButtonElement>("clear-button"),
  operationStatus: elementById<HTMLParagraphElement>("operation-status"),
  retryAgentButton: elementById<HTMLButtonElement>("retry-agent-button"),
  ocrButton: elementById<HTMLButtonElement>("ocr-button"),
  hostDetail: elementById<HTMLElement>("host-detail"),
  agentDetail: elementById<HTMLElement>("agent-detail"),
  retryOfficeButton: elementById<HTMLButtonElement>("retry-office-button"),
};

const modeInputs = [
  ...document.querySelectorAll<HTMLInputElement>('input[name="formula-mode"]'),
];
const store = new StateStore<AppState>(createInitialAppState());
const renderer = new MathJaxRenderer();
const officeHost = createOfficeJsHostPort();
const agentClient = createSameOriginAgentClient();

let editor: MathLiveEditorController | undefined;
let renderGeneration = 0;
let officeCheckGeneration = 0;
let agentCheckGeneration = 0;
let previewErrorActive = false;

function connectionTone(status: HostStatus | AgentStatus): StatusTone {
  if (status === "ready") {
    return "success";
  }
  if (status === "checking") {
    return "working";
  }
  if (status === "outside-office" || status === "offline") {
    return "warning";
  }
  return "danger";
}

function renderState(state: Readonly<AppState>): void {
  elements.hostStatus.textContent = state.host.label;
  elements.hostStatus.dataset.state = connectionTone(state.host.status);
  elements.hostStatus.title = state.host.detail;
  elements.agentStatus.textContent = state.agent.label;
  elements.agentStatus.dataset.state = connectionTone(state.agent.status);
  elements.agentStatus.title = state.agent.detail;
  elements.editorStatus.textContent = state.editor.detail;
  elements.previewStatus.textContent = state.preview.detail;
  elements.preview.setAttribute("aria-busy", String(state.preview.status === "loading"));
  elements.editorHost.setAttribute("aria-busy", String(state.editor.status === "loading"));
  elements.clearButton.disabled = state.operation.busy || !state.draft.latex;
  elements.insertButton.disabled = true;
  elements.ocrButton.disabled = true;
  elements.operationStatus.textContent = state.operation.message;
  elements.operationStatus.dataset.tone = state.operation.tone;
  elements.numberField.hidden = state.draft.mode !== "numbered";
  elements.manualNumber.disabled = state.draft.mode !== "numbered";
  elements.retryOfficeButton.hidden = state.host.status !== "error";
  elements.retryOfficeButton.disabled = state.host.status === "checking";
  elements.retryAgentButton.disabled = state.agent.status === "checking";
  elements.hostDetail.textContent = state.host.detail;
  elements.agentDetail.textContent = state.agent.detail;
}

store.subscribe(renderState);

function setPreviewPlaceholder(message: string): void {
  const placeholder = document.createElement("span");
  placeholder.className = "preview-placeholder";
  placeholder.textContent = message;
  elements.preview.replaceChildren(placeholder);
}

async function updatePreview(): Promise<void> {
  const generation = ++renderGeneration;
  const { latex, mode } = store.snapshot.draft;
  if (!latex) {
    setPreviewPlaceholder("输入公式后，由本地 MathJax 生成预览。");
    store.update((state) => ({
      ...state,
      preview: { status: "idle", detail: "等待输入", mathml: "" },
      operation: previewErrorActive
        ? { busy: false, tone: "neutral", message: "等待输入公式；当前不会修改文档。" }
        : state.operation,
    }));
    previewErrorActive = false;
    return;
  }

  store.update((state) => ({
    ...state,
    preview: { ...state.preview, status: "loading", detail: "正在渲染" },
  }));

  try {
    const rendered = await renderer.render(latex, mode !== "inline");
    if (generation !== renderGeneration) {
      return;
    }
    elements.preview.replaceChildren(rendered.svg);
    store.update((state) => ({
      ...state,
      preview: {
        status: "ready",
        detail: "本地预览已更新",
        mathml: rendered.mathml,
      },
      operation: previewErrorActive
        ? { busy: false, tone: "neutral", message: "公式预览已恢复；当前不会修改文档。" }
        : state.operation,
    }));
    previewErrorActive = false;
  } catch (error) {
    if (generation !== renderGeneration) {
      return;
    }
    const message =
      error instanceof FormulaRenderError ? error.message : "公式预览渲染失败。";
    setPreviewPlaceholder(message);
    previewErrorActive = true;
    store.update((state) => ({
      ...state,
      preview: { status: "error", detail: "预览失败", mathml: "" },
      operation: { busy: false, tone: "danger", message },
    }));
  }
}

const previewTask = createDebouncedTask(() => {
  void updatePreview();
}, 180);

function setLatex(latexValue: unknown, source: "mathlive" | "textarea" | "clear"): void {
  renderGeneration += 1;
  const latex = normalizeLatexInput(latexValue);
  if (source !== "textarea" && elements.latexSource.value !== latex) {
    elements.latexSource.value = latex;
  }
  if (source !== "mathlive") {
    editor?.setLatex(latex);
  }
  store.update((state) => ({
    ...state,
    draft: { ...state.draft, latex },
    editor: {
      ...state.editor,
      dirty: latex.length > 0,
      detail: state.editor.status === "ready" ? (latex ? "正在编辑" : "可以输入公式") : state.editor.detail,
    },
  }));
  previewTask.schedule();
}

async function initializeEditor(): Promise<void> {
  try {
    editor = await mountMathLiveEditor(elements.editorHost, {
      initialLatex: store.snapshot.draft.latex,
      onChange(latex) {
        setLatex(latex, "mathlive");
      },
    });
    store.update((state) => ({
      ...state,
      editor: { status: "ready", dirty: false, detail: "可以输入公式" },
    }));
  } catch (error) {
    const message = `MathLive 加载失败：${error instanceof Error ? error.message : String(error)}`;
    setPreviewPlaceholder("可继续使用 LaTeX 源码输入；可视化编辑器未加载。" );
    elements.sourceDetails.open = true;
    store.update((state) => ({
      ...state,
      editor: { status: "error", dirty: false, detail: "MathLive 加载失败" },
      operation: { busy: false, tone: "danger", message },
    }));
  }
}

async function initializeOffice(): Promise<void> {
  const generation = ++officeCheckGeneration;
  store.update((state) => ({
    ...state,
    host: {
      status: "checking",
      label: "正在连接 Word",
      detail: "正在等待 Office.js 初始化。",
    },
  }));
  try {
    const info = await officeHost.ready();
    if (generation !== officeCheckGeneration) {
      return;
    }
    if (info.host === "word" && info.wordApi13) {
      const diagnostics = [info.platform, info.version].filter(Boolean).join(" · ");
      store.update((state) => ({
        ...state,
        host: {
          status: "ready",
          label: "Word 已连接",
          detail: `WordApi 1.3 可用${diagnostics ? ` · ${diagnostics}` : ""}`,
        },
      }));
      return;
    }
    if (info.host === "word") {
      store.update((state) => ({
        ...state,
        host: {
          status: "unsupported",
          label: "Word 版本不支持",
          detail: "当前 Word 不支持所需的 WordApi 1.3。",
        },
      }));
      return;
    }
    if (info.host === "other") {
      store.update((state) => ({
        ...state,
        host: {
          status: "unsupported",
          label: "请在 Word 中打开",
          detail: `检测到其他 Office 宿主${info.platform ? ` · ${info.platform}` : ""}。`,
        },
      }));
      return;
    }
    store.update((state) => ({
      ...state,
      host: {
        status: "outside-office",
        label: "浏览器预览模式",
        detail: "未检测到 Word；编辑和预览仍可用于开发测试。",
      },
    }));
  } catch (error) {
    if (generation !== officeCheckGeneration) {
      return;
    }
    const timedOut = error instanceof OfficeInitializationTimeoutError;
    const unavailable = error instanceof OfficeJsUnavailableError;
    store.update((state) => ({
      ...state,
      host: {
        status: "error",
        label: "Word 连接失败",
        detail:
          timedOut || unavailable
            ? `${error.message} 请检查 Office.js 网络状态后重试。`
            : `Office.js 初始化失败：${String(error)}`,
      },
    }));
  }
}

async function checkAgent(): Promise<void> {
  const generation = ++agentCheckGeneration;
  store.update((state) => ({
    ...state,
    agent: {
      status: "checking",
      label: "正在连接后台",
      detail: "正在检查同源 /v1/health。",
    },
  }));
  try {
    const health = await agentClient.getHealth();
    if (generation !== agentCheckGeneration) {
      return;
    }
    store.update((state) => ({
      ...state,
      agent: {
        status: "ready",
        label: "后台已连接",
        detail: `${health.serviceVersion} · ${health.capabilities.length} 项能力`,
      },
    }));
  } catch (error) {
    if (generation !== agentCheckGeneration) {
      return;
    }
    const clientError = error instanceof AgentClientError ? error : undefined;
    const incompatible = clientError?.code === "incompatible";
    store.update((state) => ({
      ...state,
      agent: {
        status: incompatible ? "incompatible" : "offline",
        label: incompatible ? "后台版本不兼容" : "后台未连接",
        detail: clientError?.message ?? "无法连接本机 LaTeXSnipper 服务。",
      },
    }));
  }
}

elements.latexSource.addEventListener("input", (event) => {
  if ("isComposing" in event && event.isComposing === true) {
    return;
  }
  setLatex(elements.latexSource.value, "textarea");
});
elements.latexSource.addEventListener("compositionend", () => {
  setLatex(elements.latexSource.value, "textarea");
});

for (const input of modeInputs) {
  input.addEventListener("change", () => {
    if (!input.checked) {
      return;
    }
    const mode = input.value as FormulaMode;
    store.update((state) => ({
      ...state,
      draft: { ...state.draft, mode },
    }));
    previewTask.schedule();
  });
}

elements.manualNumber.addEventListener("input", () => {
  store.update((state) => ({
    ...state,
    draft: { ...state.draft, manualNumber: normalizeLatexInput(elements.manualNumber.value) },
  }));
});

elements.clearButton.addEventListener("click", () => {
  renderGeneration += 1;
  previewTask.cancel();
  setLatex("", "clear");
  elements.manualNumber.value = "";
  store.update((state) => ({
    ...state,
    draft: { ...state.draft, manualNumber: "" },
    operation: { busy: false, tone: "neutral", message: "已清空当前编辑内容。" },
  }));
  editor?.focus();
});

elements.retryAgentButton.addEventListener("click", () => {
  void checkAgent();
});
elements.retryOfficeButton.addEventListener("click", () => {
  void initializeOffice();
});

window.addEventListener("beforeunload", () => {
  previewTask.cancel();
  editor?.destroy();
});

void Promise.allSettled([initializeEditor(), initializeOffice(), checkAgent()]);
