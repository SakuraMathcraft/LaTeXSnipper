import { copyFile, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const PAGES_TASKPANE_URL =
  "https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");
const repositoryRoot = path.resolve(projectRoot, "../..");

export const PAGES_OUTPUT_DIR = path.join(repositoryRoot, "docs", "word-macos");

const staticFiles = [
  ["src/taskpane.html", "taskpane.html"],
  ["src/taskpane.css", "taskpane.css"],
  ["src/taskpane.js", "taskpane.js"],
  ["src/editor/mathEditor.js", "editor/mathEditor.js"],
  ["src/formula/formulaModel.js", "formula/formulaModel.js"],
  ["src/latex.js", "latex.js"],
  ["src/office/wordInsert.js", "office/wordInsert.js"],
  ["src/shortcuts.js", "shortcuts.js"],
];

export function createReleaseManifest(sourceLocation = PAGES_TASKPANE_URL) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp
  xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:type="TaskPaneApp">
  <Id>6c1dfaf4-a8bf-4b74-9ce8-7e22df34c8c8</Id>
  <Version>0.1.0.0</Version>
  <ProviderName>LaTeXSnipper</ProviderName>
  <DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="LaTeXSnipper Word"/>
  <Description DefaultValue="LaTeXSnipper formula task pane for Word on macOS."/>
  <AppDomains>
    <AppDomain>https://galileo927.github.io</AppDomain>
  </AppDomains>
  <Hosts>
    <Host Name="Document"/>
  </Hosts>
  <DefaultSettings>
    <SourceLocation DefaultValue="${sourceLocation}"/>
  </DefaultSettings>
  <Permissions>ReadWriteDocument</Permissions>
</OfficeApp>
`;
}

export async function buildPagesDist({
  rootDir = projectRoot,
  distDir = PAGES_OUTPUT_DIR,
} = {}) {
  await rm(distDir, { force: true, recursive: true });
  await mkdir(path.join(distDir, "manifest"), { recursive: true });

  for (const [source, destination] of staticFiles) {
    const outputPath = path.join(distDir, destination);
    await mkdir(path.dirname(outputPath), { recursive: true });
    await copyFile(path.join(rootDir, source), outputPath);
  }

  await writeFile(
    path.join(distDir, "manifest", "LaTeXSnipperWordAddin.xml"),
    createReleaseManifest(),
    "utf8",
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await buildPagesDist();
  console.log("Built GitHub Pages preview files in docs/word-macos/");
}
