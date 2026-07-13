import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createOfficeJsHostPort,
  OfficeInitializationTimeoutError,
  OfficeJsUnavailableError,
} from "../src/office/officeHost";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeOffice(host: string | null, supported: boolean) {
  return {
    HostType: { Word: "Word" },
    onReady: vi.fn(async () => ({ host, platform: "Mac" })),
    context: {
      diagnostics: { version: "16.99" },
      requirements: {
        isSetSupported: vi.fn(() => supported),
      },
    },
  };
}

describe("OfficeHostPort", () => {
  it("keeps a missing Office.js runtime distinct from a normal browser", async () => {
    vi.stubGlobal("Office", undefined);
    await expect(createOfficeJsHostPort().ready()).rejects.toBeInstanceOf(
      OfficeJsUnavailableError,
    );

    vi.stubGlobal("Office", fakeOffice(null, false));
    await expect(createOfficeJsHostPort().ready()).resolves.toEqual({
      host: "none",
      platform: "Mac",
      version: "16.99",
      wordApi13: false,
    });
  });

  it("reports an Office.js readiness timeout instead of browser mode", async () => {
    vi.stubGlobal("Office", {
      ...fakeOffice("Word", true),
      onReady: vi.fn(() => new Promise<never>(() => undefined)),
    });

    await expect(createOfficeJsHostPort().ready(5)).rejects.toBeInstanceOf(
      OfficeInitializationTimeoutError,
    );
  });

  it("reports Word ready only when WordApi 1.3 is supported", async () => {
    vi.stubGlobal("Office", fakeOffice("Word", true));
    await expect(createOfficeJsHostPort().ready()).resolves.toEqual({
      host: "word",
      platform: "Mac",
      version: "16.99",
      wordApi13: true,
    });
  });

  it("keeps unsupported Word distinct from other hosts", async () => {
    vi.stubGlobal("Office", fakeOffice("Word", false));
    await expect(createOfficeJsHostPort().ready()).resolves.toMatchObject({
      host: "word",
      wordApi13: false,
    });

    vi.stubGlobal("Office", fakeOffice("PowerPoint", true));
    await expect(createOfficeJsHostPort().ready()).resolves.toMatchObject({
      host: "other",
      wordApi13: false,
    });
  });
});
