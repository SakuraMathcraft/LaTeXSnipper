import { access, readFile, readdir } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = resolve(projectRoot, ".dev/taskpane");
const requiredFiles = [
  "taskpane.html",
  "support.html",
  "assets/icon-16.png",
  "assets/icon-32.png",
  "assets/icon-64.png",
  "assets/icon-80.png",
  "assets/mathjax/es5/tex-mml-svg.js",
  "assets/mathjax/es5/output/svg/fonts/tex.js",
  "assets/mathjax/es5/input/tex/extensions/bbox.js",
  "assets/licenses/mathlive.LICENSE.txt",
  "assets/licenses/mathjax.LICENSE.txt",
];
const allowedRemoteScripts = new Set([
  "https://appsforoffice.microsoft.com/lib/1/hosted/office.js",
]);
const remoteComputeEngineHint =
  "https://esm.run/@cortex-js/" + "compute" + "-engine";

async function filesBelow(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesBelow(path) : [path];
  }));
  return nested.flat();
}

for (const path of requiredFiles) {
  await access(resolve(outputRoot, path));
}

const outputFiles = await filesBelow(outputRoot);
const relativePaths = outputFiles.map((path) => relative(outputRoot, path));
if (relativePaths.some((path) => /compute[-_]?engine/i.test(path))) {
  throw new Error("Development bundle must not contain Compute Engine files.");
}

for (const path of outputFiles.filter((candidate) => candidate.endsWith(".js"))) {
  const source = await readFile(path, "utf8");
  if (source.includes(remoteComputeEngineHint)) {
    throw new Error(
      "Remote Compute Engine hint leaked into " + relative(outputRoot, path) + ".",
    );
  }
  if (/\bimport\s*(?:\(\s*)?["']https?:\/\//u.test(source)) {
    throw new Error(
      "Remote JavaScript import found in " + relative(outputRoot, path) + ".",
    );
  }
}

for (const path of outputFiles.filter((candidate) => candidate.endsWith(".html"))) {
  const markup = await readFile(path, "utf8");
  const document = new JSDOM(markup).window.document;
  const remoteScripts = [...document.querySelectorAll("script[src]")]
    .map((script) => script.getAttribute("src") ?? "")
    .filter((source) => /^https?:\/\//u.test(source));
  for (const source of remoteScripts) {
    if (!allowedRemoteScripts.has(source)) {
      throw new Error(
        "Unapproved remote script " + source + " found in " +
          relative(outputRoot, path) + ".",
      );
    }
  }
}

console.log(
  "Development bundle policy passed (" + String(outputFiles.length) + " files).",
);
