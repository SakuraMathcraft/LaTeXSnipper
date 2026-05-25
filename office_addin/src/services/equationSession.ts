const BRIDGE_URL_KEY = "latexsnipper.bridgeUrl";
const BRIDGE_TOKEN_KEY = "latexsnipper.bridgeToken";
const NUMBERING_KEY = "latexsnipper.equationNumbering";

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

export async function allocateEquationNumber(): Promise<string> {
  const settings = Office.context.document.settings;
  const state = readNumberingState(settings.get(NUMBERING_KEY));
  const current = state.next;
  settings.set(NUMBERING_KEY, { next: current + 1 });
  await saveSettings();
  return `(${current})`;
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
