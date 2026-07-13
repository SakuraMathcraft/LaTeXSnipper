export type DetectedOfficeHost = "word" | "other" | "none";

export interface OfficeHostInfo {
  readonly host: DetectedOfficeHost;
  readonly platform: string | null;
  readonly version: string | null;
  readonly wordApi13: boolean;
}

export interface OfficeHostPort {
  ready(timeoutMilliseconds?: number): Promise<OfficeHostInfo>;
  supports(setName: string, minimumVersion: string): boolean;
}

export class OfficeInitializationTimeoutError extends Error {
  constructor() {
    super("Office.js 初始化超时。");
    this.name = "OfficeInitializationTimeoutError";
  }
}

export class OfficeJsUnavailableError extends Error {
  constructor() {
    super("Office.js 未加载，无法判断当前 Office 宿主。");
    this.name = "OfficeJsUnavailableError";
  }
}

function timeoutAfter(milliseconds: number): Promise<never> {
  return new Promise((_, reject) => {
    setTimeout(() => reject(new OfficeInitializationTimeoutError()), milliseconds);
  });
}

export function createOfficeJsHostPort(): OfficeHostPort {
  return {
    async ready(timeoutMilliseconds = 8_000) {
      if (typeof Office === "undefined") {
        throw new OfficeJsUnavailableError();
      }

      const info = await Promise.race([
        Office.onReady(),
        timeoutAfter(Math.max(1, timeoutMilliseconds)),
      ]);
      const host: DetectedOfficeHost =
        info?.host == null
          ? "none"
          : info.host === Office.HostType.Word
            ? "word"
            : "other";
      const diagnostics = Office.context.diagnostics as
        | { version?: string | undefined }
        | undefined;

      return {
        host,
        platform: info?.platform == null ? null : String(info.platform),
        version: diagnostics?.version ?? null,
        wordApi13:
          host === "word" &&
          Office.context.requirements.isSetSupported("WordApi", "1.3"),
      };
    },

    supports(setName, minimumVersion) {
      if (typeof Office === "undefined") {
        return false;
      }
      return Office.context.requirements.isSetSupported(setName, minimumVersion);
    },
  };
}
