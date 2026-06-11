import { MathfieldElement } from "./vendor/mathlive.min.mjs";

if (!window.LaTeXSnipperEditorSymbols) {
  throw new Error("LaTeXSnipper editor symbol library was not loaded.");
}

if (!window.LaTeXSnipperMathfieldInput) {
  throw new Error("LaTeXSnipper MathLive input configuration was not loaded.");
}

if (!window.LaTeXSnipperMatrixTemplates) {
  throw new Error("LaTeXSnipper matrix templates were not loaded.");
}

const { STRINGS, GROUPS } = window.LaTeXSnipperEditorSymbols;
let mathfield = null;
let locale = "zh";
let mode = "insert";
let submitting = false;
let pendingInit = null;
let libraryState = loadLibraryState();

const host = document.getElementById("mathfieldHost");
const latexSource = document.getElementById("latexSource");
const statusText = document.getElementById("statusText");
const cancelButton = document.getElementById("cancelButton");
const acceptButton = document.getElementById("acceptButton");
const tabs = document.getElementById("libraryTabs");
const titleText = document.getElementById("libraryTitleText");
const grid = document.getElementById("symbolGrid");
const searchInput = document.getElementById("symbolSearch");
const globalSearch = document.getElementById("globalSearch");

function strings() {
  return locale.startsWith("zh") ? STRINGS.zh : STRINGS.en;
}

function displayLabel(item) {
  if (isSectionItem(item)) {
    return locale.startsWith("zh") ? item.section : item.sectionEn;
  }

  if (locale.startsWith("zh")) {
    return item[0];
  }

  return item[2] || item[0];
}

function isSectionItem(item) {
  return Boolean(item?.section);
}

function groupTitle(group) {
  return strings().tabs[group.id] || group.id;
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
}

function currentLatex() {
  const source = latexSource.value.trim();
  if (isMathMlSource(source)) {
    return source;
  }

  return mathfield?.getValue("latex-expanded")?.trim() || "";
}

function syncSource() {
  latexSource.value = currentLatex();
}

function setLatex(latex) {
  const source = latex || "";
  if (isMathMlSource(source.trim())) {
    latexSource.value = source;
    mathfield.setValue("", { silenceNotifications: true });
    return;
  }

  mathfield.setValue(source, { silenceNotifications: true });
  syncSource();
}

function isMathMlSource(source) {
  return /^<math(\s|>|:)/i.test(source);
}

function insertLatex(latex) {
  if (latex.startsWith("matrix:")) {
    insertMatrix(latex.slice("matrix:".length));
    return;
  }

  window.LaTeXSnipperMathfieldInput.insertTemplate(mathfield, latex);
  syncSource();
}

function insertMatrix(env, rows = 2, cols = 2) {
  window.LaTeXSnipperMatrixTemplates.insert(mathfield, env, rows, cols);
  syncSource();
}

let _currentGroup = null;

function loadLibraryState() {
  try {
    return { groupId: "greek", search: "", globalSearch: "", scrollTop: 0, ...JSON.parse(localStorage.getItem("latexSnipperEditorLibraryState") || "{}") };
  } catch {
    return { groupId: "greek", search: "", globalSearch: "", scrollTop: 0 };
  }
}

function saveLibraryState() {
  try {
    localStorage.setItem("latexSnipperEditorLibraryState", JSON.stringify(libraryState));
  } catch {
    // localStorage can be unavailable in constrained WebView profiles.
  }
}

function restoreGridScroll() {
  const scrollTop = Number(libraryState.scrollTop) || 0;
  requestAnimationFrame(() => { grid.scrollTop = scrollTop; });
}

function selectGroup(group, options = {}) {
  _currentGroup = group;
  libraryState.groupId = group.id;
  if (!options.preserveSearch) {
    libraryState.search = "";
  }
  if (!options.preserveGlobalSearch) {
    libraryState.globalSearch = "";
  }
  globalSearch.value = libraryState.globalSearch || "";
  searchInput.value = libraryState.search || "";
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.group === group.id);
  }

  titleText.textContent = groupTitle(group);
  renderGrid(group, searchInput.value);
  if (options.preserveScroll) {
    restoreGridScroll();
  } else {
    libraryState.scrollTop = 0;
  }
  saveLibraryState();
}

function renderGrid(group, query) {
  grid.className = group.structures ? "symbol-grid structures" : "symbol-grid";
  grid.replaceChildren();
  const q = query.trim().toLowerCase();
  for (const item of group.items) {
    if (isSectionItem(item)) {
      if (!q) {
        const label = document.createElement("div");
        label.className = "symbol-section-label";
        label.textContent = displayLabel(item);
        grid.appendChild(label);
      }
      continue;
    }

    if (q && !matchItem(item, q)) continue;

    if (group.structures && String(item[1]).startsWith("matrix:")) {
      grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
      continue;
    }

    grid.appendChild(createSymbolButton(item));
  }
}

function createSymbolButton(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = displayLabel(item);
  button.title = item[2] ? `${item[2]}\n${item[1]}` : item[1];
  button.addEventListener("pointerdown", event => event.preventDefault());
  button.addEventListener("click", () => insertLatex(item[1]));
  return button;
}

function matchItem(item, query) {
  if (isSectionItem(item)) return false;
  const label = displayLabel(item).toLowerCase();
  const latex = item[1].toLowerCase();
  return label.includes(query) || latex.includes(query);
}

searchInput.addEventListener("input", () => {
  libraryState.search = searchInput.value;
  libraryState.scrollTop = 0;
  saveLibraryState();
  if (_currentGroup) renderGrid(_currentGroup, searchInput.value);
});

function renderGlobalResults(query) {
  const q = query.trim().toLowerCase();
  if (!q) { selectGroup(_currentGroup || GROUPS[0], { preserveSearch: true, preserveScroll: true }); return; }
  grid.className = "symbol-grid structures";
  grid.replaceChildren();
  for (const group of GROUPS) {
    const hits = group.items.filter(item => !isSectionItem(item) && matchItem(item, q));
    if (!hits.length) continue;
    const label = document.createElement("div");
    label.className = "global-group-label";
    label.textContent = groupTitle(group);
    grid.appendChild(label);
    for (const item of hits) {
      if (group.structures && String(item[1]).startsWith("matrix:")) {
        grid.appendChild(createMatrixControl(displayLabel(item), item[1].slice("matrix:".length)));
        continue;
      }
      grid.appendChild(createSymbolButton(item));
    }
  }
}

globalSearch.addEventListener("input", () => {
  libraryState.globalSearch = globalSearch.value;
  libraryState.scrollTop = 0;
  saveLibraryState();
  renderGlobalResults(globalSearch.value);
});

grid.addEventListener("scroll", () => {
  libraryState.scrollTop = grid.scrollTop;
  saveLibraryState();
});

function createMatrixControl(label, env) {
  const isCases = env === "cases";
  const isSquare = ["identity", "diagonal"].includes(env);
  const row = document.createElement("div");
  row.className = `matrix-row${isCases ? " cases" : ""}${isSquare ? " square" : ""}`;

  const rowSelect = document.createElement("select");
  rowSelect.title = strings().rows;
  for (let i = 1; i <= 10; i++) {
    rowSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
  }
  row.appendChild(rowSelect);

  let colSelect = null;
  if (!isCases && !isSquare) {
    colSelect = document.createElement("select");
    colSelect.title = strings().columns;
    for (let i = 1; i <= 10; i++) {
      colSelect.appendChild(new Option(String(i), String(i), i === 2, i === 2));
    }
    row.appendChild(colSelect);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.title = `\\begin{${env}}...\\end{${env}}`;
  button.addEventListener("click", () => {
    insertMatrix(env, Number(rowSelect.value), colSelect ? Number(colSelect.value) : 2);
  });
  row.appendChild(button);
  return row;
}

function buildLibrary() {
  tabs.replaceChildren();
  for (const group of GROUPS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab";
    button.dataset.group = group.id;
    button.textContent = groupTitle(group);
    button.title = groupTitle(group);
    button.addEventListener("click", () => selectGroup(group));
    tabs.appendChild(button);
  }

  const group = GROUPS.find(candidate => candidate.id === libraryState.groupId) || GROUPS[0];
  _currentGroup = group;
  for (const button of tabs.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.group === group.id);
  }
  titleText.textContent = groupTitle(group);
  searchInput.value = libraryState.search || "";
  globalSearch.value = libraryState.globalSearch || "";
  if (globalSearch.value) {
    renderGlobalResults(globalSearch.value);
    restoreGridScroll();
  } else {
    selectGroup(group, { preserveSearch: true, preserveGlobalSearch: true, preserveScroll: true });
  }
}

function accept() {
  if (submitting) {
    return;
  }

  const latex = currentLatex();
  if (!latex) {
    setStatus(strings().latexRequired);
    return;
  }

  send({ type: "accept", latex, display: true });
}

function hideVirtualKeyboard() {
  window.mathVirtualKeyboard?.hide();
}

function configureText() {
  document.documentElement.lang = locale.startsWith("zh") ? "zh-CN" : "en";
  cancelButton.textContent = strings().cancel;
  acceptButton.textContent = mode === "update" ? strings().acceptUpdate : strings().acceptInsert;
  setStatus(strings().ready);
  buildLibrary();
}

function applyInit(payload) {
  locale = String(payload?.locale || "zh").toLowerCase();
  mode = payload?.mode === "update" ? "update" : "insert";
  setSubmitting(false);
  configureText();
  window.LaTeXSnipperMathfieldInput.setDefaultFontStyle(
    mathfield,
    payload?.fontStyle || "Italic",
  );
  setLatex(payload?.latex || "");
}

async function bootstrap() {
  MathfieldElement.fontsDirectory = new URL("./vendor/fonts", window.location.href).href;
  mathfield = new MathfieldElement();
  mathfield.smartFence = true;
  mathfield.mathVirtualKeyboardPolicy = "onfocus";
  window.LaTeXSnipperMathfieldInput.configure(mathfield, accept);
  host.appendChild(mathfield);
  mathfield.addEventListener("input", syncSource);
  latexSource.addEventListener("input", () => {
    const source = latexSource.value || "";
    if (!isMathMlSource(source.trim())) {
      mathfield.setValue(source, { silenceNotifications: true });
    }
  });
  cancelButton.addEventListener("click", () => send({ type: "cancel" }));
  acceptButton.addEventListener("click", accept);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
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
  if (pendingInit || window.__latexSnipperPendingInit) {
    applyInit(pendingInit || window.__latexSnipperPendingInit);
    pendingInit = null;
    window.__latexSnipperPendingInit = null;
  }
}

window.LaTeXSnipperEditor = {
  init(payload) {
    pendingInit = payload;
    if (mathfield) {
      applyInit(payload);
      pendingInit = null;
    }
  },
  setStatus,
  setSubmitting,
};

bootstrap().catch((error) => setStatus(String(error)));
