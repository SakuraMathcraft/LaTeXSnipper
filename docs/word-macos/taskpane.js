import {
  canUseMathLive,
  createMathEditorState,
} from "./editor/mathEditor.js";
import { createFormulaModel } from "./formula/formulaModel.js";
import {
  formatFormulaForInsertion,
  insertFormula as insertFormulaIntoWord,
} from "./office/wordInsert.js";
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
  updatePreview();
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

function updatePreview() {
  elements.formulaPreview.textContent = getPreviewText();
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
    await insertFormulaIntoWord({
      latex: formula.latex,
      manualNumber: formula.manualNumber,
      mode: formula.mode,
    });
    setStatus("Inserted at cursor");
  } catch (error) {
    setStatus(error.message);
    elements.latexInput.focus();
  }
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

function initializeMathEditorStatus() {
  const editorState = createMathEditorState({
    mathLiveAvailable: canUseMathLive(globalThis),
  });
  elements.editorStatus.textContent = editorState.message;
}

function initialize() {
  initializeMathEditorStatus();
  updateNumberInputState();
  updatePreview();

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
  elements.latexInput.addEventListener("input", updatePreview);
  elements.manualNumber.addEventListener("input", updatePreview);
  for (const input of elements.modeInputs) {
    input.addEventListener("change", () => {
      updateNumberInputState();
      updatePreview();
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
