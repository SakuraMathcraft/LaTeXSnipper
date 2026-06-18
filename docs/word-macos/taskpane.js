import { formatInlineFormula } from "./latex.js";
import {
  shouldClearInputShortcut,
  shouldInsertFormulaShortcut,
} from "./shortcuts.js";

const elements = {
  clearButton: document.getElementById("clear-button"),
  hostStatus: document.getElementById("host-status"),
  insertButton: document.getElementById("insert-button"),
  latexInput: document.getElementById("latex-input"),
  operationStatus: document.getElementById("operation-status"),
};

function setStatus(message) {
  elements.operationStatus.textContent = message;
}

function clearInput() {
  elements.latexInput.value = "";
  elements.latexInput.focus();
  setStatus("Input cleared");
}

function insertIntoWord(text) {
  return new Promise((resolve, reject) => {
    if (!globalThis.Office?.context?.document?.setSelectedDataAsync) {
      reject(new Error("Word is not ready yet."));
      return;
    }

    Office.context.document.setSelectedDataAsync(
      text,
      { coercionType: Office.CoercionType.Text },
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve();
          return;
        }
        reject(new Error(result.error?.message || "Word insertion failed."));
      },
    );
  });
}

async function insertFormula() {
  let text;
  try {
    text = formatInlineFormula(elements.latexInput.value);
  } catch (error) {
    setStatus(error.message);
    elements.latexInput.focus();
    return;
  }

  try {
    await insertIntoWord(text);
    setStatus("Formula inserted as text");
  } catch (error) {
    setStatus(error.message);
  }
}

function handleKeydown(event) {
  if (shouldInsertFormulaShortcut(event)) {
    event.preventDefault();
    void insertFormula();
    return;
  }

  if (shouldClearInputShortcut(event)) {
    event.preventDefault();
    clearInput();
  }
}

function markOfficeReady() {
  elements.hostStatus.textContent = "Word ready";
  setStatus("Ready");
}

function initialize() {
  elements.insertButton.addEventListener("click", () => {
    void insertFormula();
  });
  elements.clearButton.addEventListener("click", clearInput);
  document.addEventListener("keydown", handleKeydown);

  if (globalThis.Office?.onReady) {
    Office.onReady(markOfficeReady);
  } else {
    elements.hostStatus.textContent = "Office.js unavailable";
    setStatus("Open this pane from Word to insert formulas");
  }
}

initialize();
