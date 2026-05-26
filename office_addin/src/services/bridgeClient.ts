export type ConvertTarget = "omml" | "mathml" | "svg" | "png";

export type BridgeHealth = {
  name: string;
  protocol: number;
  auth: string;
  features: Record<string, boolean>;
};

export type BridgeConfig = {
  bridge_url: string;
  token: string;
  features: Record<string, boolean>;
};

export type ConversionResult = {
  latex: string;
  display: boolean;
  warnings: string[];
  omml?: string;
  mathml?: string;
  svg?: string;
  png_base64?: string;
};

export type ScreenshotOcrResult = {
  latex: string;
};

const DEFAULT_REQUEST_TIMEOUT_MS = 7000;
const OCR_REQUEST_TIMEOUT_MS = 305000;

type BridgeEnvelope<T> =
  | { ok: true; result: T }
  | { ok: false; error: { code: string; message: string } };

export class BridgeClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS
  ) {}

  async health(authenticated = true): Promise<BridgeHealth> {
    return this.request<BridgeHealth>("/health", { method: "GET" }, authenticated);
  }

  async config(): Promise<BridgeConfig> {
    return this.request<BridgeConfig>("/config", { method: "GET" }, false);
  }

  async convertLatex(latex: string, targets: ConvertTarget[] = ["omml"]): Promise<ConversionResult> {
    return this.request<ConversionResult>(
      "/convert/latex",
      {
        method: "POST",
        body: JSON.stringify({
          latex,
          display: true,
          targets
        })
      },
      true
    );
  }

  async recognizeScreenshot(): Promise<ScreenshotOcrResult> {
    const health = await this.health();
    if (!health.features.capture_recognize) {
      throw new Error(
        "Connected bridge does not support Screenshot OCR. Enable the Office bridge in LaTeXSnipper."
      );
    }
    return this.request<ScreenshotOcrResult>(
      "/recognize/screenshot",
      {
        method: "POST",
        body: JSON.stringify({ timeout: 300 })
      },
      true,
      OCR_REQUEST_TIMEOUT_MS
    );
  }

  private async request<T>(
    path: string,
    init: RequestInit,
    authenticated: boolean,
    timeoutMs = this.timeoutMs
  ): Promise<T> {
    const headers = new Headers(init.headers || {});
    if (init.body) {
      headers.set("Content-Type", "application/json");
    }
    if (authenticated) {
      if (!this.token.trim()) {
        throw new Error("Bridge token is required.");
      }
      headers.set("Authorization", `Bearer ${this.token.trim()}`);
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetch(`${this.normalizedBaseUrl()}${path}`, {
        ...init,
        headers,
        signal: controller.signal
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("Bridge request timed out.");
      }
      throw new Error(`Bridge is not reachable at ${this.normalizedBaseUrl()}.`);
    } finally {
      window.clearTimeout(timeout);
    }
    const payload = (await response.json()) as BridgeEnvelope<T>;
    if (!response.ok || !payload.ok) {
      const message = payload.ok ? `Bridge request failed: ${response.status}` : payload.error.message;
      throw new Error(message);
    }
    return payload.result;
  }

  private normalizedBaseUrl(): string {
    return this.baseUrl.trim().replace(/\/+$/, "");
  }
}
