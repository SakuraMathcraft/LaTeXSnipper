export type RibbonCommandName =
  | "insert"
  | "numbered"
  | "ocr"
  | "loadSelected"
  | "updateSelected"
  | "renumber";

export type RibbonCommand = {
  name: RibbonCommandName;
  id: string;
  createdAt: number;
};

const STORAGE_KEY = "latexsnipper.pendingRibbonCommand";

type OfficeRuntimeLike = {
  storage?: {
    getItem(key: string): Promise<string | null>;
    setItem(key: string, value: string): Promise<void>;
    removeItem(key: string): Promise<void>;
  };
};

function officeRuntime(): OfficeRuntimeLike | undefined {
  return (globalThis as typeof globalThis & { OfficeRuntime?: OfficeRuntimeLike }).OfficeRuntime;
}

export function createRibbonCommand(name: RibbonCommandName): RibbonCommand {
  return {
    name,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    createdAt: Date.now()
  };
}

export async function enqueueRibbonCommand(name: RibbonCommandName): Promise<void> {
  const command = createRibbonCommand(name);
  const serialized = JSON.stringify(command);
  try {
    const runtime = officeRuntime();
    if (runtime?.storage) {
      await runtime.storage.setItem(STORAGE_KEY, serialized);
      return;
    }
  } catch {
    // Fall back to localStorage in older Office command runtimes.
  }
  localStorage.setItem(STORAGE_KEY, serialized);
}

export async function readRibbonCommand(): Promise<RibbonCommand | null> {
  let raw = "";
  try {
    const runtime = officeRuntime();
    if (runtime?.storage) {
      raw = String((await runtime.storage.getItem(STORAGE_KEY)) || "");
    }
  } catch {
    raw = "";
  }
  if (!raw) {
    raw = localStorage.getItem(STORAGE_KEY) || "";
  }
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as RibbonCommand;
    return parsed && parsed.name && parsed.id ? parsed : null;
  } catch {
    return null;
  }
}

export async function clearRibbonCommand(command: RibbonCommand): Promise<void> {
  const current = await readRibbonCommand();
  if (!current || current.id !== command.id) {
    return;
  }
  try {
    const runtime = officeRuntime();
    if (runtime?.storage) {
      await runtime.storage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Ignore and clear localStorage below.
  }
  localStorage.removeItem(STORAGE_KEY);
}
