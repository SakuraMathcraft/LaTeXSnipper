const state = {
  host: "127.0.0.1",
  port: 43637,
  token: "",
  contractPath: "",
  hotkey: "Ctrl+Shift+F",
  pollIntervalMs: 200,
  timeoutMs: 120000,
  currentTaskId: "",
  fxApplied: "unknown",
  hotkeyBusy: false,
  handshakeBusy: false,
  daemonEnsurePromise: null,
  imagePollInFlight: false,
  pdfPollInFlight: false,
  pdfMaxPages: 0,
  pdfDpi: 200,
  pdfTemplateStyle: "paper",
  currentPdfTaskId: "",
  metricsTimer: null,
  envMirror: "official",
  envTaskId: "",
  envTaskBusy: false,
  envProgressCur: 0,
  envProgressTotal: 0,
  envProgressVisualPct: 0,
  envProgressTargetPct: 0,
  envProgressTimer: null,
  fxMode: "acrylic",
  compactMode: false,
  uiBgAlpha: 0.20,
  uiSidebarAlpha: 0.20,
  uiPanelAlpha: 0.33,
  uiBlurPx: 26,
  uiRadiusPx: 12,
  uiBrightness: 1.18,
  uiContrast: 1.20,
  uiSaturatePct: 40,
  uiTintAlpha: 0.00,
  uiNoiseAlpha: 0.02,
  aboutUpdateUrl: "https://github.com/SakuraMathcraft/LaTeXSnipper/tree/tauri",
  imageCopyFormat: "latex",
  resultHistory: [],
};

const el = (id) => document.getElementById(id);
const now = () => new Date().toLocaleTimeString();
const RESULT_STORE_KEY = "latexsnipper_tauri_mvp_result_store";
const IMAGE_TIMEOUT_DEFAULT_MS = 120000;
const IMAGE_TIMEOUT_MIN_MS = 15000;
const IMAGE_TIMEOUT_MAX_MS = 1800000;
const HOTKEY_TIMEOUT_MIN_MS = 45000;
let actionTagTimer = null;

function log(msg, level = "INFO") {
  const box = el("logOutput");
  const line = `[${now()}] [${level}] ${String(msg ?? "")}`;
  box.textContent += `${line}\n`;
  box.scrollTop = box.scrollHeight;
}

function setActionTag(text, level = "info", timeoutMs = 3200) {
  const tag = el("actionTag");
  if (!tag) return;
  tag.textContent = text || "操作: 就绪";
  tag.classList.remove("action-ok", "action-warn", "action-error", "muted");
  if (level === "ok") {
    tag.classList.add("action-ok");
  } else if (level === "warn") {
    tag.classList.add("action-warn");
  } else if (level === "error") {
    tag.classList.add("action-error");
  } else {
    tag.classList.add("muted");
  }
  if (actionTagTimer) {
    clearTimeout(actionTagTimer);
    actionTagTimer = null;
  }
  if (timeoutMs > 0) {
    actionTagTimer = setTimeout(() => {
      tag.textContent = "操作: 就绪";
      tag.classList.remove("action-ok", "action-warn", "action-error");
      tag.classList.add("muted");
      actionTagTimer = null;
    }, timeoutMs);
  }
}

function getInvoke() {
  return window.__TAURI__?.core?.invoke;
}

async function invoke(cmd, args = {}) {
  const fn = getInvoke();
  if (!fn) throw new Error("Tauri invoke unavailable");
  return fn(cmd, args);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clampNumber(v, min, max, fallback) {
  const n = Number(v);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function getImagePollOptions() {
  const pollIntervalMs = clampNumber(el("pollIntervalMs")?.value, 50, 5000, 200);
  const timeoutMs = clampNumber(el("timeoutMs")?.value, IMAGE_TIMEOUT_MIN_MS, IMAGE_TIMEOUT_MAX_MS, IMAGE_TIMEOUT_DEFAULT_MS);
  return { pollIntervalMs, timeoutMs };
}

function updateNavIndicator(btn) {
  const indicator = el("navIndicator");
  const nav = document.querySelector(".nav");
  if (!indicator || !nav || !btn) return;
  const top = btn.offsetTop;
  const h = btn.offsetHeight;
  indicator.style.top = `${top}px`;
  indicator.style.height = `${h}px`;
  indicator.style.opacity = "1";
}

function initCustomSelectByIds(rootId, triggerId, panelId, hiddenId, fallbackValue = "") {
  const root = el(rootId);
  const trigger = el(triggerId);
  const panel = el(panelId);
  const hidden = el(hiddenId);
  if (!root || !trigger || !panel || !hidden) return;
  const hostCard = root.closest(".card");

  const close = () => {
    root.classList.remove("open");
    root.setAttribute("aria-expanded", "false");
    if (hostCard && !hostCard.querySelector(".custom-select.open")) {
      hostCard.classList.remove("select-open");
    }
  };
  const open = () => {
    document.querySelectorAll(".card.select-open").forEach((n) => {
      if (n !== hostCard) n.classList.remove("select-open");
    });
    document.querySelectorAll(".custom-select.open").forEach((n) => {
      if (n !== root) {
        n.classList.remove("open");
        n.setAttribute("aria-expanded", "false");
      }
    });
    root.classList.add("open");
    root.setAttribute("aria-expanded", "true");
    if (hostCard) hostCard.classList.add("select-open");
  };
  const toggle = () => {
    if (root.classList.contains("open")) {
      close();
    } else {
      open();
    }
  };

  const selectValue = (value) => {
    const items = panel.querySelectorAll(".custom-select-item");
    let hit = false;
    items.forEach((item) => {
      const active = item.dataset.value === value;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
      if (active) {
        hit = true;
        trigger.textContent = (item.textContent || "").trim();
      }
    });
    if (hit) {
      hidden.value = value;
      return;
    }
    const first = panel.querySelector(".custom-select-item");
    if (first) {
      const fv = first.dataset.value || fallbackValue;
      hidden.value = fv;
      first.classList.add("active");
      first.setAttribute("aria-selected", "true");
      trigger.textContent = (first.textContent || "").trim();
      return;
    }
    hidden.value = fallbackValue;
  };

  trigger.addEventListener("click", (ev) => {
    ev.preventDefault();
    toggle();
  });

  panel.querySelectorAll(".custom-select-item").forEach((item) => {
    item.addEventListener("click", (ev) => {
      ev.preventDefault();
      selectValue(item.dataset.value || "pix2text");
      close();
    });
  });

  root.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      close();
      return;
    }
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      toggle();
    }
  });

  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (!(t instanceof Node)) return;
    if (!root.contains(t)) close();
  });

  selectValue(hidden.value || fallbackValue);
}

function syncCustomSelectByIds(rootId, triggerId, panelId, hiddenId, fallbackValue = "") {
  const root = el(rootId);
  const trigger = el(triggerId);
  const panel = el(panelId);
  const hidden = el(hiddenId);
  if (!root || !trigger || !panel || !hidden) return;
  const value = String(hidden.value || fallbackValue || "").trim();
  const items = panel.querySelectorAll(".custom-select-item");
  let matched = false;
  items.forEach((item) => {
    const active = String(item.dataset.value || "") === value;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", active ? "true" : "false");
    if (active) {
      matched = true;
      trigger.textContent = (item.textContent || "").trim();
    }
  });
  if (!matched) {
    const first = panel.querySelector(".custom-select-item");
    if (first) {
      first.classList.add("active");
      first.setAttribute("aria-selected", "true");
      hidden.value = String(first.dataset.value || fallbackValue || "");
      trigger.textContent = (first.textContent || "").trim();
    } else {
      hidden.value = fallbackValue || "";
      trigger.textContent = "";
    }
  }
}

function initCustomSelect() {
  initCustomSelectByIds("modelNameSelect", "modelNameTrigger", "modelNamePanel", "modelName", "pix2text");
  initCustomSelectByIds(
    "imageCopyFormatSelect",
    "imageCopyFormatTrigger",
    "imageCopyFormatPanel",
    "imageCopyFormat",
    "latex"
  );
  initCustomSelectByIds(
    "pdfOutputFormatSelect",
    "pdfOutputFormatTrigger",
    "pdfOutputFormatPanel",
    "pdfOutputFormat",
    "markdown"
  );
  initCustomSelectByIds(
    "pdfTemplateStyleSelect",
    "pdfTemplateStyleTrigger",
    "pdfTemplateStylePanel",
    "pdfTemplateStyle",
    "paper"
  );
  initCustomSelectByIds(
    "envMirrorSelect",
    "envMirrorTrigger",
    "envMirrorPanel",
    "envMirror",
    "official"
  );
}

function bindNav() {
  const nav = document.querySelectorAll(".nav-btn");
  nav.forEach((btn) => {
    btn.addEventListener("click", () => {
      const page = btn.dataset.page;
      const title = btn.dataset.title || btn.textContent.trim();
      nav.forEach((x) => x.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
      el(`page-${page}`).classList.add("active");
      el("pageTitle").textContent = title;
      updateNavIndicator(btn);
    });
  });
  const active = document.querySelector(".nav-btn.active");
  if (active) {
    updateNavIndicator(active);
  }
  window.addEventListener("resize", () => {
    const nowActive = document.querySelector(".nav-btn.active");
    if (nowActive) updateNavIndicator(nowActive);
  });
}

function loadSettings() {
  try {
    const raw = localStorage.getItem("latexsnipper_tauri_mvp_settings");
    if (!raw) return;
    const data = JSON.parse(raw);
    Object.assign(state, data || {});
  } catch (e) {
    log(`读取本地设置失败: ${e}`, "WARN");
  }
}

function saveSettings() {
  const imgPoll = getImagePollOptions();
  const data = {
    host: el("host").value.trim(),
    port: Number(el("port").value || 0) || 43637,
    token: el("token").value.trim(),
    contractPath: el("contractPath").value.trim(),
    hotkey: el("hotkeyInput").value.trim() || "Ctrl+Shift+F",
    pollIntervalMs: imgPoll.pollIntervalMs,
    timeoutMs: imgPoll.timeoutMs,
    fxMode: (state.fxMode || "acrylic").trim() || "acrylic",
    compactMode: !!state.compactMode,
    pdfMaxPages: Math.max(0, Number(el("pdfMaxPages")?.value || 0) || 0),
    pdfDpi: Math.max(72, Number(el("pdfDpi")?.value || 200) || 200),
    pdfTemplateStyle: (el("pdfTemplateStyle")?.value || "paper").trim() || "paper",
    envMirror: (el("envMirror")?.value || "official").trim() || "official",
    uiBgAlpha: Math.max(0.08, Math.min(0.56, Number(el("uiBgAlpha")?.value || 0.20) || 0.20)),
    uiSidebarAlpha: Math.max(0.08, Math.min(0.50, Number(el("uiSidebarAlpha")?.value || 0.20) || 0.20)),
    uiPanelAlpha: Math.max(0.08, Math.min(0.50, Number(el("uiPanelAlpha")?.value || 0.33) || 0.33)),
    uiBlurPx: Math.max(6, Math.min(64, Number(el("uiBlurPx")?.value || 26) || 26)),
    uiRadiusPx: Math.max(8, Math.min(18, Number(el("uiRadiusPx")?.value || 12) || 12)),
    uiBrightness: Math.max(0.6, Math.min(1.8, Number(el("uiBrightness")?.value || 1.18) || 1.18)),
    uiContrast: Math.max(0.7, Math.min(1.2, Number(el("uiContrast")?.value || 1.2) || 1.2)),
    uiSaturatePct: Math.max(40, Math.min(280, Number(el("uiSaturatePct")?.value || 40) || 40)),
    uiTintAlpha: Math.max(0.0, Math.min(0.26, Number(el("uiTintAlpha")?.value || 0.0) || 0.0)),
    uiNoiseAlpha: Math.max(0.0, Math.min(0.18, Number(el("uiNoiseAlpha")?.value || 0.02) || 0.02)),
    imageCopyFormat: (el("imageCopyFormat")?.value || "latex").trim() || "latex",
    aboutUpdateUrl:
      (el("aboutUpdateUrl")?.value || "https://github.com/SakuraMathcraft/LaTeXSnipper/tree/tauri").trim() ||
      "https://github.com/SakuraMathcraft/LaTeXSnipper/tree/tauri",
  };
  Object.assign(state, data);
  localStorage.setItem("latexsnipper_tauri_mvp_settings", JSON.stringify(data));
  log("设置已保存");
}

function fillForm() {
  el("host").value = state.host;
  el("port").value = String(state.port);
  el("token").value = state.token;
  el("contractPath").value = state.contractPath || "";
  el("hotkeyInput").value = state.hotkey || "Ctrl+Shift+F";
  el("hotkeyStatus").value = "未注册";
  el("pollIntervalMs").value = String(clampNumber(state.pollIntervalMs, 50, 5000, 200));
  el("timeoutMs").value = String(clampNumber(state.timeoutMs, IMAGE_TIMEOUT_MIN_MS, IMAGE_TIMEOUT_MAX_MS, IMAGE_TIMEOUT_DEFAULT_MS));
  if (el("pdfMaxPages")) el("pdfMaxPages").value = String(state.pdfMaxPages ?? 0);
  if (el("pdfDpi")) el("pdfDpi").value = String(state.pdfDpi || 200);
  if (el("pdfTemplateStyle")) el("pdfTemplateStyle").value = String(state.pdfTemplateStyle || "paper");
  if (el("envMirror")) el("envMirror").value = state.envMirror || "official";
  if (el("uiBgAlpha")) el("uiBgAlpha").value = String(state.uiBgAlpha ?? 0.20);
  if (el("uiSidebarAlpha")) el("uiSidebarAlpha").value = String(state.uiSidebarAlpha ?? 0.20);
  if (el("uiPanelAlpha")) el("uiPanelAlpha").value = String(state.uiPanelAlpha ?? 0.33);
  if (el("uiBlurPx")) el("uiBlurPx").value = String(state.uiBlurPx ?? 26);
  if (el("uiRadiusPx")) el("uiRadiusPx").value = String(state.uiRadiusPx ?? 12);
  if (el("uiBrightness")) el("uiBrightness").value = String(state.uiBrightness ?? 1.18);
  if (el("uiContrast")) el("uiContrast").value = String(state.uiContrast ?? 1.2);
  if (el("uiSaturatePct")) el("uiSaturatePct").value = String(state.uiSaturatePct ?? 40);
  if (el("uiTintAlpha")) el("uiTintAlpha").value = String(state.uiTintAlpha ?? 0.0);
  if (el("uiNoiseAlpha")) el("uiNoiseAlpha").value = String(state.uiNoiseAlpha ?? 0.02);
  if (el("imageCopyFormat")) el("imageCopyFormat").value = String(state.imageCopyFormat || "latex");
  if (el("aboutUpdateUrl")) {
    el("aboutUpdateUrl").value =
      state.aboutUpdateUrl || "https://github.com/SakuraMathcraft/LaTeXSnipper/tree/tauri";
  }
  setWindowModeTag(!!state.compactMode);
  if (el("pdfModelName")) el("pdfModelName").value = "pix2text_mixed";
  if (el("pdfModelDisplay")) el("pdfModelDisplay").value = "mixed（固定）";
  syncCustomSelectByIds("imageCopyFormatSelect", "imageCopyFormatTrigger", "imageCopyFormatPanel", "imageCopyFormat", "latex");
  syncCustomSelectByIds("pdfOutputFormatSelect", "pdfOutputFormatTrigger", "pdfOutputFormatPanel", "pdfOutputFormat", "markdown");
  syncCustomSelectByIds("pdfTemplateStyleSelect", "pdfTemplateStyleTrigger", "pdfTemplateStylePanel", "pdfTemplateStyle", "paper");
  syncCustomSelectByIds("envMirrorSelect", "envMirrorTrigger", "envMirrorPanel", "envMirror", "official");
  applyUiTuning();
}

function loadResultStore() {
  try {
    const raw = localStorage.getItem(RESULT_STORE_KEY);
    if (!raw) {
      state.resultHistory = [];
      renderResultLists();
      setCompactResultPreview("");
      return;
    }
    const parsed = JSON.parse(raw);
    const list = Array.isArray(parsed?.history) ? parsed.history : [];
    state.resultHistory = list.filter((x) => x && typeof x === "object").slice(0, 200);
  } catch (e) {
    state.resultHistory = [];
    log(`读取结果历史失败: ${e}`, "WARN");
  }
  renderResultLists();
  syncCompactResultPreviewFromHistory();
}

function saveResultStore() {
  try {
    localStorage.setItem(
      RESULT_STORE_KEY,
      JSON.stringify({
        history: Array.isArray(state.resultHistory) ? state.resultHistory.slice(0, 200) : [],
      })
    );
  } catch (e) {
    log(`保存结果历史失败: ${e}`, "WARN");
  }
}

function escHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function compactText(text, limit = 90) {
  const raw = String(text || "").replace(/\s+/g, " ").trim();
  if (raw.length <= limit) return raw;
  return `${raw.slice(0, limit - 1)}…`;
}

function setCompactResultPreview(text, source = "") {
  const node = el("compactResultText");
  if (!node) return;
  const raw = String(text || "").replace(/\r/g, "").trim();
  if (!raw) {
    node.textContent = "暂无识别结果";
    node.classList.add("is-empty");
    return;
  }
  const body = raw.length > 420 ? `${raw.slice(0, 420)}\n...` : raw;
  node.textContent = body;
  node.classList.remove("is-empty");
}

function syncCompactResultPreviewFromHistory() {
  const first = Array.isArray(state.resultHistory) && state.resultHistory.length > 0 ? state.resultHistory[0] : null;
  if (!first) {
    setCompactResultPreview("");
    return;
  }
  const text = first.preview || first.formats?.latex || first.formats?.markdown || "";
  setCompactResultPreview(text, first.source || "");
}

function renderResultLists() {
  const historyNode = el("resultHistoryList");
  if (!historyNode) return;
  const items = Array.isArray(state.resultHistory) ? state.resultHistory : [];
  if (!items.length) {
    historyNode.innerHTML = '<div class="result-empty">暂无记录</div>';
    return;
  }
  historyNode.innerHTML = items
    .map((item) => {
      const source = item.source === "pdf" ? "PDF" : "图片";
      const summary = compactText(item.preview || item.formats?.latex || item.formats?.markdown || "");
      return `
        <div class="result-item" data-id="${escHtml(item.id)}">
          <div class="result-item-head">
            <span class="result-tag">${source}</span>
            <span class="result-time">${escHtml(item.createdAt || "")}</span>
          </div>
          <div class="result-item-body">${escHtml(summary || "<empty>")}</div>
          <div class="result-item-actions">
            <button class="btn btn-secondary btn-compact result-copy" data-id="${escHtml(item.id)}">复制</button>
          </div>
        </div>
      `;
    })
    .join("");
}

function upsertResultSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object" || !snapshot.id) return;
  const list = Array.isArray(state.resultHistory) ? state.resultHistory : [];
  const idx = list.findIndex((x) => x?.id === snapshot.id);
  if (idx >= 0) {
    list[idx] = { ...list[idx], ...snapshot };
  } else {
    list.unshift(snapshot);
  }
  state.resultHistory = list.slice(0, 200);
  saveResultStore();
  renderResultLists();
  const previewText = snapshot.preview || snapshot.formats?.latex || snapshot.formats?.markdown || "";
  setCompactResultPreview(previewText, snapshot.source || "");
}

function findSnapshotById(id) {
  const key = String(id || "").trim();
  if (!key) return null;
  return (state.resultHistory || []).find((x) => x?.id === key) || null;
}

function clearResultHistory() {
  state.resultHistory = [];
  saveResultStore();
  renderResultLists();
  setCompactResultPreview("");
}

function getPreferredCopyFormatBySource(source) {
  if (source === "pdf") {
    return "markdown";
  }
  return String(el("imageCopyFormat")?.value || "latex").trim().toLowerCase() || "latex";
}

async function copySnapshotById(id) {
  const item = findSnapshotById(id);
  if (!item) throw new Error("记录不存在或已失效");
  const fmt = getPreferredCopyFormatBySource(item.source);
  const payload = {
    formats: normalizeFormatMap(item.formats),
    formatErrors: normalizeFormatMap(item.formatErrors),
    result: String(item.preview || ""),
    content: String(item.preview || ""),
  };
  const copied = await copyByFormat(payload, fmt, item.source === "pdf" ? "PDF记录" : "图片记录");
  log(`已从${item.source === "pdf" ? "PDF" : "图片"}记录复制（${copied.format}${copied.fallback ? "，回退" : ""}）`);
}

function bindResultListActions() {
  const clickHandler = async (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;
    const copyBtn = target.closest(".result-copy");
    const itemNode = target.closest(".result-item");
    if (copyBtn instanceof HTMLElement) {
      const id = copyBtn.dataset.id || "";
      try {
        await copySnapshotById(id);
      } catch (e) {
        log(`从记录复制失败: ${e}`, "WARN");
      }
      return;
    }
    if (itemNode instanceof HTMLElement) {
      const id = itemNode.dataset.id || "";
      try {
        await copySnapshotById(id);
      } catch (e) {
        log(`从记录复制失败: ${e}`, "WARN");
      }
    }
  };
  const historyNode = el("resultHistoryList");
  if (historyNode) historyNode.addEventListener("click", clickHandler);
}

function endpoint() {
  const imagePoll = getImagePollOptions();
  return {
    host: el("host").value.trim() || "127.0.0.1",
    port: Number(el("port").value || 0) || 43637,
    token: el("token").value.trim(),
    timeoutMs: clampNumber(imagePoll.timeoutMs, 3000, 180000, 20000),
  };
}

function contractPathOrNull() {
  const v = el("contractPath").value.trim();
  return v || null;
}

function isDaemonUnavailableError(err) {
  const msg = String(err || "").toLowerCase();
  return (
    msg.includes("10061") ||
    msg.includes("10060") ||
    msg.includes("connection refused") ||
    msg.includes("actively refused") ||
    msg.includes("timed out") ||
    msg.includes("time out") ||
    msg.includes("no response") ||
    msg.includes("没有正确答复") ||
    msg.includes("主机没有反应") ||
    msg.includes("无法连接") ||
    msg.includes("超时") ||
    msg.includes("积极拒绝") ||
    msg.includes("read response failed") ||
    msg.includes("connection attempt failed")
  );
}

function isImagePayloadMissingError(err) {
  const msg = String(err || "").toLowerCase();
  return msg.includes("image_path missing") || msg.includes("image_path/image_b64 missing");
}

function isUnsupportedTaskKindError(err) {
  const msg = String(err || "").toLowerCase();
  return msg.includes("unsupported task kind");
}

function isDaemonEncodingError(err) {
  const msg = String(err || "").toLowerCase();
  return msg.includes("gbk") && (msg.includes("unicodeencodeerror") || msg.includes("can't encode"));
}

function taskErrorCode(snap) {
  const direct = String(snap?.error_code || "").trim();
  if (direct) return direct;
  return String(snap?.raw?.task?.error_code || "").trim();
}

function taskDetails(snap) {
  const details = snap?.details;
  if (details && typeof details === "object") return details;
  const rawDetails = snap?.raw?.task?.details;
  if (rawDetails && typeof rawDetails === "object") return rawDetails;
  return {};
}

function isEnvInstallLockError(snap) {
  const code = taskErrorCode(snap).toUpperCase();
  if (code === "ENV_FILE_LOCKED" || code === "ENV_IN_USE" || code === "DAEMON_ENV_LOCKED") {
    return true;
  }
  const msg = `${snap?.error || ""}\n${JSON.stringify(taskDetails(snap) || {})}`.toLowerCase();
  return (
    msg.includes("winerror 5") ||
    msg.includes("拒绝访问") ||
    msg.includes("access is denied") ||
    msg.includes("target python is in use") ||
    msg.includes("loaded torch stack")
  );
}

async function ensureDaemonReady(reason = "operation", opts = {}) {
  if (state.daemonEnsurePromise) {
    return state.daemonEnsurePromise;
  }

  const task = (async () => {
    const ep = endpoint();
    const forceRestart = Boolean(opts && opts.forceRestart);
    const hsEp = {
      host: ep.host,
      port: ep.port,
      token: ep.token,
      timeoutMs: 12000,
    };
    const doHandshake = () =>
      invoke("daemon_health_handshake", {
        input: {
          endpoint: hsEp,
          contractPath: contractPathOrNull(),
        },
      });

    const tryShutdown = async () => {
      try {
        await invoke("daemon_shutdown", {
          input: { endpoint: ep },
        });
        log("已请求现有 daemon 关闭", "WARN");
      } catch (e) {
        log(`关闭已有 daemon 失败(可忽略): ${e}`, "WARN");
      }
    };

    const bootstrapAndWait = async () => {
      const boot = await invoke("daemon_bootstrap_local", {
        input: {
          endpoint: ep,
          model: "pix2text",
        },
      });
      log(`daemon bootstrap: ${boot?.message || "ok"}`, "INFO");

      let lastErr = null;
      for (let i = 0; i < 30; i++) {
        try {
          const hs = await doHandshake();
          if (hs?.contract_match === true) {
            return hs;
          }
          lastErr = new Error("daemon contract mismatch");
        } catch (e) {
          lastErr = e;
        }
        if (i === 0 || (i + 1) % 5 === 0) {
          log(`等待 daemon 就绪... (${i + 1}/30)`, "INFO");
        }
        await sleep(350);
      }
      throw new Error(`daemon 启动后仍不可达: ${lastErr || "unknown"}`);
    };

    try {
      const hs = await doHandshake();
      if (!forceRestart && hs?.contract_match === true) {
        return hs;
      }
      log("检测到旧版或不匹配 daemon，准备重启本地 daemon...", "WARN");
      await tryShutdown();
      await sleep(220);
      return await bootstrapAndWait();
    } catch (firstErr) {
      if (!forceRestart && !isDaemonUnavailableError(firstErr)) {
        throw firstErr;
      }
      log(`Daemon 不可用(${reason})，尝试自动拉起...`, "WARN");
      if (forceRestart) {
        await tryShutdown();
        await sleep(220);
      }
      return await bootstrapAndWait();
    }
  })();

  state.daemonEnsurePromise = task;
  try {
    return await task;
  } finally {
    state.daemonEnsurePromise = null;
  }
}

function setHealth(ok, text) {
  const tag = el("healthTag");
  tag.textContent = text;
  tag.classList.toggle("muted", !ok);
}

function setFxTag(fx) {
  const mode = String(fx || "none").toLowerCase();
  document.body.classList.remove("fx-mica", "fx-acrylic", "fx-none");
  if (mode === "mica") {
    document.body.classList.add("fx-mica");
  } else if (mode === "acrylic") {
    document.body.classList.add("fx-acrylic");
  } else {
    document.body.classList.add("fx-none");
  }
  state.fxApplied = mode;
  state.fxMode = mode === "mica" ? "mica" : "acrylic";
  const fxSwitch = document.querySelector(".fx-switch");
  if (fxSwitch) fxSwitch.setAttribute("data-active", state.fxMode === "mica" ? "1" : "0");
  const acrylicBtn = el("btnFxAcrylic");
  const micaBtn = el("btnFxMica");
  if (acrylicBtn) acrylicBtn.classList.toggle("active", state.fxMode === "acrylic");
  if (micaBtn) micaBtn.classList.toggle("active", state.fxMode === "mica");
}

function setWindowModeTag(compact) {
  const isCompact = !!compact;
  state.compactMode = isCompact;
  document.body.classList.toggle("compact-mode", isCompact);
  const modeSwitch = document.querySelector(".window-mode-switch");
  if (modeSwitch) modeSwitch.setAttribute("data-active", isCompact ? "1" : "0");
  const normalBtn = el("btnModeNormal");
  const compactBtn = el("btnModeCompact");
  if (normalBtn) normalBtn.classList.toggle("active", !isCompact);
  if (compactBtn) compactBtn.classList.toggle("active", isCompact);
}

async function applyWindowMode(compact, options = {}) {
  const persist = !!options.persist;
  const silent = !!options.silent;
  const targetCompact = !!compact;
  try {
    const applied = await invoke("set_window_compact_mode", {
      input: { compact: targetCompact },
    });
    setWindowModeTag(Boolean(applied));
    if (!silent) setActionTag(`已切换为${targetCompact ? "小窗模式" : "正常窗口"}`, "ok");
    if (persist) saveSettings();
  } catch (e) {
    if (!silent) {
      log(`切换窗口模式失败: ${e}`, "WARN");
      setActionTag("切换窗口模式失败", "warn");
    }
  }
}

function setUiValueText(id, v, suffix = "") {
  const n = el(id);
  if (!n) return;
  n.textContent = `${v}${suffix}`;
}

function applyUiTuning() {
  const bg = Number(el("uiBgAlpha")?.value ?? state.uiBgAlpha ?? 0.20);
  const side = Number(el("uiSidebarAlpha")?.value ?? state.uiSidebarAlpha ?? 0.20);
  const panel = Number(el("uiPanelAlpha")?.value ?? state.uiPanelAlpha ?? 0.33);
  const blur = Number(el("uiBlurPx")?.value ?? state.uiBlurPx ?? 26);
  const radius = Number(el("uiRadiusPx")?.value ?? state.uiRadiusPx ?? 12);
  const brightness = Number(el("uiBrightness")?.value ?? state.uiBrightness ?? 1.18);
  const contrast = Number(el("uiContrast")?.value ?? state.uiContrast ?? 1.2);
  const saturate = Number(el("uiSaturatePct")?.value ?? state.uiSaturatePct ?? 40);
  const tint = Number(el("uiTintAlpha")?.value ?? state.uiTintAlpha ?? 0.0);
  const noise = Number(el("uiNoiseAlpha")?.value ?? state.uiNoiseAlpha ?? 0.02);
  const blurEffective = Math.round(blur * 1.45);
  const cardBlur = Math.max(4, Math.round(blur * 0.58));
  const saturateEffective = Math.round(saturate * 1.25);
  const brightnessEffective = (0.35 + brightness * 0.95).toFixed(2);
  const toneAlpha = Math.max(
    0,
    Math.min(0.32, ((saturateEffective - 100) / 180) * 0.3 + tint * 0.3)
  ).toFixed(2);
  const root = document.documentElement.style;
  root.setProperty("--ui-bg-alpha", String(bg));
  root.setProperty("--ui-sidebar-alpha", String(side));
  root.setProperty("--ui-panel-alpha", String(panel));
  root.setProperty("--ui-blur", `${blurEffective}px`);
  root.setProperty("--ui-card-blur", `${cardBlur}px`);
  root.setProperty("--ui-radius", `${radius}px`);
  root.setProperty("--ui-brightness", brightnessEffective);
  root.setProperty("--ui-contrast", contrast.toFixed(2));
  root.setProperty("--ui-saturate", `${saturateEffective}%`);
  root.setProperty("--ui-tint-alpha", tint.toFixed(2));
  root.setProperty("--ui-noise-alpha", noise.toFixed(2));
  root.setProperty("--ui-tone-alpha", toneAlpha);
  setUiValueText("uiBgAlphaVal", bg.toFixed(2));
  setUiValueText("uiSidebarAlphaVal", side.toFixed(2));
  setUiValueText("uiPanelAlphaVal", panel.toFixed(2));
  setUiValueText("uiBlurPxVal", blur, "px");
  setUiValueText("uiRadiusPxVal", radius, "px");
  setUiValueText("uiBrightnessVal", brightness.toFixed(2));
  setUiValueText("uiContrastVal", contrast.toFixed(2));
  setUiValueText("uiSaturatePctVal", Math.round(saturate), "%");
  setUiValueText("uiTintAlphaVal", tint.toFixed(2));
  setUiValueText("uiNoiseAlphaVal", noise.toFixed(2));
}

function setHotkeyStatusText(text) {
  const node = el("hotkeyStatus");
  if (node) node.value = text || "";
}

async function onLoadContract() {
  try {
    saveSettings();
    const result = await invoke("load_rpc_contract", { contractPath: contractPathOrNull() });
    el("handshakeOutput").textContent = JSON.stringify(result, null, 2);
    log(`Contract loaded: ${result.name}@${result.version}`);
  } catch (e) {
    log(`读取 contract 失败: ${e}`, "ERROR");
    el("handshakeOutput").textContent = String(e);
  }
}

async function onHandshake() {
  if (state.handshakeBusy) {
    log("握手任务正在进行中，请稍候...", "WARN");
    return;
  }
  state.handshakeBusy = true;
  const btn = el("btnHandshake");
  const oldBtnHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "握手中...";
  }
  try {
    saveSettings();
    const result = await ensureDaemonReady("health");
    el("handshakeOutput").textContent = JSON.stringify(result, null, 2);
    const ok = Boolean(result.ok && result.contract_match);
    setHealth(ok, ok ? "Daemon: 握手通过" : "Daemon: 握手失败");
    log(`Health handshake done, match=${result.contract_match}`);
    setActionTag(ok ? "握手成功" : "握手失败", ok ? "ok" : "warn");
  } catch (e) {
    if (isDaemonUnavailableError(e)) {
      try {
        log("握手超时/连接异常，尝试强制重启 daemon 后重试...", "WARN");
        const retry = await ensureDaemonReady("health_retry", { forceRestart: true });
        el("handshakeOutput").textContent = JSON.stringify(retry, null, 2);
        const okRetry = Boolean(retry.ok && retry.contract_match);
        setHealth(okRetry, okRetry ? "Daemon: 握手通过" : "Daemon: 握手失败");
        log(`Health handshake retry done, match=${retry.contract_match}`);
        setActionTag(okRetry ? "握手成功" : "握手失败", okRetry ? "ok" : "warn");
        return;
      } catch (retryErr) {
        e = retryErr;
      }
    }
    setHealth(false, "Daemon: 握手异常");
    log(`Health handshake 失败: ${e}`, "ERROR");
    el("handshakeOutput").textContent = String(e);
    setActionTag("握手失败", "error");
  } finally {
    state.handshakeBusy = false;
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = oldBtnHtml;
    }
  }
}

function setImageButtonsBusy(busy) {
  const submitBtn = el("btnSubmitTask");
  const pollBtn = el("btnPollTask");
  const submitAndPollBtn = el("btnSubmitAndPoll");
  const hotkeyBtn = el("btnHotkeyCapturePredict");
  const cancelBtn = el("btnCancelTask");
  if (submitBtn) submitBtn.disabled = !!busy;
  if (pollBtn) pollBtn.disabled = !!busy;
  if (submitAndPollBtn) submitAndPollBtn.disabled = !!busy;
  if (hotkeyBtn) hotkeyBtn.disabled = !!busy;
  if (cancelBtn) cancelBtn.disabled = false;
}

async function pollImageTaskNonBlocking(taskId, options, context = "image") {
  const pollIntervalMs = clampNumber(options?.pollIntervalMs, 50, 5000, 200);
  const timeoutMs = clampNumber(options?.timeoutMs, IMAGE_TIMEOUT_MIN_MS, IMAGE_TIMEOUT_MAX_MS, IMAGE_TIMEOUT_DEFAULT_MS);
  const startedAt = Date.now();

  while (true) {
    const snap = await invoke("daemon_task_status", {
      input: {
        endpoint: endpoint(),
        taskId,
      },
    });
    el("taskOutput").textContent = JSON.stringify(snap, null, 2);

    const status = String(snap?.status || "");
    if (isTerminalTaskStatus(status)) {
      return snap;
    }
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error(`${context} 任务轮询超时: ${timeoutMs}ms`);
    }
    await sleep(pollIntervalMs);
  }
}

async function onSubmitTask() {
  try {
    saveSettings();
    await ensureDaemonReady("submit_task");
    const imagePath = el("imagePath").value.trim();
    if (!imagePath) throw new Error("请填写图片路径");
    const modelName = el("modelName").value;
    const out = await invoke("daemon_task_submit", {
      input: {
        endpoint: endpoint(),
        kind: "predict_image",
        params: {
          image_path: imagePath,
          model_name: modelName,
        },
      },
    });
    state.currentTaskId = out.task_id || "";
    el("taskId").value = state.currentTaskId;
    el("taskOutput").textContent = JSON.stringify(out, null, 2);
    log(`任务已提交: ${state.currentTaskId}`);
  } catch (e) {
    log(`提交任务失败: ${e}`, "ERROR");
    el("taskOutput").textContent = String(e);
  }
}

async function onPollTask() {
  if (state.imagePollInFlight) {
    log("图片轮询已在进行中，请稍候...", "WARN");
    return;
  }
  try {
    state.imagePollInFlight = true;
    setImageButtonsBusy(true);
    saveSettings();
    await ensureDaemonReady("poll_task");
    const taskId = el("taskId").value.trim();
    if (!taskId) throw new Error("请先提供 taskId");
    const out = await pollImageTaskNonBlocking(taskId, getImagePollOptions());
    el("taskOutput").textContent = JSON.stringify(out, null, 2);
    const status = out?.status || "unknown";
    log(`任务轮询结束: ${taskId} status=${status}`);
    if (String(status).toLowerCase() === "success") {
      addResultSnapshot(
        "image",
        {
          result: String(out?.output?.result || ""),
          formats: normalizeFormatMap(out?.output?.result_formats),
          formatErrors: normalizeFormatMap(out?.output?.result_format_errors),
        },
        taskId
      );
      const autoCopied = await autoCopyImageLatexFromTask(out);
      setActionTag(
        autoCopied.ok ? "图片识别完成，LaTeX已复制" : "图片识别完成（复制失败）",
        autoCopied.ok ? "ok" : "warn"
      );
    }
  } catch (e) {
    log(`轮询任务失败: ${e}`, "ERROR");
    el("taskOutput").textContent = String(e);
    setActionTag("图片识别失败", "error");
  } finally {
    state.imagePollInFlight = false;
    setImageButtonsBusy(false);
  }
}

async function onSubmitAndPoll() {
  if (state.imagePollInFlight) {
    log("图片提交并轮询已在进行中，请稍候...", "WARN");
    return;
  }
  try {
    state.imagePollInFlight = true;
    setImageButtonsBusy(true);
    saveSettings();
    await ensureDaemonReady("submit_and_poll");
    const imagePath = el("imagePath").value.trim();
    if (!imagePath) throw new Error("请填写图片路径");
    const modelName = el("modelName").value;
    const submit = await invoke("daemon_task_submit", {
      input: {
        endpoint: endpoint(),
        kind: "predict_image",
        params: {
          image_path: imagePath,
          model_name: modelName,
        },
      },
    });
    const taskId = String(submit?.task_id || "");
    if (!taskId) throw new Error("图片任务提交失败: 空 task_id");
    state.currentTaskId = taskId;
    el("taskId").value = taskId;
    log(`任务已提交: ${taskId}`);
    const out = await pollImageTaskNonBlocking(
      taskId,
      getImagePollOptions(),
      "image"
    );
    el("taskOutput").textContent = JSON.stringify(out, null, 2);
    const result = out?.output?.result ?? "";
    log(`识别完成，结果长度=${String(result).length}`);
    if (String(out?.status || "").toLowerCase() === "success") {
      addResultSnapshot(
        "image",
        {
          result: String(result || ""),
          formats: normalizeFormatMap(out?.output?.result_formats),
          formatErrors: normalizeFormatMap(out?.output?.result_format_errors),
        },
        taskId
      );
      const autoCopied = await autoCopyImageLatexFromTask(out);
      setActionTag(
        autoCopied.ok ? "图片识别完成，LaTeX已复制" : "图片识别完成（复制失败）",
        autoCopied.ok ? "ok" : "warn"
      );
    }
  } catch (e) {
    log(`提交并轮询失败: ${e}`, "ERROR");
    el("taskOutput").textContent = String(e);
    setActionTag("图片识别失败", "error");
  } finally {
    state.imagePollInFlight = false;
    setImageButtonsBusy(false);
  }
}

async function onCancelTask() {
  try {
    await ensureDaemonReady("cancel_task");
    const taskId = (el("taskId")?.value || "").trim() || String(state.currentTaskId || "").trim();
    if (!taskId) throw new Error("请先提供 taskId");
    if (!(el("taskId")?.value || "").trim()) {
      el("taskId").value = taskId;
    }
    const out = await invoke("daemon_task_cancel", {
      input: { endpoint: endpoint(), taskId },
    });
    el("taskOutput").textContent = JSON.stringify({ ok: out, task_id: taskId }, null, 2);
    log(`取消任务请求已发送: ${taskId}`);
    setActionTag("已取消图片任务", "warn");
  } catch (e) {
    log(`取消任务失败: ${e}`, "ERROR");
    el("taskOutput").textContent = String(e);
    setActionTag("取消图片任务失败", "error");
  }
}

function getPdfPollOptions() {
  const pollIntervalMs = clampNumber(el("pollIntervalMs")?.value, 50, 5000, 200);
  return { pollIntervalMs };
}

function isTerminalTaskStatus(status) {
  const s = String(status || "").toLowerCase();
  return s === "success" || s === "error" || s === "cancelled";
}

function setPdfButtonsBusy(busy) {
  const submitBtn = el("btnSubmitPdfTask");
  const pollBtn = el("btnPollPdfTask");
  const submitAndPollBtn = el("btnSubmitAndPollPdf");
  const cancelBtn = el("btnCancelPdfTask");
  if (submitBtn) submitBtn.disabled = !!busy;
  if (pollBtn) pollBtn.disabled = !!busy;
  if (submitAndPollBtn) submitAndPollBtn.disabled = !!busy;
  if (cancelBtn) cancelBtn.disabled = false;
}

async function pollPdfTaskNonBlocking(taskId, options) {
  const pollIntervalMs = clampNumber(options?.pollIntervalMs, 50, 5000, 200);

  while (true) {
    const snap = await invoke("daemon_task_status", {
      input: {
        endpoint: endpoint(),
        taskId,
      },
    });
    el("pdfTaskOutput").textContent = JSON.stringify(snap, null, 2);

    const status = String(snap?.status || "");
    const cur = Number(snap?.progress_current || 0);
    const total = Number(snap?.progress_total || 0);
    if (!isTerminalTaskStatus(status)) {
      log(`PDF 任务进度: ${taskId} ${cur}/${total} (${status || "running"})`);
    }

    if (isTerminalTaskStatus(status)) {
      return snap;
    }
    await sleep(pollIntervalMs);
  }
}

function getPdfSubmitParams() {
  const pdfPath = (el("pdfPath")?.value || "").trim();
  if (!pdfPath) {
    throw new Error("请填写 PDF 路径");
  }
  const modelName = "pix2text_mixed";
  const outputFormat = (el("pdfOutputFormat")?.value || "markdown").trim() || "markdown";
  const maxPages = Math.max(0, Number(el("pdfMaxPages")?.value || 0) || 0);
  const dpi = Math.max(72, Number(el("pdfDpi")?.value || 200) || 200);
  const { pollIntervalMs } = getPdfPollOptions();
  return {
    pdfPath,
    modelName,
    outputFormat,
    maxPages,
    dpi,
    pollIntervalMs,
  };
}

async function onSubmitPdfTask() {
  try {
    saveSettings();
    await ensureDaemonReady("submit_pdf_task");
    const p = getPdfSubmitParams();
    const out = await invoke("daemon_task_submit", {
      input: {
        endpoint: endpoint(),
        kind: "predict_pdf",
        params: {
          pdf_path: p.pdfPath,
          max_pages: p.maxPages,
          model_name: p.modelName,
          output_format: p.outputFormat,
          dpi: p.dpi,
        },
      },
    });
    state.currentPdfTaskId = out.task_id || "";
    el("pdfTaskId").value = state.currentPdfTaskId;
    el("pdfTaskOutput").textContent = JSON.stringify(out, null, 2);
    log(`PDF 任务已提交: ${state.currentPdfTaskId}`);
  } catch (e) {
    log(`提交 PDF 任务失败: ${e}`, "ERROR");
    el("pdfTaskOutput").textContent = String(e);
  }
}

async function onPollPdfTask() {
  if (state.pdfPollInFlight) {
    log("PDF 轮询已在进行中，请稍候...", "WARN");
    return;
  }
  try {
    state.pdfPollInFlight = true;
    setPdfButtonsBusy(true);
    saveSettings();
    await ensureDaemonReady("poll_pdf_task");
    const taskId = (el("pdfTaskId")?.value || "").trim();
    if (!taskId) throw new Error("请先提供 PDF taskId");
    const p = getPdfPollOptions();
    const out = await pollPdfTaskNonBlocking(taskId, p);
    el("pdfTaskOutput").textContent = JSON.stringify(out, null, 2);
    const status = out?.status || "unknown";
    const pages = Number(out?.output?.pages || 0);
    log(`PDF 任务轮询结束: ${taskId} status=${status} pages=${pages}`);
    if (String(status).toLowerCase() === "success") {
      addResultSnapshot(
        "pdf",
        {
          content: String(out?.output?.content || ""),
          format: String(out?.output?.output_format || "markdown"),
          formats: normalizeFormatMap(out?.output?.content_formats),
          formatErrors: normalizeFormatMap(out?.output?.content_format_errors),
        },
        taskId
      );
      setActionTag("PDF 识别完成", "ok");
    }
  } catch (e) {
    log(`轮询 PDF 任务失败: ${e}`, "ERROR");
    el("pdfTaskOutput").textContent = String(e);
    setActionTag("PDF 识别失败", "error");
  } finally {
    state.pdfPollInFlight = false;
    setPdfButtonsBusy(false);
  }
}

async function onSubmitAndPollPdf() {
  if (state.pdfPollInFlight) {
    log("PDF 提交并轮询已在进行中，请稍候...", "WARN");
    return;
  }
  try {
    state.pdfPollInFlight = true;
    setPdfButtonsBusy(true);
    saveSettings();
    await ensureDaemonReady("submit_and_poll_pdf");
    const p = getPdfSubmitParams();
    const submit = await invoke("daemon_task_submit", {
      input: {
        endpoint: endpoint(),
        kind: "predict_pdf",
        params: {
          pdf_path: p.pdfPath,
          max_pages: p.maxPages,
          model_name: p.modelName,
          output_format: p.outputFormat,
          dpi: p.dpi,
        },
      },
    });
    const taskId = String(submit?.task_id || "");
    if (!taskId) throw new Error("PDF 任务提交失败: 空 task_id");
    state.currentPdfTaskId = taskId;
    el("pdfTaskId").value = taskId;
    log(`PDF 任务已提交: ${taskId}`);
    const out = await pollPdfTaskNonBlocking(taskId, {
      pollIntervalMs: p.pollIntervalMs,
    });
    el("pdfTaskOutput").textContent = JSON.stringify(out, null, 2);
    const content = String(out?.output?.content || "");
    const pages = Number(out?.output?.pages || 0);
    log(`PDF 识别完成: pages=${pages}, content_len=${content.length}`);
    if (String(out?.status || "").toLowerCase() === "success") {
      addResultSnapshot(
        "pdf",
        {
          content,
          format: String(out?.output?.output_format || "markdown"),
          formats: normalizeFormatMap(out?.output?.content_formats),
          formatErrors: normalizeFormatMap(out?.output?.content_format_errors),
        },
        taskId
      );
      setActionTag("PDF 识别完成", "ok");
    }
  } catch (e) {
    log(`提交并轮询 PDF 失败: ${e}`, "ERROR");
    el("pdfTaskOutput").textContent = String(e);
    setActionTag("PDF 识别失败", "error");
  } finally {
    state.pdfPollInFlight = false;
    setPdfButtonsBusy(false);
  }
}

async function onCancelPdfTask() {
  try {
    await ensureDaemonReady("cancel_pdf_task");
    const taskId = (el("pdfTaskId")?.value || "").trim() || String(state.currentPdfTaskId || "").trim();
    if (!taskId) throw new Error("请先提供 PDF taskId");
    if (!(el("pdfTaskId")?.value || "").trim()) {
      el("pdfTaskId").value = taskId;
    }
    const out = await invoke("daemon_task_cancel", {
      input: { endpoint: endpoint(), taskId },
    });
    el("pdfTaskOutput").textContent = JSON.stringify({ ok: out, task_id: taskId }, null, 2);
    log(`取消 PDF 任务请求已发送: ${taskId}`);
    setActionTag("已取消 PDF 任务", "warn");
  } catch (e) {
    log(`取消 PDF 任务失败: ${e}`, "ERROR");
    el("pdfTaskOutput").textContent = String(e);
    setActionTag("取消 PDF 任务失败", "error");
  }
}

async function onPickImagePath() {
  try {
    const out = await invoke("pick_file", {
      input: { kind: "image" },
    });
    if (typeof out === "string" && out.trim()) {
      el("imagePath").value = out.trim();
      log(`已选择图片: ${out}`);
    }
  } catch (e) {
    log(`选择图片失败: ${e}`, "WARN");
  }
}

async function onPickPdfPath() {
  try {
    const out = await invoke("pick_file", {
      input: { kind: "pdf" },
    });
    if (typeof out === "string" && out.trim()) {
      el("pdfPath").value = out.trim();
      log(`已选择 PDF: ${out}`);
    }
  } catch (e) {
    log(`选择 PDF 失败: ${e}`, "WARN");
  }
}

function safeParseJson(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function getTaskSnapshotFromOutput(nodeId) {
  const text = String(el(nodeId)?.textContent || "");
  const parsed = safeParseJson(text);
  if (!parsed || typeof parsed !== "object") return null;
  if (parsed.task_id && parsed.status) return parsed;
  if (parsed.raw?.task && parsed.raw.task.status) return parsed.raw.task;
  return null;
}

function extractImageResultPayload() {
  const snap = getTaskSnapshotFromOutput("taskOutput");
  if (!snap) return { result: "", formats: {}, formatErrors: {} };
  const out = snap.output || snap.raw?.task?.output || {};
  const result = typeof out?.result === "string" ? out.result : "";
  const formats = out?.result_formats && typeof out.result_formats === "object" ? out.result_formats : {};
  const formatErrors =
    out?.result_format_errors && typeof out.result_format_errors === "object" ? out.result_format_errors : {};
  return { result, formats: normalizeFormatMap(formats), formatErrors };
}

function normalizeFormatMap(input) {
  const out = {};
  if (!input || typeof input !== "object") return out;
  for (const [k, v] of Object.entries(input)) {
    if (typeof v === "string") out[String(k)] = v;
  }
  return out;
}

function trimFormatMapForStore(input, maxLen = 120000) {
  const out = {};
  for (const [k, v] of Object.entries(normalizeFormatMap(input))) {
    const raw = String(v || "");
    out[k] = raw.length > maxLen ? `${raw.slice(0, maxLen)}\n...<truncated>` : raw;
  }
  return out;
}

function extractPdfResultPayload() {
  const snap = getTaskSnapshotFromOutput("pdfTaskOutput");
  if (!snap) return { content: "", format: "markdown", formats: {}, formatErrors: {} };
  const out = snap.output || snap.raw?.task?.output || {};
  const content = typeof out?.content === "string" ? out.content : "";
  const format = typeof out?.output_format === "string" ? out.output_format : (el("pdfOutputFormat")?.value || "markdown");
  const result = {
    content,
    format: String(format || "markdown").toLowerCase(),
    formats: normalizeFormatMap(out?.content_formats),
    formatErrors: normalizeFormatMap(out?.content_format_errors),
  };
  if (!result.formats.markdown) {
    result.formats.markdown = result.format === "markdown" ? content : toMarkdownFromLatex(content);
  }
  if (!result.formats.latex) {
    result.formats.latex = result.format === "markdown" ? toLatexFromMarkdown(content) : content;
  }
  return result;
}

function toMarkdownFromLatex(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  return `$$\n${raw}\n$$\n`;
}

function toLatexFromMarkdown(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";
  return raw.replace(/^\s*\$\$\s*/m, "").replace(/\s*\$\$\s*$/m, "").trim();
}

function wrapPdfDocumentOutput(content, fmtKey, styleKey) {
  const text = String(content || "").trim();
  if (!text) return "";
  const fmt = String(fmtKey || "markdown").trim().toLowerCase();
  const style = String(styleKey || "paper").trim().toLowerCase();
  if (fmt === "markdown") {
    if (style === "paper") {
      return `# Title\n\n## Abstract\n\n${text}\n\n## References\n`;
    }
    return `# Title\n\n${text}`;
  }
  if (text.includes("\\documentclass") && text.includes("\\begin{document}")) {
    return text;
  }
  const docclass = style === "journal" ? "\\documentclass[journal]{IEEEtran}" : "\\documentclass[11pt]{article}";
  const preamble =
    `${docclass}\n` +
    "\\usepackage{amsmath,amssymb}\n" +
    "\\usepackage{geometry}\n" +
    "\\geometry{a4paper, margin=1in}\n" +
    "\\begin{document}\n";
  return `${preamble}${text}\n\\end{document}\n`;
}

async function saveTextContent(content, suggestedName) {
  const text = String(content || "");
  if (!text.trim()) {
    throw new Error("没有可导出的内容");
  }
  const out = await invoke("save_text_file", {
    input: {
      content: text,
      suggestedName: suggestedName || "output.txt",
    },
  });
  if (out) {
    log(`文件已保存: ${out}`);
  } else {
    log("用户取消保存", "WARN");
  }
}

function buildWordOmmlClipboardHtml(omml) {
  const mathXml = String(omml || "").trim();
  return (
    "<html xmlns:o='urn:schemas-microsoft-com:office:office' " +
    "xmlns:w='urn:schemas-microsoft-com:office:word' " +
    "xmlns:m='http://schemas.openxmlformats.org/officeDocument/2006/math'>" +
    "<head><meta charset='utf-8'></head><body><p>" +
    mathXml +
    "</p></body></html>"
  );
}

async function copyWordOmmlWithFallback(formats, fallbackText, label = "结果") {
  const omml = String(formats?.omml || "").trim();
  const mathml = String(formats?.mathml || "").trim();
  if (omml && navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
    try {
      const html = buildWordOmmlClipboardHtml(omml);
      const item = new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([omml], { type: "text/plain" }),
      });
      await navigator.clipboard.write([item]);
      return { used: "omml", fallback: false };
    } catch (e) {
      log(`${label} OMML 富文本复制失败，自动回退: ${e}`, "WARN");
    }
  }
  if (mathml) {
    await navigator.clipboard.writeText(mathml);
    return { used: "mathml", fallback: true };
  }
  const plain = String(fallbackText || omml || "").trim();
  if (!plain) throw new Error("没有可复制内容");
  await navigator.clipboard.writeText(plain);
  return { used: "latex", fallback: true };
}

async function copyByFormat(payload, preferredFormat, label) {
  const fmt = String(preferredFormat || "").trim().toLowerCase() || "latex";
  const formats = normalizeFormatMap(payload?.formats);
  const fallback = String(payload?.result || payload?.content || "").trim();
  if (fmt === "omml") {
    const ommlResult = await copyWordOmmlWithFallback(formats, fallback, label);
    return { format: ommlResult.used, fallback: ommlResult.fallback };
  }
  let text = String(formats[fmt] || "").trim();
  if (!text) {
    if (fmt === "markdown") text = String(formats.markdown || "").trim();
    else if (fmt === "latex") text = String(formats.latex || fallback).trim();
    else text = fallback;
  }
  if (!text) throw new Error("当前没有可复制内容");
  await navigator.clipboard.writeText(text);
  return { format: text === fallback && fmt !== "latex" ? "latex" : fmt, fallback: text === fallback && fmt !== "latex" };
}

async function autoCopyImageLatexFromTask(out) {
  const payload = {
    result: String(out?.output?.result || ""),
    formats: normalizeFormatMap(out?.output?.result_formats),
    formatErrors: normalizeFormatMap(out?.output?.result_format_errors),
  };
  try {
    const copied = await copyByFormat(payload, "latex", "图片结果");
    if (copied.fallback) {
      log("图片识别完成，已自动复制（latex 回退）", "WARN");
    } else {
      log("图片识别完成，已自动复制 LaTeX");
    }
    return { ok: true, copied };
  } catch (e) {
    log(`图片识别完成，但自动复制失败: ${e}`, "WARN");
    return { ok: false, error: String(e) };
  }
}

function addResultSnapshot(source, payload, taskId = "") {
  const nowText = new Date().toLocaleString();
  const formats = trimFormatMapForStore(payload?.formats);
  const mode = String(payload?.format || "").toLowerCase();
  const plain = String(payload?.result || payload?.content || "").trim();
  if (source === "image") {
    if (!formats.latex && plain) formats.latex = plain;
    if (!formats.markdown && plain) formats.markdown = toMarkdownFromLatex(plain);
  } else if (source === "pdf") {
    if (!formats.markdown && plain) {
      formats.markdown = mode === "latex" ? toMarkdownFromLatex(plain) : plain;
    }
    if (!formats.latex && plain) {
      formats.latex = mode === "markdown" ? toLatexFromMarkdown(plain) : plain;
    }
  }
  const previewRaw = String(payload?.result || payload?.content || formats.latex || formats.markdown || "").trim();
  const preview = previewRaw.length > 30000 ? `${previewRaw.slice(0, 30000)}\n...<truncated>` : previewRaw;
  const id = taskId ? `${source}:${taskId}` : `${source}:${Date.now().toString(36)}:${Math.random().toString(16).slice(2, 8)}`;
  upsertResultSnapshot({
    id,
    source: source === "pdf" ? "pdf" : "image",
    taskId: String(taskId || ""),
    createdAt: nowText,
    preview,
    formats,
    formatErrors: payload?.formatErrors || {},
  });
}

async function onCopyImageResult() {
  try {
    const payload = extractImageResultPayload();
    const fmt = String(el("imageCopyFormat")?.value || "latex").trim().toLowerCase() || "latex";
    const copied = await copyByFormat(payload, fmt, "图片结果");
    if (payload.formatErrors && payload.formatErrors[fmt] && copied.format !== fmt) {
      log(`已复制 ${copied.format}（${fmt} 转换失败，已降级）`, "WARN");
      setActionTag(`已复制（${copied.format}，回退）`, "warn");
    } else if (copied.fallback) {
      log(`图片识别结果已复制（${copied.format}，回退）`, "WARN");
      setActionTag(`已复制（${copied.format}，回退）`, "warn");
    } else {
      log(`图片识别结果已复制（${copied.format}）`);
      setActionTag(`已复制 ${copied.format}`, "ok");
    }
  } catch (e) {
    log(`复制图片结果失败: ${e}`, "WARN");
    setActionTag("复制结果失败", "warn");
  }
}

async function onSavePdfMarkdown() {
  try {
    const { content, format } = extractPdfResultPayload();
    if (!content.trim()) throw new Error("当前没有 PDF 识别结果");
    const style = String(el("pdfTemplateStyle")?.value || "paper").trim() || "paper";
    const core = format === "latex" ? toMarkdownFromLatex(content) : content;
    const out = wrapPdfDocumentOutput(core, "markdown", style);
    await saveTextContent(out, "pdf_result.md");
    log(`PDF Markdown 已保存（模板=${style}）`);
    setActionTag("PDF Markdown 已保存", "ok");
  } catch (e) {
    log(`保存 PDF Markdown 失败: ${e}`, "ERROR");
    setActionTag("保存 PDF Markdown 失败", "error");
  }
}

async function onSavePdfLatex() {
  try {
    const { content, format } = extractPdfResultPayload();
    if (!content.trim()) throw new Error("当前没有 PDF 识别结果");
    const style = String(el("pdfTemplateStyle")?.value || "paper").trim() || "paper";
    const core = format === "markdown" ? toLatexFromMarkdown(content) : content;
    const out = wrapPdfDocumentOutput(core, "latex", style);
    await saveTextContent(out, "pdf_result.tex");
    log(`PDF LaTeX 已保存（模板=${style}）`);
    setActionTag("PDF LaTeX 已保存", "ok");
  } catch (e) {
    log(`保存 PDF LaTeX 失败: ${e}`, "ERROR");
    setActionTag("保存 PDF LaTeX 失败", "error");
  }
}

function setMetricBar(id, pct) {
  const node = el(id);
  if (!node) return;
  const clamped = Math.max(0, Math.min(100, Number(pct || 0)));
  node.style.width = `${clamped.toFixed(1)}%`;
}

function fmtMB(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n) || n < 0) return "0 MB";
  if (n >= 1024) return `${(n / 1024).toFixed(1)} GB`;
  return `${Math.round(n)} MB`;
}

async function refreshSystemMetrics() {
  try {
    const data = await invoke("get_system_usage");
    const cpu = Number(data?.cpu_percent || 0);
    const memPct = Number(data?.memory_percent || 0);
    const gpu = data?.gpu_percent == null ? null : Number(data?.gpu_percent || 0);

    if (el("metricCpuText")) el("metricCpuText").textContent = `${cpu.toFixed(1)}%`;
    if (el("metricMemText")) {
      el("metricMemText").textContent =
        `${memPct.toFixed(1)}% (${fmtMB(data?.memory_used_mb)}/${fmtMB(data?.memory_total_mb)})`;
    }
    if (el("metricGpuText")) el("metricGpuText").textContent = gpu == null ? "N/A" : `${gpu.toFixed(1)}%`;

    const gpuName = String(data?.gpu_name || "").trim();
    const gpuSrc = String(data?.gpu_source || "");
    if (el("metricGpuName")) {
      if (gpuName) {
        const memInfo =
          data?.gpu_memory_used_mb != null && data?.gpu_memory_total_mb != null
            ? ` | 显存 ${fmtMB(data.gpu_memory_used_mb)}/${fmtMB(data.gpu_memory_total_mb)}`
            : "";
        el("metricGpuName").textContent = `GPU: ${gpuName}${memInfo} (${gpuSrc || "unknown"})`;
      } else {
        el("metricGpuName").textContent = `GPU: 不可用 (${gpuSrc || "unavailable"})`;
      }
    }

    setMetricBar("metricCpuBar", cpu);
    setMetricBar("metricMemBar", memPct);
    setMetricBar("metricGpuBar", gpu == null ? 0 : gpu);
  } catch (e) {
    if (el("metricGpuName")) {
      el("metricGpuName").textContent = `系统资源读取失败: ${e}`;
    }
  }
}

function startSystemMetricsPolling() {
  if (state.metricsTimer) {
    clearInterval(state.metricsTimer);
    state.metricsTimer = null;
  }
  refreshSystemMetrics();
  state.metricsTimer = setInterval(() => {
    refreshSystemMetrics();
  }, 1000);
}

async function onLoadAboutInfo() {
  try {
    const out = await invoke("get_app_info");
    if (el("aboutAppName")) el("aboutAppName").value = String(out?.name || "");
    if (el("aboutAppVersion")) el("aboutAppVersion").value = String(out?.version || "");
    if (el("aboutPlatform")) el("aboutPlatform").value = `${String(out?.os || "")}/${String(out?.arch || "")}`;
    if (el("aboutBuildProfile")) el("aboutBuildProfile").value = String(out?.profile || "");
  } catch (e) {
    log(`读取程序信息失败: ${e}`, "WARN");
  }
}

async function onOpenUpdateUrl() {
  try {
    const url = (el("aboutUpdateUrl")?.value || "").trim();
    if (!url) throw new Error("更新地址为空");
    await invoke("open_external_url", { url });
    log(`已打开更新地址: ${url}`);
  } catch (e) {
    log(`打开更新地址失败: ${e}`, "ERROR");
  }
}

async function onCopyUpdateUrl() {
  try {
    const url = (el("aboutUpdateUrl")?.value || "").trim();
    if (!url) throw new Error("更新地址为空");
    await navigator.clipboard.writeText(url);
    log("更新地址已复制");
    setActionTag("更新地址已复制", "ok");
  } catch (e) {
    log(`复制更新地址失败: ${e}`, "WARN");
    setActionTag("复制地址失败", "warn");
  }
}

async function onLoadEnvConfig() {
  try {
    const out = await invoke("get_runtime_env_config");
    if (el("envInstallBaseDir")) el("envInstallBaseDir").value = String(out?.install_base_dir || "");
    if (el("envPythonExe")) el("envPythonExe").value = String(out?.python_exe || "");
    if (el("envCacheDir")) el("envCacheDir").value = String(out?.cache_dir || "");
    if (el("envConfigPath")) el("envConfigPath").value = String(out?.config_path || "");
    if (el("envStatePath")) el("envStatePath").value = String(out?.deps_state_path || "");
    if (el("envMirror")) el("envMirror").value = state.envMirror || "official";
    syncCustomSelectByIds("envMirrorSelect", "envMirrorTrigger", "envMirrorPanel", "envMirror", "official");
    applyInstalledLayers(out?.installed_layers || [], out?.failed_layers || []);
    if (el("envOutput")) el("envOutput").textContent = JSON.stringify(out, null, 2);
    log("环境配置已读取");
  } catch (e) {
    if (el("envOutput")) el("envOutput").textContent = String(e);
    log(`读取环境配置失败: ${e}`, "ERROR");
  }
}

async function onSaveEnvConfig() {
  try {
    const installBaseDir = (el("envInstallBaseDir")?.value || "").trim();
    if (!installBaseDir) throw new Error("依赖目录不能为空");
    await invoke("set_runtime_env_config", {
      input: { installBaseDir },
    });
    log(`环境配置已保存: ${installBaseDir}`);
    await onLoadEnvConfig();
  } catch (e) {
    log(`保存环境配置失败: ${e}`, "ERROR");
  }
}

function envLayers() {
  const out = [];
  if (el("envLayerBasic")?.checked && !el("envLayerBasic")?.disabled) out.push("BASIC");
  if (el("envLayerCore")?.checked && !el("envLayerCore")?.disabled) out.push("CORE");
  if (el("envLayerHeavyCpu")?.checked && !el("envLayerHeavyCpu")?.disabled) out.push("HEAVY_CPU");
  if (el("envLayerHeavyGpu")?.checked && !el("envLayerHeavyGpu")?.disabled) out.push("HEAVY_GPU");
  return out;
}

function setEnvTaskProgress(cur = 0, total = 0) {
  const c = Math.max(0, Number(cur || 0));
  const t = Math.max(0, Number(total || 0));
  const pct = t > 0 ? Math.max(0, Math.min(100, (c / t) * 100)) : 0;
  state.envProgressCur = c;
  state.envProgressTotal = t;
  state.envProgressTargetPct = pct;
  if (el("envTaskProgressText")) {
    el("envTaskProgressText").textContent = `${c}/${t} (${pct.toFixed(0)}%)`;
  }
  if (!state.envTaskBusy) {
    state.envProgressVisualPct = pct;
  } else if (pct < state.envProgressVisualPct) {
    state.envProgressVisualPct = pct;
  }
  if (el("envTaskProgressBar")) {
    el("envTaskProgressBar").style.width = `${state.envProgressVisualPct.toFixed(1)}%`;
  }
  if (!state.envProgressTimer) {
    state.envProgressTimer = setInterval(() => {
      const diff = state.envProgressTargetPct - state.envProgressVisualPct;
      if (Math.abs(diff) < 0.2) {
        state.envProgressVisualPct = state.envProgressTargetPct;
      } else {
        const step = Math.max(0.4, Math.min(5, Math.abs(diff) * 0.22));
        state.envProgressVisualPct += diff > 0 ? step : -step;
      }
      if (el("envTaskProgressBar")) {
        el("envTaskProgressBar").style.width = `${Math.max(0, Math.min(100, state.envProgressVisualPct)).toFixed(1)}%`;
      }
      if (
        !state.envTaskBusy &&
        Math.abs(state.envProgressTargetPct - state.envProgressVisualPct) < 0.2
      ) {
        clearInterval(state.envProgressTimer);
        state.envProgressTimer = null;
      }
    }, 90);
  }
}

function setEnvTaskStatus(text) {
  if (el("envTaskStatus")) el("envTaskStatus").textContent = String(text || "");
}

function setEnvTaskBusy(busy) {
  state.envTaskBusy = !!busy;
  const disableWhileBusy = ["btnInstallLayers", "btnLoadEnvConfig", "btnSaveEnvConfig"];
  disableWhileBusy.forEach((id) => {
    const n = el(id);
    if (n) n.disabled = !!busy;
  });
  const cancel = el("btnCancelEnvTask");
  if (cancel) cancel.disabled = !busy;
  if (!busy) {
    state.envProgressTargetPct = state.envProgressTotal > 0
      ? Math.max(0, Math.min(100, (state.envProgressCur / state.envProgressTotal) * 100))
      : state.envProgressTargetPct;
  }
}

function bindEnvLayerRules() {
  const cpu = el("envLayerHeavyCpu");
  const gpu = el("envLayerHeavyGpu");
  if (!cpu || !gpu) return;
  cpu.addEventListener("change", () => {
    if (cpu.checked) gpu.checked = false;
  });
  gpu.addEventListener("change", () => {
    if (gpu.checked) cpu.checked = false;
  });
}

function setLayerInstalledState(layer, installed) {
  const map = {
    BASIC: ["envLayerBasic", "envLayerBasicWrap"],
    CORE: ["envLayerCore", "envLayerCoreWrap"],
    HEAVY_CPU: ["envLayerHeavyCpu", "envLayerHeavyCpuWrap"],
    HEAVY_GPU: ["envLayerHeavyGpu", "envLayerHeavyGpuWrap"],
  };
  const pair = map[layer];
  if (!pair) return;
  const check = el(pair[0]);
  const wrap = el(pair[1]);
  if (!check || !wrap) return;
  check.checked = !!installed;
  check.disabled = !!installed;
  wrap.classList.toggle("installed", !!installed);
}

function applyInstalledLayers(installedLayers, failedLayers) {
  const installed = new Set((Array.isArray(installedLayers) ? installedLayers : []).map((x) => String(x || "").toUpperCase()));
  const failed = new Set((Array.isArray(failedLayers) ? failedLayers : []).map((x) => String(x || "").toUpperCase()));
  ["BASIC", "CORE", "HEAVY_CPU", "HEAVY_GPU"].forEach((layer) => {
    setLayerInstalledState(layer, installed.has(layer));
  });
  const hint = el("envInstalledHint");
  if (hint) {
    const installedText = installed.size ? Array.from(installed).sort().join(", ") : "(无)";
    const failedText = failed.size ? `；失败层: ${Array.from(failed).sort().join(", ")}` : "";
    hint.textContent = `已安装层: ${installedText}${failedText}`;
  }
}

function renderEnvTaskSnapshot(snap) {
  if (!snap || typeof snap !== "object") {
    return String(snap ?? "");
  }
  const status = String(snap?.status || "unknown");
  const cur = Number(snap?.progress_current || 0);
  const total = Number(snap?.progress_total || 0);
  const details = taskDetails(snap);
  const errorCode = taskErrorCode(snap);
  const tail = typeof details.log_tail === "string" ? details.log_tail.trim() : "";
  const lines = [];
  lines.push(`task_id: ${String(snap?.task_id || "")}`);
  lines.push(`kind: ${String(snap?.kind || "")}`);
  lines.push(`status: ${status}`);
  lines.push(`progress: ${cur}/${total}`);
  if (errorCode) {
    lines.push(`error_code: ${errorCode}`);
  }
  if (snap?.error) {
    lines.push(`error: ${String(snap.error)}`);
  }
  if (tail) {
    lines.push("");
    lines.push("[install log]");
    lines.push(tail);
  } else {
    lines.push("");
    lines.push("[raw]");
    lines.push(JSON.stringify(snap, null, 2));
  }
  return lines.join("\n");
}

async function pollEnvTaskNonBlocking(taskId) {
  const pollMs = 300;
  while (true) {
    const snap = await invoke("daemon_task_status", {
      input: { endpoint: endpoint(), taskId },
    });
    if (el("envOutput")) el("envOutput").textContent = renderEnvTaskSnapshot(snap);
    setEnvTaskProgress(snap?.progress_current || 0, snap?.progress_total || 0);
    setEnvTaskStatus(`状态: ${snap?.status || "unknown"}`);
    const status = String(snap?.status || "").toLowerCase();
    if (status === "success" || status === "error" || status === "cancelled") return snap;
    await sleep(pollMs);
  }
}

async function submitEnvTask(kind, params) {
  if (state.envTaskBusy) {
    log("环境任务进行中，请稍候", "WARN");
    return;
  }
  try {
    saveSettings();
    setEnvTaskBusy(true);
    setEnvTaskStatus("提交中...");
    await ensureDaemonReady(`env_${kind}`, { forceRestart: true });
    const doSubmit = async () =>
      invoke("daemon_task_submit", {
        input: {
          endpoint: endpoint(),
          kind,
          params,
        },
      });
    let out;
    try {
      out = await doSubmit();
    } catch (e) {
      if (isUnsupportedTaskKindError(e)) {
        log(`检测到 daemon 不支持 ${kind}，自动重启并重试一次...`, "WARN");
        await ensureDaemonReady(`env_${kind}_retry`, { forceRestart: true });
        out = await doSubmit();
      } else {
        throw e;
      }
    }
    const taskId = String(out?.task_id || "");
    if (!taskId) throw new Error("环境任务提交失败: 空 task_id");
    state.envTaskId = taskId;
    if (el("envTaskId")) el("envTaskId").value = taskId;
    log(`环境任务已提交: ${taskId} (${kind})`);
    let snap = await pollEnvTaskNonBlocking(taskId);
    let lockRetried = false;
    if (String(snap?.status || "").toLowerCase() === "error" && isDaemonEncodingError(snap?.error || "")) {
      log("检测到 daemon 编码异常，自动重启并重试一次环境任务...", "WARN");
      await ensureDaemonReady(`env_${kind}_encoding_retry`, { forceRestart: true });
      const retrySubmit = await doSubmit();
      const retryTaskId = String(retrySubmit?.task_id || "");
      if (!retryTaskId) throw new Error("环境任务重试失败: 空 task_id");
      state.envTaskId = retryTaskId;
      if (el("envTaskId")) el("envTaskId").value = retryTaskId;
      log(`环境任务重试已提交: ${retryTaskId} (${kind})`);
      snap = await pollEnvTaskNonBlocking(retryTaskId);
    }
    if (
      String(snap?.status || "").toLowerCase() === "error" &&
      kind === "install_deps" &&
      isEnvInstallLockError(snap) &&
      !lockRetried
    ) {
      lockRetried = true;
      log("检测到依赖文件占用/锁冲突，自动重启 daemon 并重试一次...", "WARN");
      await ensureDaemonReady(`env_${kind}_lock_retry`, { forceRestart: true });
      const retrySubmit = await doSubmit();
      const retryTaskId = String(retrySubmit?.task_id || "");
      if (!retryTaskId) throw new Error("环境任务锁冲突重试失败: 空 task_id");
      state.envTaskId = retryTaskId;
      if (el("envTaskId")) el("envTaskId").value = retryTaskId;
      log(`环境任务锁冲突重试已提交: ${retryTaskId} (${kind})`);
      snap = await pollEnvTaskNonBlocking(retryTaskId);
    }
    if (String(snap?.status || "").toLowerCase() === "success") {
      log(`环境任务成功: ${kind}`);
      setEnvTaskStatus("状态: success");
      setActionTag("环境任务完成", "ok");
      await onLoadEnvConfig();
    } else if (String(snap?.status || "").toLowerCase() === "cancelled") {
      log(`环境任务已取消: ${kind}`, "WARN");
      setEnvTaskStatus("状态: cancelled");
      setActionTag("环境任务已取消", "warn");
    } else {
      const errMsg = String(snap?.error || "unknown error");
      log(`环境任务失败: ${errMsg}`, "ERROR");
      const details = taskDetails(snap);
      const detail = String(details?.primary_error || "").trim();
      if (detail) {
        log(`环境任务失败详情: ${detail}`, "ERROR");
      }
      const code = taskErrorCode(snap);
      if (code) {
        log(`环境任务错误码: ${code}`, "ERROR");
      }
      const tail = String(details?.log_tail || "").trim();
      if (tail) {
        log("环境任务日志尾部:\n" + tail, "ERROR");
      }
      setEnvTaskStatus("状态: error");
      setActionTag("环境任务失败", "error");
    }
  } catch (e) {
    log(`环境任务异常: ${e}`, "ERROR");
    setEnvTaskStatus("状态: error");
    if (el("envOutput")) el("envOutput").textContent = String(e);
    setActionTag("环境任务异常", "error");
  } finally {
    setEnvTaskBusy(false);
  }
}

async function onInstallLayers() {
  const installBaseDir = (el("envInstallBaseDir")?.value || "").trim();
  if (!installBaseDir) {
    log("依赖目录为空，请先选择依赖目录", "WARN");
    return;
  }
  const layers = envLayers();
  if (!layers.length) {
    log("请至少选择一个功能层", "WARN");
    return;
  }
  if (layers.includes("HEAVY_CPU") && layers.includes("HEAVY_GPU")) {
    log("HEAVY_CPU 与 HEAVY_GPU 互斥，请只保留一个", "WARN");
    return;
  }
  const mirror = (el("envMirror")?.value || "official").trim();
  log(`环境安装参数: layers=${layers.join(",")} mirror=${mirror}`);
  await submitEnvTask(
    "install_deps",
    {
      layers,
      deps_dir: installBaseDir,
      mirror,
    }
  );
}

async function onCancelEnvTask() {
  try {
    const taskId = (el("envTaskId")?.value || "").trim() || String(state.envTaskId || "").trim();
    if (!taskId) throw new Error("没有可取消的环境任务");
    await invoke("daemon_task_cancel", {
      input: { endpoint: endpoint(), taskId },
    });
    log(`已发送环境任务取消请求: ${taskId}`, "WARN");
    setActionTag("已取消环境任务", "warn");
  } catch (e) {
    log(`取消环境任务失败: ${e}`, "ERROR");
    setActionTag("取消环境任务失败", "error");
  }
}

async function onPickEnvDepsDir() {
  try {
    const out = await invoke("pick_file", {
      input: { kind: "folder" },
    });
    if (typeof out === "string" && out.trim()) {
      el("envInstallBaseDir").value = out.trim();
    }
  } catch (e) {
    log(`选择依赖目录失败: ${e}`, "WARN");
  }
}

async function onPickEnvPython() {
  try {
    const out = await invoke("pick_file", {
      input: { kind: "python" },
    });
    if (typeof out === "string" && out.trim()) {
      el("envPythonExe").value = out.trim();
      const low = out.toLowerCase().replaceAll("\\", "/");
      const marker = "/python311/python.exe";
      const idx = low.lastIndexOf(marker);
      if (idx > 0 && el("envInstallBaseDir")) {
        const base = out.slice(0, idx).replaceAll("/", "\\");
        if (base.trim()) el("envInstallBaseDir").value = base;
      }
    }
  } catch (e) {
    log(`选择 Python 失败: ${e}`, "WARN");
  }
}

async function onOpenPath(rawPath, label) {
  const p = String(rawPath || "").trim();
  if (!p) {
    log(`${label}为空，无法打开`, "WARN");
    return;
  }
  try {
    await invoke("open_path", { path: p });
  } catch (e) {
    log(`打开${label}失败: ${e}`, "WARN");
  }
}

async function onGlobalKeyDown(ev) {
  if (!ev || ev.key !== "Escape" || ev.repeat) return;
  const imageTaskId = (el("taskId")?.value || "").trim() || String(state.currentTaskId || "").trim();
  const pdfTaskId = (el("pdfTaskId")?.value || "").trim() || String(state.currentPdfTaskId || "").trim();
  const envTaskId = (el("envTaskId")?.value || "").trim() || String(state.envTaskId || "").trim();

  if (state.imagePollInFlight && imageTaskId) {
    ev.preventDefault();
    log(`ESC: 尝试取消图片任务 ${imageTaskId}`, "WARN");
    try {
      await onCancelTask();
    } catch (_) {}
  }

  if (state.pdfPollInFlight && pdfTaskId) {
    ev.preventDefault();
    log(`ESC: 尝试取消 PDF 任务 ${pdfTaskId}`, "WARN");
    try {
      await onCancelPdfTask();
    } catch (_) {}
  }

  if (state.envTaskBusy && envTaskId) {
    ev.preventDefault();
    log(`ESC: 尝试取消环境任务 ${envTaskId}`, "WARN");
    try {
      await onCancelEnvTask();
    } catch (_) {}
  }
}

async function onRegisterHotkey() {
  try {
    saveSettings();
    const shortcut = (el("hotkeyInput").value || "").trim();
    if (!shortcut) throw new Error("热键不能为空");
    const out = await invoke("register_capture_hotkey", {
      input: { shortcut },
    });
    const label = out?.shortcut || shortcut;
    setHotkeyStatusText(`已注册: ${label}`);
    log(`全局热键已注册: ${label}`);
  } catch (e) {
    setHotkeyStatusText("注册失败");
    log(`注册全局热键失败: ${e}`, "ERROR");
  }
}

async function onUnregisterHotkey() {
  try {
    await invoke("unregister_capture_hotkey");
    setHotkeyStatusText("未注册");
    log("全局热键已注销");
  } catch (e) {
    log(`注销全局热键失败: ${e}`, "WARN");
  }
}

async function hotkeyCaptureAndPredict(trigger = "manual") {
  if (state.hotkeyBusy || state.imagePollInFlight) {
    log("热键触发已忽略: 当前识别任务进行中", "WARN");
    return;
  }
  state.hotkeyBusy = true;
  state.imagePollInFlight = true;
  setImageButtonsBusy(true);
  try {
    saveSettings();
    await ensureDaemonReady(`capture_${trigger}`);
    log(`开始区域框选截图 (${trigger})`);
    const cap = await invoke("capture_region_to_base64");
    const imageB64 = String(cap?.image_b64 || "");
    if (!imageB64) throw new Error("截图失败: 空图像数据");
    log(`区域截图完成: in-memory png (${cap?.width || 0}x${cap?.height || 0})`);

    const modelName = el("modelName").value;
    const runOne = async () => {
      const pollOptions = getImagePollOptions();
      pollOptions.timeoutMs = Math.max(pollOptions.timeoutMs, HOTKEY_TIMEOUT_MIN_MS);
      const submit = await invoke("daemon_task_submit", {
        input: {
          endpoint: endpoint(),
          kind: "predict_image",
          params: {
            image_b64: imageB64,
            model_name: modelName,
          },
        },
      });
      const taskId = String(submit?.task_id || "");
      if (!taskId) throw new Error("热键任务提交失败: 空 task_id");
      state.currentTaskId = taskId;
      el("taskId").value = taskId;
      return pollImageTaskNonBlocking(
        taskId,
        pollOptions,
        "hotkey_image"
      );
    };

    let out = await runOne();
    if (String(out?.status || "").toLowerCase() === "error" && isImagePayloadMissingError(out?.error || "")) {
      log("检测到旧版 daemon 不支持 image_b64，自动重启并重试一次...", "WARN");
      await ensureDaemonReady("hotkey_retry", { forceRestart: true });
      out = await runOne();
    }
    el("taskOutput").textContent = JSON.stringify(out, null, 2);
    const status = out?.status || "unknown";
    const result = out?.output?.result ?? "";
    log(`热键识别完成: status=${status}, result_len=${String(result).length}`);
    if (String(status).toLowerCase() === "success") {
      addResultSnapshot(
        "image",
        {
          result: String(result || ""),
          formats: normalizeFormatMap(out?.output?.result_formats),
          formatErrors: normalizeFormatMap(out?.output?.result_format_errors),
        },
        String(out?.task_id || state.currentTaskId || "")
      );
      const autoCopied = await autoCopyImageLatexFromTask(out);
      setActionTag(
        autoCopied.ok ? "图片识别完成，LaTeX已复制" : "图片识别完成（复制失败）",
        autoCopied.ok ? "ok" : "warn"
      );
    }
  } catch (e) {
    log(`热键截图识别失败: ${e}`, "ERROR");
    setActionTag("图片识别失败", "error");
  } finally {
    state.hotkeyBusy = false;
    state.imagePollInFlight = false;
    setImageButtonsBusy(false);
  }
}

async function applyWindowEffects(options = {}) {
  const silent = !!options.silent;
  const persist = !!options.persist;
  const mode = String(options.mode || state.fxMode || "acrylic").toLowerCase();
  try {
    const fx = await invoke("apply_window_effects", {
      input: {
        mode,
      },
    });
    setFxTag(fx || "none");
    if (!silent) log(`窗口效果应用: ${fx}`);
    if (!silent) setActionTag(`已切换到 ${fx}`, "ok");
    if (persist) saveSettings();
  } catch (e) {
    // 保持当前视觉状态，避免瞬时失败导致界面发白/跳色
    if (!silent) log(`窗口效果应用失败: ${e}`, "WARN");
    if (!silent) setActionTag("材质切换失败", "warn");
  }
}

function bindButtons() {
  el("btnLoadContract").addEventListener("click", onLoadContract);
  el("btnHandshake").addEventListener("click", onHandshake);
  el("btnSubmitTask").addEventListener("click", onSubmitTask);
  el("btnPollTask").addEventListener("click", onPollTask);
  el("btnSubmitAndPoll").addEventListener("click", onSubmitAndPoll);
  el("btnHotkeyCapturePredict").addEventListener("click", () => hotkeyCaptureAndPredict("button"));
  el("btnCancelTask").addEventListener("click", onCancelTask);
  el("btnCopyImageResult").addEventListener("click", onCopyImageResult);
  el("btnSubmitPdfTask").addEventListener("click", onSubmitPdfTask);
  el("btnPollPdfTask").addEventListener("click", onPollPdfTask);
  el("btnSubmitAndPollPdf").addEventListener("click", onSubmitAndPollPdf);
  el("btnCancelPdfTask").addEventListener("click", onCancelPdfTask);
  if (el("btnSavePdfMarkdown")) el("btnSavePdfMarkdown").addEventListener("click", onSavePdfMarkdown);
  if (el("btnSavePdfLatex")) el("btnSavePdfLatex").addEventListener("click", onSavePdfLatex);
  el("btnPickImagePath").addEventListener("click", onPickImagePath);
  el("btnPickPdfPath").addEventListener("click", onPickPdfPath);
  if (el("btnClearResultHistory")) {
    el("btnClearResultHistory").addEventListener("click", () => {
      clearResultHistory();
      log("已清空识别历史");
    });
  }
  el("btnLoadEnvConfig").addEventListener("click", onLoadEnvConfig);
  el("btnSaveEnvConfig").addEventListener("click", onSaveEnvConfig);
  el("btnInstallLayers").addEventListener("click", onInstallLayers);
  el("btnCancelEnvTask").addEventListener("click", onCancelEnvTask);
  el("btnPickEnvDepsDir").addEventListener("click", onPickEnvDepsDir);
  el("btnPickEnvPython").addEventListener("click", onPickEnvPython);
  el("btnOpenDepsDir").addEventListener("click", () => onOpenPath(el("envInstallBaseDir")?.value, "依赖目录"));
  el("btnOpenCacheDir").addEventListener("click", () => onOpenPath(el("envCacheDir")?.value, "缓存目录"));
  el("btnOpenStateFile").addEventListener("click", () => onOpenPath(el("envStatePath")?.value, "状态文件"));
  el("btnOpenConfigDir").addEventListener("click", () => {
    const cfg = String(el("envConfigPath")?.value || "").trim();
    const dir = cfg.includes("\\") ? cfg.slice(0, cfg.lastIndexOf("\\")) : cfg;
    onOpenPath(dir, "配置目录");
  });

  el("btnSaveSettings").addEventListener("click", () => {
    applyUiTuning();
    saveSettings();
    log("设置已保存");
    setActionTag("设置保存成功", "ok");
  });
  el("btnResetSettings").addEventListener("click", () => {
    Object.assign(state, {
      host: "127.0.0.1",
      port: 43637,
      token: "",
      contractPath: "",
      hotkey: "Ctrl+Shift+F",
      pollIntervalMs: 200,
      timeoutMs: 120000,
      pdfMaxPages: 0,
      pdfDpi: 200,
      pdfTemplateStyle: "paper",
      uiBgAlpha: 0.20,
      uiSidebarAlpha: 0.20,
      uiPanelAlpha: 0.33,
      uiBlurPx: 26,
      uiRadiusPx: 12,
      uiBrightness: 1.18,
      uiContrast: 1.2,
      uiSaturatePct: 40,
      uiTintAlpha: 0.0,
      uiNoiseAlpha: 0.02,
      fxMode: "acrylic",
      compactMode: false,
      imageCopyFormat: "latex",
      aboutUpdateUrl: "https://github.com/SakuraMathcraft/LaTeXSnipper/tree/tauri",
    });
    fillForm();
    applyWindowMode(false, { persist: false, silent: true });
    saveSettings();
    log("已恢复默认设置");
    setActionTag("已恢复默认设置", "ok");
  });
  if (el("btnFxAcrylic")) {
    el("btnFxAcrylic").addEventListener("click", () => {
      state.fxMode = "acrylic";
      applyWindowEffects({ mode: "acrylic", persist: true });
    });
  }
  if (el("btnFxMica")) {
    el("btnFxMica").addEventListener("click", () => {
      state.fxMode = "mica";
      applyWindowEffects({ mode: "mica", persist: true });
    });
  }
  if (el("btnModeNormal")) {
    el("btnModeNormal").addEventListener("click", () => {
      applyWindowMode(false, { persist: true });
    });
  }
  if (el("btnModeCompact")) {
    el("btnModeCompact").addEventListener("click", () => {
      applyWindowMode(true, { persist: true });
    });
  }
  const brandTitle = document.querySelector(".brand-text strong");
  if (brandTitle) {
    brandTitle.addEventListener("dblclick", () => {
      if (state.compactMode) {
        applyWindowMode(false, { persist: true });
      }
    });
  }
  el("btnRegisterHotkey").addEventListener("click", onRegisterHotkey);
  el("btnUnregisterHotkey").addEventListener("click", onUnregisterHotkey);
  el("btnCopyLogs").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el("logOutput").textContent || "");
      log("日志已复制");
      setActionTag("日志已复制", "ok");
    } catch (e) {
      log(`复制日志失败: ${e}`, "WARN");
      setActionTag("复制日志失败", "warn");
    }
  });
  el("btnClearLogs").addEventListener("click", () => {
    el("logOutput").textContent = "";
    log("日志已清空");
  });
  el("btnOpenUpdateUrl").addEventListener("click", onOpenUpdateUrl);
  el("btnCopyUpdateUrl").addEventListener("click", onCopyUpdateUrl);
  [
    "uiBgAlpha",
    "uiSidebarAlpha",
    "uiPanelAlpha",
    "uiBlurPx",
    "uiRadiusPx",
    "uiBrightness",
    "uiContrast",
    "uiSaturatePct",
    "uiTintAlpha",
    "uiNoiseAlpha",
  ].forEach((id) => {
    const n = el(id);
    if (n) n.addEventListener("input", applyUiTuning);
  });
}

function bindTauriEvents() {
  const listen = window.__TAURI__?.event?.listen;
  if (!listen) return;
  listen("window-effects-applied", (event) => {
    setFxTag(String(event?.payload ?? "none"));
  }).catch(() => {});
  listen("global-hotkey-triggered", () => {
    hotkeyCaptureAndPredict("global-hotkey");
  }).catch(() => {});
  listen("hotkey-status", (event) => {
    const p = event?.payload || {};
    if (p.registered === true) {
      const label = p.shortcut || "";
      setHotkeyStatusText(label ? `已注册: ${label}` : "已注册");
    } else if (p.ready === false || p.registered === false) {
      setHotkeyStatusText("未注册");
    }
    if (p.error) {
      log(`热键状态: ${p.error}`, "WARN");
    }
  }).catch(() => {});
}

async function syncHotkeyStatus() {
  try {
    const status = await invoke("get_capture_hotkey_status");
    if (status?.registered) {
      const label = status.shortcut || "";
      setHotkeyStatusText(label ? `已注册: ${label}` : "已注册");
    } else {
      setHotkeyStatusText("未注册");
    }
  } catch (e) {
    log(`获取热键状态失败: ${e}`, "WARN");
  }
}

function boot() {
  bindNav();
  loadSettings();
  fillForm();
  initCustomSelect();
  bindEnvLayerRules();
  bindButtons();
  bindResultListActions();
  loadResultStore();
  document.addEventListener("keydown", onGlobalKeyDown);
  bindTauriEvents();
  setEnvTaskBusy(false);
  setEnvTaskStatus("空闲");
  setEnvTaskProgress(0, 0);
  setFxTag(state.fxMode || "acrylic");
  setActionTag("操作: 就绪", "info", 0);
  log("Tauri MVP UI 已启动");
  startSystemMetricsPolling();
  onLoadEnvConfig();
  onLoadAboutInfo();
  syncHotkeyStatus();
  onRegisterHotkey();
  applyWindowEffects({ mode: state.fxMode || "acrylic", silent: true });
  applyWindowMode(!!state.compactMode, { silent: true, persist: false });
  onHandshake().catch(() => {});
}

boot();
