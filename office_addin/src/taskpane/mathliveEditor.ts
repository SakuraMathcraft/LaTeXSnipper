import { MathfieldElement } from "mathlive";

export class MathLiveEditor {
  private readonly mathfield: MathfieldElement;
  private readonly latexOutput: HTMLTextAreaElement;

  constructor(host: HTMLElement, latexOutput: HTMLTextAreaElement, initialLatex: string) {
    this.latexOutput = latexOutput;
    this.mathfield = new MathfieldElement();
    this.configureMathfield();
    host.replaceChildren(this.mathfield);
    this.setLatex(initialLatex);
    this.installListeners();
    this.syncLatexOutput();
  }

  getLatex(): string {
    return this.mathfield.getValue("latex-expanded").trim();
  }

  setLatex(latex: string): void {
    this.mathfield.setValue(latex, { silenceNotifications: true });
    this.syncLatexOutput();
  }

  focus(showKeyboard = true): void {
    this.mathfield.focus();
    if (showKeyboard) {
      this.ensureKeyboardVisible();
    }
  }

  toggleKeyboard(): void {
    const keyboard = window.mathVirtualKeyboard;
    if (!keyboard) {
      this.focus(true);
      return;
    }
    try {
      keyboard.visible = !keyboard.visible;
      this.syncKeyboardState();
      if (keyboard.visible) {
        this.mathfield.focus();
      }
    } catch {
      this.focus(true);
    }
  }

  private configureMathfield(): void {
    MathfieldElement.fontsDirectory = "https://cdn.jsdelivr.net/npm/mathlive/fonts";
    this.mathfield.tabIndex = 0;
    this.mathfield.mathVirtualKeyboardPolicy = "auto";
    this.mathfield.smartFence = true;
    this.mathfield.smartMode = false;
    this.mathfield.defaultMode = "math";
    this.mathfield.style.overflowX = "auto";
    this.mathfield.style.overflowY = "auto";

    const keyboard = window.mathVirtualKeyboard;
    if (keyboard) {
      keyboard.container = document.body;
      keyboard.addEventListener?.("geometrychange", () => this.syncKeyboardState());
      keyboard.addEventListener?.("visibilitychange", () => this.syncKeyboardState());
    }
  }

  private installListeners(): void {
    this.mathfield.addEventListener("input", () => this.syncLatexOutput());
    this.mathfield.addEventListener("keydown", (event) => this.routeArrowKey(event), true);
    this.mathfield.addEventListener("focusin", () => queueMicrotask(() => this.syncKeyboardState()));
    this.mathfield.addEventListener("focusout", () => setTimeout(() => this.syncKeyboardState(), 0));
    this.latexOutput.addEventListener("change", () => {
      this.setLatex(this.latexOutput.value);
      this.focus(false);
    });
    window.addEventListener("resize", () => this.syncKeyboardState());
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
      const handled = this.mathfield.executeCommand(command as unknown as Parameters<MathfieldElement["executeCommand"]>[0]);
      if (handled !== false) {
        event.preventDefault();
        event.stopPropagation();
      }
    } catch {
      // Keep MathLive's default behavior when a command is unsupported.
    }
  }

  private ensureKeyboardVisible(): void {
    const keyboard = window.mathVirtualKeyboard;
    if (!keyboard) {
      return;
    }
    try {
      keyboard.container = document.body;
      const keyboardHeight = Math.max(180, Math.min(380, Math.floor(window.innerHeight * 0.52)));
      (keyboard as { boundingRect?: { left: number; top: number; width: number; height: number } }).boundingRect = {
        left: 0,
        top: Math.max(0, window.innerHeight - keyboardHeight),
        width: window.innerWidth,
        height: keyboardHeight
      };
      keyboard.visible = true;
      this.syncKeyboardState();
    } catch {
      // Ignore virtual-keyboard placement failures in older WebViews.
    }
  }

  private syncKeyboardState(): void {
    const keyboard = window.mathVirtualKeyboard;
    document.body.classList.toggle("vk-visible", Boolean(keyboard?.visible));
  }

  private syncLatexOutput(): void {
    this.latexOutput.value = this.getLatex();
    this.latexOutput.dispatchEvent(new Event("latexsnipper-latex-change"));
  }
}
