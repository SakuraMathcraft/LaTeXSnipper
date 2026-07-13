import { createFormulaDraft, type FormulaDraft } from "../domain/formula";

export type HostStatus = "checking" | "ready" | "outside-office" | "unsupported" | "error";
export type AgentStatus = "checking" | "ready" | "offline" | "incompatible" | "error";
export type EditorStatus = "loading" | "ready" | "error";
export type PreviewStatus = "idle" | "loading" | "ready" | "error";
export type StatusTone = "neutral" | "working" | "success" | "warning" | "danger";

export interface ConnectionState<Status extends string> {
  readonly status: Status;
  readonly label: string;
  readonly detail: string;
}

export interface AppState {
  readonly host: ConnectionState<HostStatus>;
  readonly agent: ConnectionState<AgentStatus>;
  readonly editor: {
    readonly status: EditorStatus;
    readonly dirty: boolean;
    readonly detail: string;
  };
  readonly preview: {
    readonly status: PreviewStatus;
    readonly detail: string;
    readonly mathml: string;
  };
  readonly draft: FormulaDraft;
  readonly operation: {
    readonly busy: boolean;
    readonly tone: StatusTone;
    readonly message: string;
  };
}

export function createInitialAppState(): AppState {
  return {
    host: {
      status: "checking",
      label: "正在连接 Word",
      detail: "正在等待 Office.js 初始化。",
    },
    agent: {
      status: "checking",
      label: "正在连接后台",
      detail: "正在检查本机 LaTeXSnipper 服务。",
    },
    editor: {
      status: "loading",
      dirty: false,
      detail: "正在加载本地 MathLive。",
    },
    preview: {
      status: "idle",
      detail: "输入公式后显示本地预览。",
      mathml: "",
    },
    draft: createFormulaDraft(),
    operation: {
      busy: false,
      tone: "neutral",
      message: "当前里程碑启用编辑与预览；Word 写入将在真机 Spike 通过后开启。",
    },
  };
}

type StateListener<T> = (state: Readonly<T>) => void;

export class StateStore<T> {
  readonly #listeners = new Set<StateListener<T>>();
  #state: T;

  constructor(initialState: T) {
    this.#state = initialState;
  }

  get snapshot(): Readonly<T> {
    return this.#state;
  }

  update(updater: (current: Readonly<T>) => T): void {
    const next = updater(this.#state);
    if (Object.is(next, this.#state)) {
      return;
    }
    this.#state = next;
    for (const listener of this.#listeners) {
      listener(this.#state);
    }
  }

  subscribe(listener: StateListener<T>, emitImmediately = true): () => void {
    this.#listeners.add(listener);
    if (emitImmediately) {
      listener(this.#state);
    }
    return () => this.#listeners.delete(listener);
  }
}
