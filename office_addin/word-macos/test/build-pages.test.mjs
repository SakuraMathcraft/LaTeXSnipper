import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import {
  PAGES_OUTPUT_DIR,
  PAGES_TASKPANE_URL,
  buildPagesDist,
  createReleaseManifest,
} from "../scripts/build-pages.mjs";

test("createReleaseManifest points SourceLocation to GitHub Pages", () => {
  const manifest = createReleaseManifest();

  assert.match(
    manifest,
    new RegExp(`<SourceLocation DefaultValue="${PAGES_TASKPANE_URL}"\\/>`),
  );
});

test("buildPagesDist writes static task pane files and release manifest", async () => {
  const distDir = await mkdtemp(path.join(os.tmpdir(), "latexsnipper-word-macos-pages-"));

  try {
    await buildPagesDist({ distDir });

    const taskpaneHtml = await readFile(path.join(distDir, "taskpane.html"), "utf8");
    const taskpaneJs = await readFile(path.join(distDir, "taskpane.js"), "utf8");
    const taskpaneCss = await readFile(path.join(distDir, "taskpane.css"), "utf8");
    const mathEditorJs = await readFile(path.join(distDir, "editor", "mathEditor.js"), "utf8");
    const formulaModelJs = await readFile(
      path.join(distDir, "formula", "formulaModel.js"),
      "utf8",
    );
    const latexJs = await readFile(path.join(distDir, "latex.js"), "utf8");
    const wordInsertJs = await readFile(path.join(distDir, "office", "wordInsert.js"), "utf8");
    const shortcutsJs = await readFile(path.join(distDir, "shortcuts.js"), "utf8");
    const manifest = await readFile(
      path.join(distDir, "manifest", "LaTeXSnipperWordAddin.xml"),
      "utf8",
    );

    assert.match(taskpaneHtml, /LaTeXSnipper Word/);
    assert.match(taskpaneHtml, /Insert Inline/);
    assert.match(taskpaneHtml, /Insert Display/);
    assert.match(taskpaneHtml, /Insert Numbered/);
    assert.match(taskpaneJs, /insertFormulaIntoWord/);
    assert.match(taskpaneCss, /pane-shell/);
    assert.match(mathEditorJs, /Math editor unavailable; using LaTeX source/);
    assert.match(formulaModelJs, /createFormulaModel/);
    assert.match(latexJs, /formatInlineFormula/);
    assert.match(wordInsertJs, /formatFormulaForInsertion/);
    assert.match(shortcutsJs, /shouldInsertFormulaShortcut/);
    assert.match(manifest, new RegExp(PAGES_TASKPANE_URL));
  } finally {
    await rm(distDir, { force: true, recursive: true });
  }
});

test("default GitHub Pages output directory is repository docs/word-macos", () => {
  const repositoryRoot = path.resolve(process.cwd(), "../..");
  assert.equal(
    path.relative(repositoryRoot, PAGES_OUTPUT_DIR),
    path.join("docs", "word-macos"),
  );
});
