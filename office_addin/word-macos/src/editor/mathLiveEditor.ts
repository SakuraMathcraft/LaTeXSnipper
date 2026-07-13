export interface MathLiveEditorController {
  getLatex(): string;
  setLatex(latex: string): void;
  focus(): void;
  destroy(): void;
}

export interface MathLiveEditorOptions {
  readonly initialLatex?: string;
  readonly onChange: (latex: string, event: Event) => void;
}

export async function mountMathLiveEditor(
  host: HTMLElement,
  options: MathLiveEditorOptions,
): Promise<MathLiveEditorController> {
  const { MathfieldElement } = await import(
    "../../../../src/assets/mathlive/vendor/mathlive.min.mjs"
  );

  MathfieldElement.fontsDirectory = new URL(
    "assets/mathlive/fonts/",
    document.baseURI,
  ).href;

  const field = new MathfieldElement();
  field.defaultMode = "math";
  field.smartFence = true;
  field.smartMode = false;
  field.mathModeSpace = "\\,";
  field.mathVirtualKeyboardPolicy = "manual";
  field.setAttribute("aria-label", "公式可视化编辑器");
  field.setAttribute("role", "textbox");
  field.setAttribute("spellcheck", "false");
  field.setValue(options.initialLatex ?? "", { silenceNotifications: true });

  const notify = (event: Event) => {
    if ("isComposing" in event && event.isComposing === true) {
      return;
    }
    options.onChange(field.getValue("latex-expanded").trim(), event);
  };

  field.addEventListener("input", notify);
  field.addEventListener("compositionend", notify);
  host.replaceChildren(field);

  return {
    getLatex: () => field.getValue("latex-expanded").trim(),
    setLatex(latex) {
      if (field.getValue("latex-expanded").trim() === latex.trim()) {
        return;
      }
      field.setValue(latex, { silenceNotifications: true });
    },
    focus: () => field.focus(),
    destroy() {
      field.removeEventListener("input", notify);
      field.removeEventListener("compositionend", notify);
      field.remove();
    },
  };
}
