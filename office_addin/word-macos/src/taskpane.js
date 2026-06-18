import { createFormulaModel } from "./formula/formulaModel.js";
import {
  formatFormulaForInsertion,
  insertFormula as insertFormulaIntoWord,
} from "./office/wordInsert.js";
import {
  getMathJaxUnavailableMessage,
  renderLatexToSvg,
} from "./render/mathjaxRenderer.js";
import {
  shouldClearInputShortcut,
  shouldDismissShortcut,
  shouldInsertFormulaShortcut,
} from "./shortcuts.js";

const elements = {
  clearButton: document.getElementById("clear-button"),
  editorStatus: document.getElementById("editor-status"),
  formulaPreview: document.getElementById("formula-preview"),
  hostStatus: document.getElementById("host-status"),
  insertDisplayButton: document.getElementById("insert-display-button"),
  insertInlineButton: document.getElementById("insert-inline-button"),
  insertNumberedButton: document.getElementById("insert-numbered-button"),
  latexInput: document.getElementById("latex-input"),
  manualNumber: document.getElementById("manual-number"),
  modeInputs: Array.from(document.querySelectorAll("[name='formula-mode']")),
  operationStatus: document.getElementById("operation-status"),
};

let previewRequestId = 0;

function setStatus(message) {
  elements.operationStatus.textContent = message;
}

function getSelectedMode() {
  return (
    elements.modeInputs.find((input) => input.checked)?.value ?? "inline"
  );
}

function setSelectedMode(mode) {
  for (const input of elements.modeInputs) {
    input.checked = input.value === mode;
  }
  updateNumberInputState();
  void updatePreview();
}

function updateNumberInputState() {
  const numbered = getSelectedMode() === "numbered";
  elements.manualNumber.disabled = !numbered;
}

function getPreviewText() {
  if (!elements.latexInput.value.trim()) {
    return "Preview";
  }

  try {
    return formatFormulaForInsertion({
      latex: elements.latexInput.value,
      mode: getSelectedMode(),
      manualNumber: elements.manualNumber.value,
    }).trim();
  } catch (error) {
    return error.message;
  }
}

function setPreviewText(message) {
  elements.formulaPreview.classList.remove("is-rendered");
  elements.formulaPreview.textContent = message;
}

function setPreviewSvg(svg) {
  elements.formulaPreview.classList.add("is-rendered");
  elements.formulaPreview.innerHTML = svg;
}

async function updatePreview() {
  const requestId = ++previewRequestId;
  const latex = elements.latexInput.value.trim();

  if (!latex) {
    setPreviewText("Preview");
    elements.editorStatus.textContent = "MathJax preview";
    return;
  }

  setPreviewText(getPreviewText());
  elements.editorStatus.textContent = "Rendering preview...";

  try {
    const svg = await renderLatexToSvg({
      latex,
      mode: getSelectedMode(),
    });
    if (requestId !== previewRequestId) {
      return;
    }
    setPreviewSvg(svg);
    elements.editorStatus.textContent = "Visual preview ready";
  } catch (error) {
    if (requestId !== previewRequestId) {
      return;
    }
    setPreviewText(getPreviewText());
    elements.editorStatus.textContent = getMathJaxUnavailableMessage();
  }
}

function clearInput() {
  elements.latexInput.value = "";
  elements.manualNumber.value = "";
  setSelectedMode("inline");
  elements.latexInput.focus();
  setStatus("Ready");
}

async function insertSelectedFormula(mode = getSelectedMode()) {
  setSelectedMode(mode);

  const formula = createFormulaModel({
    latex: elements.latexInput.value,
    manualNumber: elements.manualNumber.value,
    mode,
  });

  try {
    setStatus("Inserting...");
    const result = await insertFormulaIntoWord({
      latex: formula.latex,
      manualNumber: formula.manualNumber,
      mode: formula.mode,
      visual: true,
    });
    setStatus(resultStatusMessage(result));
  } catch (error) {
    setStatus(error.message);
    elements.latexInput.focus();
  }
}

function resultStatusMessage(result) {
  if (result.insertedAs === "visual") {
    return "Inserted visual formula";
  }

  if (result.insertedAs === "text-fallback") {
    return "Visual insert failed; inserted text fallback";
  }

  return "Inserted at cursor";
}

function dismissTransientState() {
  document.activeElement?.blur?.();
  setStatus("Ready");
}

function handleKeydown(event) {
  if (shouldInsertFormulaShortcut(event)) {
    event.preventDefault();
    void insertSelectedFormula();
    return;
  }

  if (shouldClearInputShortcut(event)) {
    event.preventDefault();
    clearInput();
    return;
  }

  if (shouldDismissShortcut(event)) {
    dismissTransientState();
  }
}

function markOfficeReady() {
  elements.hostStatus.textContent = "Word ready";
  setStatus("Ready");
}

function initialize() {
  updateNumberInputState();
  void updatePreview();

  elements.insertInlineButton.addEventListener("click", () => {
    void insertSelectedFormula("inline");
  });
  elements.insertDisplayButton.addEventListener("click", () => {
    void insertSelectedFormula("display");
  });
  elements.insertNumberedButton.addEventListener("click", () => {
    void insertSelectedFormula("numbered");
  });
  elements.clearButton.addEventListener("click", clearInput);
  elements.latexInput.addEventListener("input", () => {
    void updatePreview();
  });
  elements.manualNumber.addEventListener("input", () => {
    void updatePreview();
  });
  for (const input of elements.modeInputs) {
    input.addEventListener("change", () => {
      updateNumberInputState();
      void updatePreview();
    });
  }
  document.addEventListener("keydown", handleKeydown);

  if (globalThis.Office?.onReady) {
    Office.onReady(markOfficeReady);
  } else {
    elements.hostStatus.textContent = "Office.js unavailable";
    setStatus("Open from Word to insert");
  }
}

initialize();
