export type ConvertTarget = "omml" | "mathml" | "svg" | "png";

export type BridgeHealth = {
  name: string;
  protocol: number;
  auth: string;
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

type BridgeEnvelope<T> =
  | { ok: true; result: T }
  | { ok: false; error: { code: string; message: string } };

export class BridgeClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string
  ) {}

  async health(): Promise<BridgeHealth> {
    return this.request<BridgeHealth>("/health", { method: "GET" }, false);
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

  private async request<T>(path: string, init: RequestInit, authenticated: boolean): Promise<T> {
    const headers = new Headers(init.headers || {});
    headers.set("Content-Type", "application/json");
    if (authenticated) {
      if (!this.token.trim()) {
        throw new Error("Bridge token is required.");
      }
      headers.set("Authorization", `Bearer ${this.token.trim()}`);
    }
    const response = await fetch(`${this.normalizedBaseUrl()}${path}`, {
      ...init,
      headers
    });
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
