import "../styles/taskpane.css";

import { BridgeClient, ConversionResult } from "../services/bridgeClient";
import { loadSession, saveSession } from "../services/equationSession";
import { insertEquationIntoWord } from "../office/wordInsert";
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
  convertButton: HTMLButtonElement;
  insertButton: HTMLButtonElement;
};

let lastConversion: ConversionResult | null = null;
let formulaEditor: MathLiveEditor | null = null;

Office.onReady((info) => {
  const elements = resolveElements();
  elements.hostLabel.textContent = `${info.host || "Office"} add-in`;
  restoreSession(elements);
  formulaEditor = new MathLiveEditor(elements.mathfieldHost, elements.latexOutput, "\\int_0^1 x^2\\,dx");
  wireEvents(elements);
  setStatus(elements, "Ready.", "ok");
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
    convertButton: requiredElement("convertButton", HTMLButtonElement),
    insertButton: requiredElement("insertButton", HTMLButtonElement)
  };
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
  elements.convertButton.addEventListener("click", () => runAction(elements, async () => {
    await convertCurrentLatex(elements);
  }));
  elements.insertButton.addEventListener("click", () => runAction(elements, () => insertCurrentLatex(elements)));
  elements.keyboardButton.addEventListener("click", () => formulaEditor?.toggleKeyboard());
  elements.bridgeUrl.addEventListener("change", () => persistSession(elements));
  elements.bridgeToken.addEventListener("change", () => persistSession(elements));
  elements.latexOutput.addEventListener("latexsnipper-latex-change", () => {
    lastConversion = null;
    elements.ommlOutput.value = "";
  });
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
  const conversion = lastConversion || (await convertCurrentLatex(elements));
  await insertEquationIntoWord(
    {
      latex: readLatex(elements),
      display: elements.displayMode.checked,
      numbering: elements.autoNumber.checked ? "auto" : elements.manualNumber.value.trim() ? "manual" : "none",
      manualNumber: elements.manualNumber.value
    },
    conversion
  );
  setStatus(elements, "Inserted equation into Word.", "ok");
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
  const latex = formulaEditor?.getLatex() || elements.latexOutput.value.trim();
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
  elements.convertButton.disabled = busy;
  elements.insertButton.disabled = busy;
}

function setStatus(elements: Elements, message: string, kind: "ok" | "error" | "" = ""): void {
  elements.status.textContent = message;
  elements.status.className = `status ${kind}`.trim();
}
