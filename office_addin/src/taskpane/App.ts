import "../styles/taskpane.css";

import { BridgeClient, type BridgeHealth, type ConversionResult } from "../services/bridgeClient";
import { loadEquationSource, loadSession, saveSession } from "../services/equationSession";
import { normalizeOfficeLatex } from "../services/latexNormalize";
import { clearRibbonCommand, readRibbonCommand, RibbonCommand } from "../services/ribbonCommands";
import {
  deleteSelectedEquationFromWord,
  getSelectedEquationIdFromWord,
  insertEquationIntoWord,
  loadSelectedEquationFromWord,
  renumberWordEquations,
  updateEquationInWord
} from "../office/wordInsert";
import { insertEquationIntoPowerPoint } from "../office/powerpointInsert";
import { MathLiveEditor } from "./mathliveEditor";

const DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765";
const SELECTED_EQUATION_STATUS = "LaTeXSnipper equation selected. Click Load to edit.";

type Elements = {
  hostLabel: HTMLElement;
  statusBanner: HTMLElement;
  bridgeUrl: HTMLInputElement;
  bridgeToken: HTMLInputElement;
  mathfieldHost: HTMLElement;
  latexOutput: HTMLTextAreaElement;
  keyboardButton: HTMLButtonElement;
  displayMode: HTMLInputElement;
  autoNumber: HTMLInputElement;
  manualNumber: HTMLInputElement;
  healthButton: HTMLButtonElement;
  ocrButton: HTMLButtonElement;
  renumberButton: HTMLButtonElement;
  insertButton: HTMLButtonElement;
};

let formulaEditor: MathLiveEditor | null = null;
let officeHost: Office.HostType | undefined;
let selectionNoticeEquationId = "";
let lastHandledCommandId = "";
let actionBusy = false;
let officeDialog: Office.Dialog | null = null;

Office.onReady(async (info) => {
  const elements = resolveElements();
  officeHost = info.host;
  elements.hostLabel.textContent = `${info.host || "Office"} add-in`;
  restoreSession(elements);
  refreshCommandAvailability(elements);
  formulaEditor = await MathLiveEditor.create(elements.mathfieldHost, elements.latexOutput, "\\int_0^1 x^2\\,dx");
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
    statusBanner: requiredElement("statusBanner", HTMLElement),
    bridgeUrl: requiredElement("bridgeUrl", HTMLInputElement),
    bridgeToken: requiredElement("bridgeToken", HTMLInputElement),
    mathfieldHost: requiredElement("mathfieldHost", HTMLElement),
    latexOutput: requiredElement("latexOutput", HTMLTextAreaElement),
    keyboardButton: requiredElement("keyboardButton", HTMLButtonElement),
    displayMode: requiredElement("displayMode", HTMLInputElement),
    autoNumber: requiredElement("autoNumber", HTMLInputElement),
    manualNumber: requiredElement("manualNumber", HTMLInputElement),
    healthButton: requiredElement("healthButton", HTMLButtonElement),
    ocrButton: requiredElement("ocrButton", HTMLButtonElement),
    renumberButton: requiredElement("renumberButton", HTMLButtonElement),
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
    if (!equationId) {
      selectionNoticeEquationId = "";
      if (elements.statusBanner.textContent === SELECTED_EQUATION_STATUS) {
        setStatus(elements, "Ready.", "ok");
      }
      return;
    }
    if (equationId === selectionNoticeEquationId) {
      return;
    }
    const record = loadEquationSource(equationId);
    if (record?.latex) {
      selectionNoticeEquationId = equationId;
      setStatus(elements, SELECTED_EQUATION_STATUS, "ok");
    }
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
      await numberSelectedEquation(elements);
      return;
    case "ocr":
      await runScreenshotOcr(elements);
      return;
    case "loadSelected":
      await loadSelectedEquation(elements);
      return;
    case "deleteSelected":
      await deleteSelectedEquation(elements);
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
  elements.renumberButton.addEventListener("click", () => runAction(elements, () => renumberEquations(elements)));
  elements.insertButton.addEventListener("click", () => runAction(elements, () => insertCurrentLatex(elements)));
  elements.keyboardButton.style.display = "none";
  elements.bridgeUrl.addEventListener("change", () => persistBridgeInputs(elements));
  elements.bridgeToken.addEventListener("change", () => persistBridgeInputs(elements));
  elements.bridgeUrl.addEventListener("input", () => persistBridgeInputs(elements));
  elements.bridgeToken.addEventListener("input", () => persistBridgeInputs(elements));
  elements.manualNumber.addEventListener("input", () => {
    if (elements.manualNumber.value.trim()) {
      elements.autoNumber.checked = false;
    }
  });
  elements.autoNumber.addEventListener("change", () => {
    if (elements.autoNumber.checked) {
      elements.manualNumber.value = "";
    }
  });
}

function applyLaunchMode(elements: Elements): boolean {
  const mode = new URLSearchParams(window.location.search).get("mode");
  if (mode === "numbered") {
    elements.displayMode.checked = true;
    elements.autoNumber.checked = true;
    elements.manualNumber.value = "";
    setStatus(elements, "Numbered equation mode is enabled.", "ok");
    return true;
  }
  if (mode === "insert") {
    setStatus(elements, "Insert mode is ready.", "ok");
    formulaEditor?.focus();
    return true;
  }
  if (mode === "ocr") {
    window.setTimeout(() => {
      void runAction(elements, () => runScreenshotOcr(elements));
    }, 200);
    return true;
  }
  if (mode === "editor") {
    if (elements.bridgeToken.value.trim()) {
      window.setTimeout(() => openDialogEditor(elements), 300);
    } else {
      setStatus(elements, "Connect to the LaTeXSnipper bridge first, then open the editor.", "error");
    }
    return true;
  }
  return false;
}

async function tryAutoConfigureBridge(elements: Elements): Promise<boolean> {
  try {
    const health = await configureBridge(elements, DEFAULT_BRIDGE_URL, 2500);
    const ocrText = health.features.capture_recognize ? "OCR enabled" : "conversion only";
    setStatus(elements, `Connected to local LaTeXSnipper bridge (${ocrText}).`, health.features.capture_recognize ? "ok" : "");
    return true;
  } catch {
    if (!elements.bridgeToken.value.trim()) {
      setStatus(elements, "Start LaTeXSnipper Office bridge to auto-configure the add-in.", "error");
      refreshCommandAvailability(elements);
      return true;
    }
  }
  return false;
}

async function testConnection(elements: Elements): Promise<void> {
  const health = await configureBridge(elements, elements.bridgeUrl.value, 7000);
  setStatus(elements, `Connected to ${health.name}, protocol ${health.protocol}.`, "ok");
}

async function configureBridge(elements: Elements, baseUrl: string, timeoutMs: number): Promise<BridgeHealth> {
  const configClient = new BridgeClient(baseUrl.trim() || DEFAULT_BRIDGE_URL, "", timeoutMs);
  const config = await configClient.config();
  if (!config.token.trim()) {
    throw new Error("Bridge config did not return a session token.");
  }
  elements.bridgeUrl.value = config.bridge_url || baseUrl || DEFAULT_BRIDGE_URL;
  elements.bridgeToken.value = config.token;
  await persistSession(elements);
  refreshCommandAvailability(elements);
  const health = await clientFromElements(elements).health(true);
  if (!health.features.convert_latex) {
    throw new Error("Connected bridge does not support LaTeX conversion.");
  }
  return health;
}

async function convertCurrentLatex(elements: Elements): Promise<ConversionResult> {
  await persistSession(elements);
  const latex = readLatex(elements);
  setStatus(elements, "Converting LaTeX through bridge.");
  const conversion = await clientFromElements(elements).convertLatex(latex, ["omml"]);
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
  const conversion = await convertCurrentLatex(elements);
  await insertEquationIntoWord(draft, conversion);
  setStatus(elements, "Inserted equation into Word.", "ok");
}

async function loadSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error("Equation editing is available in Word only.");
  }
  const selected = await loadSelectedEquationFromWord();
  // Sync equation content and numbering to the sidebar
  formulaEditor?.setLatex(selected.latex);
  elements.latexOutput.value = selected.latex;
  elements.displayMode.checked = selected.display;
  elements.autoNumber.checked = selected.numbering === "auto";
  elements.manualNumber.value = selected.numbering === "manual" ? (selected.numberValue || "") : "";
  openDialogEditor(elements, selected.latex, selected.equationId, selected.numberValue);
  setStatus(elements, "Opened equation in editor.", "ok");
}

async function deleteSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error("Deleting equations is available in Word only.");
  }
  await deleteSelectedEquationFromWord();
  selectionNoticeEquationId = "";
  setStatus(elements, "Deleted selected equation.", "ok");
}

async function numberSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error("Equation numbering is available in Word only.");
  }
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    throw new Error("Select a LaTeXSnipper equation to add numbering.");
  }
  const record = loadEquationSource(equationId);
  if (!record || !record.latex) {
    throw new Error("The selected equation does not have saved LaTeX source.");
  }
  if (record.numbering && record.numbering !== "none") {
    setStatus(elements, "Selected equation already has numbering.", "");
    return;
  }
  formulaEditor?.setLatex(record.latex);
  elements.latexOutput.value = record.latex;
  const draft = {
    latex: record.latex,
    display: true,
    numbering: "auto" as const,
    manualNumber: undefined as string | undefined,
    equationId,
    numberValue: record.numberValue,
  };
  const conversion = await convertCurrentLatex(elements);
  await updateEquationInWord(draft, conversion);
  setStatus(elements, "Added numbering to selected equation.", "ok");
  resetSidebarAfterUpdate(elements);
}

async function renumberEquations(elements: Elements): Promise<void> {
  const count = await renumberWordEquations();
  setStatus(elements, count ? `Renumbered ${count} equations.` : "No numbered LaTeXSnipper equations found.", count ? "ok" : "");
}

async function runScreenshotOcr(elements: Elements): Promise<void> {
  const client = clientFromElements(elements);
  setStatus(elements, "Waiting for the next LaTeXSnipper recognition. Use the global shortcut, then capture a region.");
  let lastStatus = "waiting";
  const statusTimer = window.setInterval(() => {
    void client.recognitionStatus().then((status) => {
      if (status.state === lastStatus) {
        return;
      }
      lastStatus = status.state;
      if (status.state === "waiting") {
        setStatus(elements, "Waiting for the next LaTeXSnipper recognition. Use the global shortcut, then capture a region.");
      } else if (status.state === "recognizing") {
        setStatus(elements, "Recognizing formula in LaTeXSnipper. First OCR after startup can take longer.");
      }
    }).catch(() => undefined);
  }, 900);
  try {
    const result = await client.recognizeScreenshot();
    const latex = normalizeOfficeLatex(result.latex);
    if (!latex) {
      throw new Error("Screenshot OCR returned an empty result.");
    }
    formulaEditor?.setLatex(latex);
    setStatus(elements, "Screenshot OCR result loaded.", "ok");
  } finally {
    window.clearInterval(statusTimer);
  }
}

async function persistSession(elements: Elements): Promise<void> {
  await saveSession({
    bridgeUrl: elements.bridgeUrl.value.trim(),
    bridgeToken: elements.bridgeToken.value.trim()
  });
}

function persistBridgeInputs(elements: Elements): void {
  refreshCommandAvailability(elements);
  void persistSession(elements);
}

function clientFromElements(elements: Elements): BridgeClient {
  const token = elements.bridgeToken.value.trim();
  if (!token) {
    throw new Error("Click Connect to refresh the LaTeXSnipper bridge token.");
  }
  return new BridgeClient(elements.bridgeUrl.value || DEFAULT_BRIDGE_URL, token);
}

function readLatex(elements: Elements): string {
  const latex = normalizeOfficeLatex(formulaEditor?.getLatex() || elements.latexOutput.value);
  if (!latex) {
    throw new Error("LaTeX is required.");
  }
  return latex;
}

function openDialogEditor(
  elements: Elements,
  latex?: string,
  equationId?: string,
  numberValue?: string
): void {
  if (officeDialog) {
    try {
      officeDialog.close();
    } catch {
      // Previous dialog may already be closed.
    }
    officeDialog = null;
  }
  const params = new URLSearchParams();
  params.set("mode", equationId ? "update" : "insert");
  params.set("bridgeUrl", elements.bridgeUrl.value || DEFAULT_BRIDGE_URL);
  params.set("bridgeToken", elements.bridgeToken.value.trim());
  if (latex) {
    params.set("latex", latex);
  }
  if (equationId) {
    params.set("equationId", equationId);
    params.set("display", String(elements.displayMode.checked));
    params.set("autoNumber", String(elements.autoNumber.checked));
    params.set("manualNumber", elements.manualNumber.value.trim());
    if (numberValue) {
      params.set("numberValue", numberValue);
    }
  }
  const dialogUrl = `${window.location.origin}${window.location.pathname.replace(
    "taskpane.html",
    "src/dialog/editorDialog.html"
  )}?${params.toString()}`;
  Office.context.ui.displayDialogAsync(dialogUrl, { height: 60, width: 48 }, (result) => {
    if (result.status === Office.AsyncResultStatus.Failed) {
      setStatus(elements, `Failed to open editor: ${result.error.message}`, "error");
      return;
    }
    officeDialog = result.value;
    officeDialog.addEventHandler(Office.EventType.DialogMessageReceived, (arg: {
      message?: string;
      error?: number;
    }) => {
      if (arg.message) {
        void handleDialogMessage(elements, arg.message);
      }
    });
    officeDialog.addEventHandler(Office.EventType.DialogEventReceived, () => {
      officeDialog = null;
      resetSidebarAfterUpdate(elements);
    });
  });
}

async function handleDialogMessage(elements: Elements, raw: string): Promise<void> {
  let message: { type: string; draft?: { latex: string; display: boolean; numbering: string; manualNumber?: string; numberValue?: string }; equationId?: string };
  try {
    message = JSON.parse(raw) as typeof message;
  } catch {
    return;
  }
  switch (message.type) {
    case "insert": {
      if (!message.draft) {
        return;
      }
      const draft = message.draft;
      formulaEditor?.setLatex(draft.latex);
      elements.latexOutput.value = draft.latex;
      elements.displayMode.checked = draft.display;
      elements.autoNumber.checked = draft.numbering === "auto";
      elements.manualNumber.value = draft.numbering === "manual" ? (draft.manualNumber || "") : "";
      await runAction(elements, () => insertFromDialog(elements, draft, message.equationId));
      officeDialog?.close();
      officeDialog = null;
      break;
    }
    case "close": {
      officeDialog?.close();
      officeDialog = null;
      break;
    }
  }
}

async function insertFromDialog(
  elements: Elements,
  draft: { latex: string; display: boolean; numbering: string; manualNumber?: string; numberValue?: string },
  equationId?: string
): Promise<void> {
  if (officeHost === Office.HostType.PowerPoint) {
    await insertEquationIntoPowerPoint(
      { latex: draft.latex, display: draft.display, numbering: draft.numbering as "none" | "auto" | "manual", manualNumber: draft.manualNumber, equationId },
      clientFromElements(elements)
    );
    setStatus(elements, "Inserted equation into PowerPoint.", "ok");
    return;
  }
  const conversion = await convertCurrentLatex(elements);
  if (equationId) {
    await updateEquationInWord(
      { latex: draft.latex, display: draft.display, numbering: draft.numbering as "none" | "auto" | "manual", manualNumber: draft.manualNumber, equationId, numberValue: draft.numberValue },
      conversion
    );
    setStatus(elements, "Updated equation in Word.", "ok");
    resetSidebarAfterUpdate(elements);
  } else {
    await insertEquationIntoWord(
      { latex: draft.latex, display: draft.display, numbering: draft.numbering as "none" | "auto" | "manual", manualNumber: draft.manualNumber },
      conversion
    );
    setStatus(elements, "Inserted equation into Word.", "ok");
  }
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
  actionBusy = busy;
  refreshCommandAvailability(elements);
}

function resetSidebarAfterUpdate(elements: Elements): void {
  const initialLatex = "\\int_0^1 x^2\\,dx";
  formulaEditor?.setLatex(initialLatex);
  elements.latexOutput.value = initialLatex;
  elements.displayMode.checked = true;
  elements.autoNumber.checked = false;
  elements.manualNumber.value = "";
}

function refreshCommandAvailability(elements: Elements): void {
  const hasBridgeToken = Boolean(elements.bridgeToken.value.trim());
  const isWord = officeHost === Office.HostType.Word;
  elements.healthButton.disabled = actionBusy;
  elements.ocrButton.disabled = actionBusy || !hasBridgeToken;
  elements.renumberButton.disabled = actionBusy || !isWord;
  elements.insertButton.disabled = actionBusy || !hasBridgeToken;
  elements.healthButton.textContent = actionBusy ? "Working..." : "Connect";
}

function setStatus(elements: Elements, message: string, kind: "ok" | "error" | "" = ""): void {
  elements.statusBanner.textContent = message;
  elements.statusBanner.className = `status-banner ${kind}`.trim();
}
