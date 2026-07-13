import { describe, expect, it, vi } from "vitest";

import {
  AgentClient,
  type FetchPort,
} from "../src/backend/agentClient";

describe("AgentClient", () => {
  it("uses the versioned same-origin health endpoint without credentials", async () => {
    const fetchPort: FetchPort = vi.fn(async () =>
      new Response(
        JSON.stringify({
          status: "ok",
          apiVersion: "v1",
          serviceVersion: "0.1.0-dev",
          capabilities: ["screenshot-ocr"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new AgentClient(new URL("https://localhost:3000/v1/"), fetchPort);

    await expect(client.getHealth()).resolves.toMatchObject({ apiVersion: "v1" });
    expect(fetchPort).toHaveBeenCalledOnce();
    const [url, init] = vi.mocked(fetchPort).mock.calls[0] ?? [];
    expect(String(url)).toBe("https://localhost:3000/v1/health");
    expect(init).toMatchObject({ method: "GET", credentials: "omit", cache: "no-store" });
  });

  it("classifies incompatible API versions", async () => {
    const client = new AgentClient(
      new URL("https://localhost:3000/v1/"),
      async () =>
        new Response(
          JSON.stringify({
            status: "ok",
            apiVersion: "v2",
            serviceVersion: "2.0.0",
            capabilities: [],
          }),
          { status: 200 },
        ),
    );

    await expect(client.getHealth()).rejects.toMatchObject({
      code: "incompatible",
    });
  });

  it("does not accept malformed successful responses", async () => {
    const client = new AgentClient(
      new URL("https://localhost:3000/v1/"),
      async () => new Response("{}", { status: 200 }),
    );

    await expect(client.getHealth()).rejects.toMatchObject({
      code: "invalid-response",
    });
  });
});
