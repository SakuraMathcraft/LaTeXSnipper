export type AgentErrorCode =
  | "offline"
  | "timeout"
  | "http-error"
  | "invalid-response"
  | "incompatible";

export interface AgentHealth {
  readonly status: "ok";
  readonly apiVersion: "v1";
  readonly serviceVersion: string;
  readonly capabilities: readonly string[];
}

export type FetchPort = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export class AgentClientError extends Error {
  constructor(
    readonly code: AgentErrorCode,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "AgentClientError";
  }
}

function isAgentHealth(value: unknown): value is AgentHealth {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    candidate.status === "ok" &&
    candidate.apiVersion === "v1" &&
    typeof candidate.serviceVersion === "string" &&
    Array.isArray(candidate.capabilities) &&
    candidate.capabilities.every((item) => typeof item === "string")
  );
}

export class AgentClient {
  readonly #baseUrl: URL;
  readonly #fetch: FetchPort;

  constructor(
    baseUrl: URL,
    fetchPort: FetchPort = (input, init) => globalThis.fetch(input, init),
  ) {
    this.#baseUrl = new URL(baseUrl.href.endsWith("/") ? baseUrl.href : `${baseUrl.href}/`);
    this.#fetch = fetchPort;
  }

  async getHealth(timeoutMilliseconds = 2_500): Promise<AgentHealth> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, Math.max(1, timeoutMilliseconds));

    try {
      const response = await this.#fetch(new URL("health", this.#baseUrl), {
        method: "GET",
        cache: "no-store",
        credentials: "omit",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new AgentClientError(
          response.status === 404 ? "offline" : "http-error",
          `后台服务返回 HTTP ${response.status}。`,
        );
      }

      let payload: unknown;
      try {
        payload = await response.json();
      } catch (error) {
        throw new AgentClientError("invalid-response", "后台服务返回了无效 JSON。", {
          cause: error,
        });
      }

      if (
        typeof payload === "object" &&
        payload !== null &&
        "apiVersion" in payload &&
        (payload as { apiVersion?: unknown }).apiVersion !== "v1"
      ) {
        throw new AgentClientError("incompatible", "后台服务 API 版本不兼容。");
      }
      if (!isAgentHealth(payload)) {
        throw new AgentClientError("invalid-response", "后台服务健康检查结构无效。");
      }
      return payload;
    } catch (error) {
      if (error instanceof AgentClientError) {
        throw error;
      }
      if (timedOut) {
        throw new AgentClientError("timeout", "连接后台服务超时。", { cause: error });
      }
      throw new AgentClientError("offline", "未连接到本机 LaTeXSnipper 服务。", {
        cause: error,
      });
    } finally {
      clearTimeout(timer);
    }
  }
}

export function createSameOriginAgentClient(location: Location = window.location): AgentClient {
  return new AgentClient(new URL("/v1/", location.origin));
}
