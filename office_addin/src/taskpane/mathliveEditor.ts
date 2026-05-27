import type { MathfieldElement } from "mathlive";

type LatexChangeCallback = (latex: string) => void;
type MathLiveModule = typeof import("mathlive");
type MathfieldConstructor = MathLiveModule["MathfieldElement"];

const MATHFIELD_TAG_NAME = "math-field";

let mathfieldConstructorPromise: Promise<MathfieldConstructor> | null = null;

function loadMathfieldConstructor(): Promise<MathfieldConstructor> {
  if (!mathfieldConstructorPromise) {
    mathfieldConstructorPromise = customElements.whenDefined(MATHFIELD_TAG_NAME).then(() => {
      const Mathfield = customElements.get(MATHFIELD_TAG_NAME);
      if (!Mathfield) {
        throw new Error("MathLive failed to register the math-field element.");
      }
      return Mathfield as unknown as MathfieldConstructor;
    });
  }
  return mathfieldConstructorPromise;
}

export class MathLiveCore {
  readonly mathfield: MathfieldElement;
  private latexChangeCallbacks: LatexChangeCallback[] = [];

  static async create(host: HTMLElement, initialLatex = ""): Promise<MathLiveCore> {
    const Mathfield = await loadMathfieldConstructor();
    return new MathLiveCore(host, Mathfield, initialLatex);
  }

  private constructor(host: HTMLElement, Mathfield: MathfieldConstructor, initialLatex: string) {
    Mathfield.fontsDirectory = "https://cdn.jsdelivr.net/npm/mathlive/fonts";
    this.mathfield = new Mathfield();
    this.configureMathfield();
    host.replaceChildren(this.mathfield);
    this.setLatex(initialLatex);
    this.installListeners();
  }

  getLatex(): string {
    return this.mathfield.getValue("latex-expanded").trim();
  }

  setLatex(latex: string): void {
    this.mathfield.setValue(latex, { silenceNotifications: true });
  }

  focus(): void {
    this.mathfield.focus();
  }

  onLatexChange(callback: LatexChangeCallback): () => void {
    this.latexChangeCallbacks.push(callback);
    return () => {
      this.latexChangeCallbacks = this.latexChangeCallbacks.filter((cb) => cb !== callback);
    };
  }

  dispose(): void {
    this.mathfield.remove();
    this.latexChangeCallbacks.length = 0;
  }

  private configureMathfield(): void {
    this.mathfield.tabIndex = 0;
    this.mathfield.mathVirtualKeyboardPolicy = "manual";
    this.mathfield.smartFence = true;
    this.mathfield.smartMode = false;
    this.mathfield.defaultMode = "math";
    this.mathfield.style.width = "100%";
    this.mathfield.style.height = "100%";
    this.mathfield.style.display = "block";
    this.mathfield.style.fontSize = "28px";
    this.mathfield.style.overflowX = "auto";
    this.mathfield.style.overflowY = "auto";
  }

  private installListeners(): void {
    this.mathfield.addEventListener("input", () => {
      const latex = this.getLatex();
      for (const cb of this.latexChangeCallbacks) {
        cb(latex);
      }
    });
    this.mathfield.addEventListener("keydown", (event) => this.routeArrowKey(event), true);
  }

  private routeArrowKey(event: KeyboardEvent): void {
    if (document.activeElement !== this.mathfield) {
      return;
    }
    const command = {
      ArrowLeft: "moveToPreviousChar",
      ArrowRight: "moveToNextChar",
      ArrowUp: "moveUp",
      ArrowDown: "moveDown"
    }[event.key];
    if (!command) {
      return;
    }
    try {
      const handled = this.mathfield.executeCommand(
        command as unknown as Parameters<MathfieldElement["executeCommand"]>[0]
      );
      if (handled !== false) {
        event.preventDefault();
        event.stopPropagation();
      }
    } catch {
      // Keep MathLive's default behavior when a command is unsupported.
    }
  }
}

export class MathLiveEditor {
  private core: MathLiveCore;
  private latexOutput: HTMLTextAreaElement;
  private updatingFromMathLive = false;
  private latexSourceTimer: ReturnType<typeof setTimeout> | null = null;

  static async create(
    host: HTMLElement,
    latexOutput: HTMLTextAreaElement,
    initialLatex: string
  ): Promise<MathLiveEditor> {
    const core = await MathLiveCore.create(host, initialLatex);
    return new MathLiveEditor(latexOutput, core);
  }

  private constructor(latexOutput: HTMLTextAreaElement, core: MathLiveCore) {
    this.latexOutput = latexOutput;
    this.core = core;
    this.core.onLatexChange(() => this.syncLatexOutputFromMathLive());
    this.latexOutput.addEventListener("input", () => this.onLatexSourceInput());
    this.syncLatexOutputFromMathLive();
  }

  getLatex(): string {
    if (this.latexSourceTimer !== null) {
      clearTimeout(this.latexSourceTimer);
      this.latexSourceTimer = null;
      this.core.setLatex(this.latexOutput.value);
    }
    return this.core.getLatex();
  }

  setLatex(latex: string): void {
    this.core.setLatex(latex);
    this.syncLatexOutputFromMathLive();
  }

  focus(): void {
    this.core.focus();
  }

  private onLatexSourceInput(): void {
    if (this.updatingFromMathLive) return;
    if (this.latexSourceTimer !== null) clearTimeout(this.latexSourceTimer);
    this.latexSourceTimer = setTimeout(() => {
      this.latexSourceTimer = null;
      this.core.setLatex(this.latexOutput.value);
      this.core.focus();
    }, 250);
  }

  private syncLatexOutputFromMathLive(): void {
    this.updatingFromMathLive = true;
    this.latexOutput.value = this.core.getLatex();
    this.latexOutput.dispatchEvent(new Event("latexsnipper-latex-change"));
    this.updatingFromMathLive = false;
  }
}
