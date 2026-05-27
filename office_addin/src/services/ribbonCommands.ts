export type RibbonCommandName =
  | "insert"
  | "numbered"
  | "ocr"
  | "loadSelected"
  | "deleteSelected"
  | "renumber";

export type RibbonCommand = {
  name: RibbonCommandName;
  id: string;
  createdAt: number;
};

const STORAGE_KEY = "latexsnipper.pendingRibbonCommand";

type OfficeRuntimeLike = {
  storage: {
    getItem(key: string): Promise<string | null>;
    setItem(key: string, value: string): Promise<void>;
    removeItem(key: string): Promise<void>;
  };
};

function commandStorage(): OfficeRuntimeLike["storage"] {
  const runtime = (globalThis as typeof globalThis & { OfficeRuntime?: OfficeRuntimeLike }).OfficeRuntime;
  if (!runtime?.storage) {
    throw new Error("OfficeRuntime storage is required for Ribbon commands.");
  }
  return runtime.storage;
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
  await commandStorage().setItem(STORAGE_KEY, JSON.stringify(command));
}

export async function readRibbonCommand(): Promise<RibbonCommand | null> {
  const raw = String((await commandStorage().getItem(STORAGE_KEY)) || "");
  if (!raw) {
    return null;
  }
  const parsed = JSON.parse(raw) as RibbonCommand;
  if (!parsed.name || !parsed.id) {
    throw new Error("Invalid Ribbon command payload.");
  }
  return parsed;
}

export async function clearRibbonCommand(command: RibbonCommand): Promise<void> {
  const current = await readRibbonCommand();
  if (!current || current.id !== command.id) {
    return;
  }
  await commandStorage().removeItem(STORAGE_KEY);
}
