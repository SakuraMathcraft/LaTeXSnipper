const BRIDGE_URL_KEY = "latexsnipper.bridgeUrl";
const BRIDGE_TOKEN_KEY = "latexsnipper.bridgeToken";
const NUMBERING_KEY = "latexsnipper.equationNumbering";
const EQUATION_SOURCE_PREFIX = "latexsnipper.equationSource.";

type NumberingState = {
  next: number;
};

export type SavedSession = {
  bridgeUrl: string;
  bridgeToken: string;
};

export function loadSession(): SavedSession {
  const settings = Office.context.document.settings;
  return {
    bridgeUrl: String(settings.get(BRIDGE_URL_KEY) || "http://127.0.0.1:8765"),
    bridgeToken: String(settings.get(BRIDGE_TOKEN_KEY) || "")
  };
}

export function saveSession(session: SavedSession): Promise<void> {
  const settings = Office.context.document.settings;
  settings.set(BRIDGE_URL_KEY, session.bridgeUrl);
  settings.set(BRIDGE_TOKEN_KEY, session.bridgeToken);
  return saveSettings();
}

export type EquationSourceRecord = {
  id: string;
  latex: string;
  display?: boolean;
  numbering?: string;
  numberValue?: string;
  updatedAt: string;
};

export async function saveEquationSource(
  latex: string,
  equationId?: string,
  display?: boolean,
  numbering?: string,
  numberValue?: string
): Promise<string> {
  const id = equationId || createEquationId();
  Office.context.document.settings.set(`${EQUATION_SOURCE_PREFIX}${id}`, {
    id,
    latex,
    display,
    numbering,
    numberValue,
    updatedAt: new Date().toISOString()
  });
  await saveSettings();
  return id;
}

export async function allocateEquationNumber(): Promise<string> {
  const settings = Office.context.document.settings;
  const state = readNumberingState(settings.get(NUMBERING_KEY));
  const current = state.next;
  settings.set(NUMBERING_KEY, { next: current + 1 });
  await saveSettings();
  return `(${current})`;
}

export function loadEquationSource(equationId: string): EquationSourceRecord | null {
  const record = Office.context.document.settings.get(`${EQUATION_SOURCE_PREFIX}${equationId}`);
  if (typeof record === "object" && record !== null && "latex" in record) {
    const r = record as Record<string, unknown>;
    return {
      id: String(r.id || equationId),
      latex: String(r.latex || ""),
      display: typeof r.display === "boolean" ? r.display : undefined,
      numbering: typeof r.numbering === "string" ? r.numbering : undefined,
      numberValue: typeof r.numberValue === "string" ? r.numberValue : undefined,
      updatedAt: String(r.updatedAt || ""),
    };
  }
  return null;
}

function readNumberingState(raw: unknown): NumberingState {
  if (typeof raw === "object" && raw !== null && "next" in raw) {
    const value = Number((raw as NumberingState).next);
    if (Number.isFinite(value) && value > 0) {
      return { next: Math.floor(value) };
    }
  }
  return { next: 1 };
}

function saveSettings(): Promise<void> {
  return new Promise((resolve, reject) => {
    Office.context.document.settings.saveAsync((result) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) {
        resolve();
        return;
      }
      reject(new Error(result.error?.message || "Failed to save Office document settings."));
    });
  });
}

function createEquationId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `eq-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
