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
import { configureLocale, currentLocale, displayMessage, localizeDocument, t } from "../services/i18n";
import { MathLiveEditor } from "./mathliveEditor";

const DEFAULT_BRIDGE_URL = window.location.port === "8765"
  ? window.location.origin
  : "https://localhost:8765";

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
  displayOption: HTMLElement;
  numberingPanel: HTMLElement;
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
let officeDialogKind: "editor" | "help" | null = null;

Office.onReady(async (info) => {
  configureLocale(Office.context.displayLanguage);
  localizeDocument();
  const elements = resolveElements();
  officeHost = info.host;
  elements.hostLabel.textContent = t("officeAddin", { host: info.host || "Office" });
  configureHostUi(elements);
  restoreSession(elements);
  refreshCommandAvailability(elements);
  wireEvents(elements);
  installSelectionTracking(elements);
  startRibbonCommandPolling(elements);
  void initializeFormulaEditor(elements);
  const configured = await tryAutoConfigureBridge(elements);
  if (!configured) {
    setStatus(elements, t("ready"), "ok");
  }
});

async function initializeFormulaEditor(elements: Elements): Promise<void> {
  try {
    formulaEditor = await MathLiveEditor.create(elements.mathfieldHost, elements.latexOutput, "\\int_0^1 x^2\\,dx");
  } catch (error: unknown) {
    setStatus(elements, displayMessage(error instanceof Error ? error.message : String(error)), "error");
  }
}

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
    displayOption: requiredElement("displayOption", HTMLElement),
    numberingPanel: requiredElement("numberingPanel", HTMLElement),
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
      void refreshSelectedEquationState(elements).catch((error: unknown) => {
        setStatus(elements, displayMessage(error instanceof Error ? error.message : String(error)), "error");
      });
    }, 300);
  };
  Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, handler);
}

async function refreshSelectedEquationState(elements: Elements): Promise<void> {
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    selectionNoticeEquationId = "";
    if (elements.statusBanner.textContent === t("selectedEquation")) {
      setStatus(elements, t("ready"), "ok");
    }
    return;
  }
  if (equationId === selectionNoticeEquationId) {
    return;
  }
  const record = loadEquationSource(equationId);
  if (record?.latex) {
    selectionNoticeEquationId = equationId;
    setStatus(elements, t("selectedEquation"), "ok");
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
    case "editor":
      openDialogEditor(elements);
      return;
    case "insert":
      await insertCurrentLatex(elements);
      return;
    case "numbered":
      if (officeHost === Office.HostType.PowerPoint) {
        openDialogEditor(elements, readLatex(elements), undefined, undefined, true);
        setStatus(elements, t("pptManualNumberPrompt"), "ok");
      } else {
        await numberSelectedEquation(elements);
      }
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
    case "help":
      openHelpDialog(elements);
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

function configureHostUi(elements: Elements): void {
  const isPowerPoint = officeHost === Office.HostType.PowerPoint;
  elements.displayOption.hidden = isPowerPoint;
  elements.numberingPanel.hidden = isPowerPoint;
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

async function tryAutoConfigureBridge(elements: Elements): Promise<boolean> {
  try {
    await configureBridge(elements, DEFAULT_BRIDGE_URL, 2500);
    setStatus(elements, t("connectedBridge"), "ok");
    return true;
  } catch {
    if (!elements.bridgeToken.value.trim()) {
      setStatus(elements, t("startBridge"), "error");
      refreshCommandAvailability(elements);
      return true;
    }
  }
  return false;
}

async function testConnection(elements: Elements): Promise<void> {
  await configureBridge(elements, elements.bridgeUrl.value, 7000);
  setStatus(elements, t("connectedBridge"), "ok");
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
  return clientFromElements(elements).health(true);
}

async function convertCurrentLatex(elements: Elements): Promise<ConversionResult> {
  await persistSession(elements);
  const latex = readLatex(elements);
  setStatus(elements, t("converting"));
  const conversion = await clientFromElements(elements).convertLatex(latex, ["omml"]);
  setStatus(elements, t("converted"), "ok");
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
    setStatus(elements, t("insertedPpt"), "ok");
    return;
  }
  const conversion = await convertCurrentLatex(elements);
  await insertEquationIntoWord(draft, conversion);
  setStatus(elements, t("insertedWord"), "ok");
}

async function loadSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error(t("wordOnlyEdit"));
  }
  const selected = await loadSelectedEquationFromWord();
  formulaEditor?.setLatex(selected.latex);
  elements.latexOutput.value = selected.latex;
  elements.displayMode.checked = selected.display;
  elements.autoNumber.checked = selected.numbering === "auto";
  elements.manualNumber.value = selected.numbering === "manual" ? (selected.numberValue || "") : "";
  openDialogEditor(elements, selected.latex, selected.equationId, selected.numberValue);
  setStatus(elements, t("openedEditor"), "ok");
}

async function deleteSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error(t("wordOnlyDelete"));
  }
  await deleteSelectedEquationFromWord();
  selectionNoticeEquationId = "";
  setStatus(elements, t("deletedEquation"), "ok");
}

async function numberSelectedEquation(elements: Elements): Promise<void> {
  if (officeHost !== Office.HostType.Word) {
    throw new Error(t("wordOnlyNumbering"));
  }
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    throw new Error(t("selectNumber"));
  }
  const record = loadEquationSource(equationId);
  if (!record || !record.latex) {
    throw new Error(t("missingSource"));
  }
  if (record.numbering && record.numbering !== "none") {
    setStatus(elements, t("alreadyNumbered"), "");
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
  setStatus(elements, t("addedNumber"), "ok");
  resetSidebarAfterUpdate(elements);
}

async function renumberEquations(elements: Elements): Promise<void> {
  const count = await renumberWordEquations();
  setStatus(elements, count ? t("renumbered", { count }) : t("noNumbered"), count ? "ok" : "");
}

async function runScreenshotOcr(elements: Elements): Promise<void> {
  const client = clientFromElements(elements);
  setStatus(elements, t("waitingCapture"));
  let lastStatus = "waiting";
  const statusTimer = window.setInterval(() => {
    void client.recognitionStatus().then((status) => {
      if (status.state === lastStatus) {
        return;
      }
      lastStatus = status.state;
      if (status.state === "waiting") {
        setStatus(elements, t("waitingCapture"));
      } else if (status.state === "recognizing") {
        setStatus(elements, t("recognizing"));
      }
    }).catch(() => undefined);
  }, 900);
  try {
    const result = await client.recognizeScreenshot();
    const latex = normalizeOfficeLatex(result.latex);
    if (!latex) {
      throw new Error(t("ocrEmpty"));
    }
    formulaEditor?.setLatex(latex);
    elements.latexOutput.value = latex;
    if (officeDialog && officeDialogKind === "editor") {
      officeDialog.messageChild(JSON.stringify({ type: "ocrResult", latex }));
    }
    setStatus(elements, t("ocrLoaded"), "ok");
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
    throw new Error(t("connectRefresh"));
  }
  return new BridgeClient(elements.bridgeUrl.value || DEFAULT_BRIDGE_URL, token);
}

function readLatex(elements: Elements): string {
  const latex = normalizeOfficeLatex(formulaEditor?.getLatex() || elements.latexOutput.value);
  if (!latex) {
    throw new Error(t("latexRequired"));
  }
  return latex;
}

function openDialogEditor(
  elements: Elements,
  latex?: string,
  equationId?: string,
  numberValue?: string,
  requireManualNumber = false
): void {
  closeOfficeDialog();
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
  params.set("host", officeHost === Office.HostType.PowerPoint ? "powerpoint" : "word");
  if (requireManualNumber) {
    params.set("requireManualNumber", "true");
  }
  params.set("locale", currentLocale());
  const dialogUrl = `${window.location.origin}${window.location.pathname.replace(
    "taskpane.html",
    "src/dialog/editorDialog.html"
  )}?${params.toString()}`;
  Office.context.ui.displayDialogAsync(dialogUrl, { height: 60, width: 48 }, (result) => {
    if (result.status === Office.AsyncResultStatus.Failed) {
      setStatus(elements, t("failedEditor", { message: result.error.message }), "error");
      return;
    }
    officeDialog = result.value;
    officeDialogKind = "editor";
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
      officeDialogKind = null;
      resetSidebarAfterUpdate(elements);
    });
  });
}

function openHelpDialog(elements: Elements): void {
  closeOfficeDialog();
  const helpPage = currentLocale() === "zh-CN" ? "help.zh-cn.html" : "help.html";
  const dialogUrl = `${window.location.origin}${window.location.pathname.replace("taskpane.html", helpPage)}`;
  Office.context.ui.displayDialogAsync(dialogUrl, { height: 80, width: 58 }, (result) => {
    if (result.status === Office.AsyncResultStatus.Failed) {
      setStatus(elements, t("failedHelp", { message: result.error.message }), "error");
      return;
    }
    officeDialog = result.value;
    officeDialogKind = "help";
    officeDialog.addEventHandler(Office.EventType.DialogEventReceived, () => {
      officeDialog = null;
      officeDialogKind = null;
    });
  });
}

function closeOfficeDialog(): void {
  if (!officeDialog) {
    return;
  }
  try {
    officeDialog.close();
  } catch {
  } finally {
    officeDialog = null;
    officeDialogKind = null;
  }
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
      const inserted = await runAction(elements, () => insertFromDialog(elements, draft, message.equationId));
      if (!inserted) {
        officeDialog?.messageChild(JSON.stringify({
          type: "insertFailed",
          message: elements.statusBanner.textContent || t("latexRequired")
        }));
        return;
      }
      officeDialog?.close();
      officeDialog = null;
      officeDialogKind = null;
      break;
    }
    case "close": {
      officeDialog?.close();
      officeDialog = null;
      officeDialogKind = null;
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
    setStatus(elements, t("insertedPpt"), "ok");
    return;
  }
  const conversion = await convertCurrentLatex(elements);
  if (equationId) {
    await updateEquationInWord(
      { latex: draft.latex, display: draft.display, numbering: draft.numbering as "none" | "auto" | "manual", manualNumber: draft.manualNumber, equationId, numberValue: draft.numberValue },
      conversion
    );
    setStatus(elements, t("updatedWord"), "ok");
    resetSidebarAfterUpdate(elements);
  } else {
    await insertEquationIntoWord(
      { latex: draft.latex, display: draft.display, numbering: draft.numbering as "none" | "auto" | "manual", manualNumber: draft.manualNumber },
      conversion
    );
    setStatus(elements, t("insertedWord"), "ok");
  }
}

async function runAction(elements: Elements, action: () => Promise<void>): Promise<boolean> {
  setBusy(elements, true);
  setStatus(elements, t("workingButton"));
  try {
    await action();
    return true;
  } catch (error) {
    setStatus(elements, displayMessage(error instanceof Error ? error.message : String(error)), "error");
    return false;
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
  elements.healthButton.textContent = actionBusy ? t("workingButton") : t("connect");
}

function setStatus(elements: Elements, message: string, kind: "ok" | "error" | "" = ""): void {
  elements.statusBanner.textContent = message;
  elements.statusBanner.className = `status-banner ${kind}`.trim();
}
