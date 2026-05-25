import "../styles/taskpane.css";

import { BridgeClient, ConversionResult } from "../services/bridgeClient";
import { loadSession, saveSession } from "../services/equationSession";
import { normalizeOfficeLatex } from "../services/latexNormalize";
import { clearRibbonCommand, readRibbonCommand, RibbonCommand } from "../services/ribbonCommands";
import {
  getSelectedEquationIdFromWord,
  insertEquationIntoWord,
  loadSelectedEquationFromWord,
  renumberWordEquations
} from "../office/wordInsert";
import { insertEquationIntoPowerPoint } from "../office/powerpointInsert";
import { MathLiveEditor } from "./mathliveEditor";

type Elements = {
  hostLabel: HTMLElement;
  bridgeUrl: HTMLInputElement;
  bridgeToken: HTMLInputElement;
  mathfieldHost: HTMLElement;
  latexOutput: HTMLTextAreaElement;
  keyboardButton: HTMLButtonElement;
  displayMode: HTMLInputElement;
  autoNumber: HTMLInputElement;
  manualNumber: HTMLInputElement;
  ommlOutput: HTMLTextAreaElement;
  status: HTMLElement;
  healthButton: HTMLButtonElement;
  ocrButton: HTMLButtonElement;
  loadSelectedButton: HTMLButtonElement;
  updateSelectedButton: HTMLButtonElement;
  renumberButton: HTMLButtonElement;
  convertButton: HTMLButtonElement;
  insertButton: HTMLButtonElement;
};

let lastConversion: ConversionResult | null = null;
let formulaEditor: MathLiveEditor | null = null;
let officeHost: Office.HostType | undefined;
let selectedEquationId = "";
let lastHandledCommandId = "";

Office.onReady(async (info) => {
  const elements = resolveElements();
  officeHost = info.host;
  elements.hostLabel.textContent = `${info.host || "Office"} add-in`;
  restoreSession(elements);
  formulaEditor = new MathLiveEditor(elements.mathfieldHost, elements.latexOutput, "\\int_0^1 x^2\\,dx");
  wireEvents(elements);
  installSelectionTracking(elements);
  startRibbonCommandPolling(elements);
  const configured = await tryAutoConfigureBridge(elements);
  const launchModeApplied = applyLaunchMode(elements);
  if (!configured && !launchModeApplied) {
    setStatus(elements, "Ready.", "ok");
  }
});

function resolveElements(): Elements {
  return {
    hostLabel: requiredElement("hostLabel", HTMLElement),
    bridgeUrl: requiredElement("bridgeUrl", HTMLInputElement),
    bridgeToken: requiredElement("bridgeToken", HTMLInputElement),
    mathfieldHost: requiredElement("mathfieldHost", HTMLElement),
    latexOutput: requiredElement("latexOutput", HTMLTextAreaElement),
    keyboardButton: requiredElement("keyboardButton", HTMLButtonElement),
    displayMode: requiredElement("displayMode", HTMLInputElement),
    autoNumber: requiredElement("autoNumber", HTMLInputElement),
    manualNumber: requiredElement("manualNumber", HTMLInputElement),
    ommlOutput: requiredElement("ommlOutput", HTMLTextAreaElement),
    status: requiredElement("status", HTMLElement),
    healthButton: requiredElement("healthButton", HTMLButtonElement),
    ocrButton: requiredElement("ocrButton", HTMLButtonElement),
    loadSelectedButton: requiredElement("loadSelectedButton", HTMLButtonElement),
    updateSelectedButton: requiredElement("updateSelectedButton", HTMLButtonElement),
    renumberButton: requiredElement("renumberButton", HTMLButtonElement),
    convertButton: requiredElement("convertButton", HTMLButtonElement),
    insertButton: requiredElement("insertButton", HTMLButtonElement)
  };
}

function installSelectionTracking(elements: Elements): void {
  if (officeHost !== Office.HostType.Word) {
    return;
  }
  let timer = 0;
  const handler = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      void refreshSelectedEquationState(elements);
    }, 300);
  };
  try {
    Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, handler);
  } catch {
    // Selection tracking is a convenience layer. Load/Update still work from buttons.
  }
}

async function refreshSelectedEquationState(elements: Elements): Promise<void> {
  try {
    const equationId = await getSelectedEquationIdFromWord();
    if (!equationId || equationId === selectedEquationId) {
      return;
    }
    selectedEquationId = equationId;
    setStatus(elements, "LaTeXSnipper equation selected.", "ok");
  } catch {
    // Ignore ordinary Word selections.
  }
}

function startRibbonCommandPolling(elements: Elements): void {
  window.setInterval(() => {
    void consumeRibbonCommand(elements);
  }, 400);
}

async function consumeRibbonCommand(elements: Elements): Promise<void> {
  const command = await readRibbonCommand();
  if (!command || command.id === lastHandledCommandId) {
    return;
  }
  lastHandledCommandId = command.id;
  await clearRibbonCommand(command);
  await runAction(elements, () => executeRibbonCommand(elements, command));
}

async function executeRibbonCommand(elements: Elements, command: RibbonCommand): Promise<void> {
  switch (command.name) {
    case "insert":
      await insertCurrentLatex(elements);
      return;
    case "numbered":
      elements.displayMode.checked = true;
      elements.autoNumber.checked = true;
      await insertCurrentLatex(elements);
      return;
    case "ocr":
      await runScreenshotOcr(elements);
      return;
    case "loadSelected":
      await loadSelectedEquation(elements);
      return;
    case "updateSelected":
      await updateSelectedEquation(elements);
      return;
    case "renumber":
      await renumberEquations(elements);
      return;
  }
}

function requiredElement<T extends HTMLElement>(id: string, ctor: { new (...args: never[]): T }): T {
  const element = document.getElementById(id);
  if (!(element instanceof ctor)) {
    throw new Error(`Missing task pane element: ${id}`);
  }
  return element;
}

function restoreSession(elements: Elements): void {
  const session = loadSession();
  elements.bridgeUrl.value = session.bridgeUrl;
  elements.bridgeToken.value = session.bridgeToken;
}

function wireEvents(elements: Elements): void {
  elements.healthButton.addEventListener("click", () => runAction(elements, () => testConnection(elements)));
  elements.ocrButton.addEventListener("click", () => runAction(elements, () => runScreenshotOcr(elements)));
  elements.loadSelectedButton.addEventListener("click", () => runAction(elements, () => loadSelectedEquation(elements)));
  elements.updateSelectedButton.addEventListener("click", () => runAction(elements, () => updateSelectedEquation(elements)));
  elements.renumberButton.addEventListener("click", () => runAction(elements, () => renumberEquations(elements)));
  elements.convertButton.addEventListener("click", () => runAction(elements, async () => {
    await convertCurrentLatex(elements);
  }));
  elements.insertButton.addEventListener("click", () => runAction(elements, () => insertCurrentLatex(elements)));
  elements.keyboardButton.addEventListener("click", () => formulaEditor?.toggleKeyboard());
  window.addEventListener("keydown", (event) => handleKeyboardShortcut(event, elements));
  elements.bridgeUrl.addEventListener("change", () => persistSession(elements));
  elements.bridgeToken.addEventListener("change", () => persistSession(elements));
  elements.bridgeUrl.addEventListener("input", () => persistSession(elements));
  elements.bridgeToken.addEventListener("input", () => persistSession(elements));
  elements.latexOutput.addEventListener("latexsnipper-latex-change", () => {
    lastConversion = null;
    elements.ommlOutput.value = "";
  });
}

function handleKeyboardShortcut(event: KeyboardEvent, elements: Elements): void {
  if (!event.ctrlKey || event.altKey || event.metaKey) {
    return;
  }
  const key = event.key.toLowerCase();
  const action =
    key === "enter"
      ? () => insertCurrentLatex(elements)
      : event.shiftKey && key === "s"
        ? () => runScreenshotOcr(elements)
        : event.shiftKey && key === "l"
          ? () => loadSelectedEquation(elements)
          : event.shiftKey && key === "u"
            ? () => updateSelectedEquation(elements)
            : null;
  if (!action) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  void runAction(elements, action);
}

function applyLaunchMode(elements: Elements): boolean {
  const mode = new URLSearchParams(window.location.search).get("mode");
  if (mode === "numbered") {
    elements.displayMode.checked = true;
    elements.autoNumber.checked = true;
    setStatus(elements, "Numbered equation mode is enabled.", "ok");
    return true;
  }
  if (mode === "insert") {
    setStatus(elements, "Insert mode is ready.", "ok");
    formulaEditor?.focus(false);
    return true;
  }
  if (mode === "ocr") {
    window.setTimeout(() => {
      void runAction(elements, () => runScreenshotOcr(elements));
    }, 200);
    return true;
  }
  return false;
}

async function tryAutoConfigureBridge(elements: Elements): Promise<boolean> {
  const candidate = new BridgeClient("http://127.0.0.1:8765", "", 2500);
  try {
    const config = await candidate.config();
    elements.bridgeUrl.value = config.bridge_url;
    elements.bridgeToken.value = config.token;
    await persistSession(elements);
    const ocrText = config.features.capture_recognize ? "OCR enabled" : "conversion only";
    setStatus(elements, `Connected to local LaTeXSnipper bridge (${ocrText}).`, config.features.capture_recognize ? "ok" : "");
    return true;
  } catch {
    if (!elements.bridgeToken.value.trim()) {
      setStatus(elements, "Start LaTeXSnipper Office bridge to auto-configure the add-in.", "error");
      return true;
    }
  }
  return false;
}

async function testConnection(elements: Elements): Promise<void> {
  await persistSession(elements);
  const health = await clientFromElements(elements).health();
  setStatus(elements, `Connected to ${health.name}, protocol ${health.protocol}.`, "ok");
}

async function convertCurrentLatex(elements: Elements): Promise<ConversionResult> {
  await persistSession(elements);
  const latex = readLatex(elements);
  setStatus(elements, "Converting LaTeX through bridge.");
  const conversion = await clientFromElements(elements).convertLatex(latex, ["omml"]);
  lastConversion = conversion;
  elements.ommlOutput.value = conversion.omml || "";
  setStatus(elements, "Converted to OMML.", "ok");
  return conversion;
}

async function insertCurrentLatex(elements: Elements): Promise<void> {
  const draft = {
    latex: readLatex(elements),
    display: elements.displayMode.checked,
    numbering: elements.autoNumber.checked ? "auto" : elements.manualNumber.value.trim() ? "manual" : "none",
    manualNumber: elements.manualNumber.value
  } as const;
  if (officeHost === Office.HostType.PowerPoint) {
    await insertEquationIntoPowerPoint(draft, clientFromElements(elements));
    setStatus(elements, "Inserted equation into PowerPoint.", "ok");
    return;
  }
  const conversion = lastConversion || (await convertCurrentLatex(elements));
  await insertEquationIntoWord(draft, conversion);
  setStatus(elements, "Inserted equation into Word.", "ok");
}

async function loadSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error("Native TeX editing is currently available in Word only.");
  }
  const selected = await loadSelectedEquationFromWord();
  selectedEquationId = selected.equationId;
  formulaEditor?.setLatex(selected.latex);
  lastConversion = null;
  elements.ommlOutput.value = "";
  setStatus(elements, "Loaded selected equation source.", "ok");
}

async function updateSelectedEquation(elements: Elements): Promise<void> {
  const currentSelectionId = await getSelectedEquationIdFromWord();
  if (currentSelectionId) {
    selectedEquationId = currentSelectionId;
  }
  if (!selectedEquationId) {
    throw new Error("Select a LaTeXSnipper equation to update.");
  }
  const draft = {
    latex: readLatex(elements),
    display: elements.displayMode.checked,
    numbering: elements.autoNumber.checked ? "auto" : elements.manualNumber.value.trim() ? "manual" : "none",
    manualNumber: elements.manualNumber.value,
    equationId: selectedEquationId
  } as const;
  const conversion = await convertCurrentLatex(elements);
  await insertEquationIntoWord(draft, conversion);
  setStatus(elements, "Updated selected equation.", "ok");
}

async function renumberEquations(elements: Elements): Promise<void> {
  const count = await renumberWordEquations();
  setStatus(elements, count ? `Renumbered ${count} equations.` : "No numbered LaTeXSnipper equations found.", count ? "ok" : "");
}

async function runScreenshotOcr(elements: Elements): Promise<void> {
  const client = clientFromElements(elements);
  setStatus(elements, "Select a screen region in LaTeXSnipper.");
  const result = await client.recognizeScreenshot();
  const latex = normalizeOfficeLatex(result.latex);
  if (!latex) {
    throw new Error("Screenshot OCR returned an empty result.");
  }
  formulaEditor?.setLatex(latex);
  lastConversion = null;
  elements.ommlOutput.value = "";
  setStatus(elements, "Screenshot OCR result loaded.", "ok");
}

async function persistSession(elements: Elements): Promise<void> {
  await saveSession({
    bridgeUrl: elements.bridgeUrl.value.trim(),
    bridgeToken: elements.bridgeToken.value.trim()
  });
}

function clientFromElements(elements: Elements): BridgeClient {
  return new BridgeClient(elements.bridgeUrl.value, elements.bridgeToken.value);
}

function readLatex(elements: Elements): string {
  const latex = normalizeOfficeLatex(formulaEditor?.getLatex() || elements.latexOutput.value);
  if (!latex) {
    throw new Error("LaTeX is required.");
  }
  return latex;
}

async function runAction(elements: Elements, action: () => Promise<void>): Promise<void> {
  setBusy(elements, true);
  setStatus(elements, "Working.");
  try {
    await action();
  } catch (error) {
    setStatus(elements, error instanceof Error ? error.message : String(error), "error");
  } finally {
    setBusy(elements, false);
  }
}

function setBusy(elements: Elements, busy: boolean): void {
  elements.healthButton.disabled = busy;
  elements.ocrButton.disabled = busy;
  elements.loadSelectedButton.disabled = busy;
  elements.updateSelectedButton.disabled = busy;
  elements.renumberButton.disabled = busy;
  elements.convertButton.disabled = busy;
  elements.insertButton.disabled = busy;
  elements.healthButton.textContent = busy ? "Working..." : "Connect";
}

function setStatus(elements: Elements, message: string, kind: "ok" | "error" | "" = ""): void {
  elements.status.textContent = message;
  elements.status.className = `status ${kind}`.trim();
}
