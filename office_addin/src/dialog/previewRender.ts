import type { BridgeClient, ConversionResult } from "../services/bridgeClient";

type PreviewState =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "svg"; svg: string; omml: string }
  | { kind: "error"; message: string };

export class PreviewRender {
  private state: PreviewState = { kind: "empty" };
  private pendingLatex: string | null = null;
  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly debounceMs: number;

  constructor(
    private readonly container: HTMLElement,
    debounceMs = 300
  ) {
    this.debounceMs = debounceMs;
    this.render();
  }

  schedule(latex: string, client: BridgeClient): void {
    this.pendingLatex = latex;
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.debounceTimer = null;
      void this.convertAndRender(client);
    }, this.debounceMs);
  }

  getCachedOmml(): string {
    return this.state.kind === "svg" ? this.state.omml : "";
  }

  dispose(): void {
    if (this.debounceTimer !== null) {
      clearTimeout(this.debounceTimer);
    }
    this.container.replaceChildren();
  }

  private async convertAndRender(client: BridgeClient): Promise<void> {
    const latex = this.pendingLatex;
    if (!latex) {
      return;
    }
    this.pendingLatex = null;
    this.setState({ kind: "loading" });
    try {
      const result: ConversionResult = await client.convertLatex(latex, ["svg", "omml"]);
      if (!result.svg) {
        this.setState({ kind: "error", message: "Bridge did not return SVG output." });
        return;
      }
      this.setState({ kind: "svg", svg: result.svg, omml: result.omml || "" });
    } catch (error) {
      this.setState({
        kind: "error",
        message: error instanceof Error ? error.message : String(error)
      });
    }
  }

  private setState(state: PreviewState): void {
    if (state.kind === "svg" && this.state.kind === "svg") {
      this.state = state;
      this.renderSvg(state.svg);
      return;
    }
    this.state = state;
    this.render();
  }

  private render(): void {
    this.container.replaceChildren();
    switch (this.state.kind) {
      case "empty": {
        const hint = document.createElement("span");
        hint.className = "preview-hint";
        hint.textContent = "SVG Preview";
        hint.style.cssText = "color:var(--office-secondary, #aaa);font-size:14px;";
        this.container.appendChild(hint);
        break;
      }
      case "loading": {
        const indicator = document.createElement("span");
        indicator.className = "preview-loading";
        indicator.textContent = "Rendering...";
        indicator.style.cssText = "color:var(--office-secondary, #888);font-size:13px;";
        this.container.appendChild(indicator);
        break;
      }
      case "svg": {
        this.renderSvg(this.state.svg);
        break;
      }
      case "error": {
        const error = document.createElement("span");
        error.className = "preview-error";
        error.textContent = this.state.message;
        this.container.appendChild(error);
        break;
      }
    }
  }

  private renderSvg(svgString: string): void {
    const wrapper = document.createElement("div");
    wrapper.style.cssText = "width:100%;height:100%;display:flex;align-items:center;justify-content:center;";
    wrapper.innerHTML = svgString;
    const svg = wrapper.querySelector("svg");
    if (svg) {
      svg.style.maxWidth = "100%";
      svg.style.maxHeight = "100%";
      svg.style.height = "auto";
    }
    this.container.appendChild(wrapper);
  }
}
