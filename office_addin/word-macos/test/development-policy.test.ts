import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function text(path: string): Promise<string> {
  return readFile(resolve(projectRoot, path), "utf8");
}

describe("private development policy", () => {
  it("keeps every manifest resource on trusted localhost HTTPS", async () => {
    const manifest = await text("manifest/word-dev.xml");
    const attributeUrls = [...manifest.matchAll(
      /\bDefaultValue\s*=\s*(["'])(https?:\/\/[^"']+)\1/giu,
    )].map((match) => match[2] ?? "");
    const textUrls = [...manifest.matchAll(
      /<AppDomain\b[^>]*>\s*(https?:\/\/[^<\s]+)\s*<\/AppDomain>/giu,
    )].map((match) => match[1] ?? "");
    const urlValues = new Set([...attributeUrls, ...textUrls]);

    expect(urlValues.size).toBeGreaterThan(0);
    expect([...urlValues].every((url) => url.startsWith("https://localhost:3000"))).toBe(true);
    expect(manifest).not.toContain("github.io");
    expect(manifest).not.toContain("<FunctionFile");
    expect(manifest).not.toContain("<TaskpaneId>");
    expect(manifest).toContain('<Set Name="WordApi" MinVersion="1.3"/>');
    const version = manifest.match(/<Version>(\d+)\.(\d+)\.(\d+)\.(\d+)<\/Version>/);
    expect(version).not.toBeNull();
    expect(Number(version?.[1])).toBeGreaterThanOrEqual(1);
  });

  it("allows only the official Office.js runtime as a remote taskpane script", async () => {
    const taskpane = await text("src/taskpane.html");
    const remoteScripts = [...taskpane.matchAll(
      /<script\b[^>]*\bsrc\s*=\s*(["'])(https?:\/\/[^"']+)\1/giu,
    )].map((match) => match[2] ?? "");

    expect(remoteScripts).toEqual([
      "https://appsforoffice.microsoft.com/lib/1/hosted/office.js",
    ]);
    expect(taskpane).not.toMatch(/jsdelivr|cdnjs|unpkg/i);
    expect(taskpane).toContain("Content-Security-Policy");
  });

  it("has no release or publishing command", async () => {
    const packageJson = JSON.parse(await text("package.json")) as {
      scripts: Record<string, string>;
    };
    expect(Object.keys(packageJson.scripts)).not.toContain("build");
    expect(Object.keys(packageJson.scripts).some((name) => /release|publish|deploy/i.test(name)))
      .toBe(false);
    expect(packageJson.scripts["build:dev"]).toContain("--mode development");
    expect(packageJson.scripts["build:dev"]).toContain("check-dev-bundle.mjs");
  });

  it("keeps device-local artifacts and credentials outside Git", async () => {
    const ignore = await text(".gitignore");
    expect(ignore).toContain(".dev/");
    expect(ignore).toContain(".env.local");
    expect(ignore).toContain("*.crt");
    expect(ignore).toContain("*.key");
    expect(ignore).toContain("*.pem");
  });

  it("does not include Compute Engine or the entire shared asset tree", async () => {
    const config = await text("vite.config.ts");
    const renderer = await text("src/rendering/mathJaxRenderer.ts");
    const bundlePolicy = await text("scripts/check-dev-bundle.mjs");
    expect(config).not.toMatch(/sourcePath:.*compute[-_]?engine/i);
    expect(bundlePolicy).toContain("must not contain Compute Engine files");
    expect(config).not.toContain("publicDir: mathLiveRoot");
    expect(config).toContain("assets/mathlive/fonts");
    expect(config).toContain("tex-mml-svg.js");
    expect(config).toContain("input/tex/extensions/bbox.js");
    expect(renderer).toContain('load: ["[tex]/bbox"]');
    expect(renderer).toContain('packages: ["base", "ams", "newcommand", "bbox"]');
    expect(renderer).not.toContain('"[+]"');
    expect(renderer).not.toContain('"autoload"');
  });
});
