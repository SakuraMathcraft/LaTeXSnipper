import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const networkPatterns = /\b(fetch|XMLHttpRequest|WebSocket|EventSource)\b/;

test("task pane source does not make OCR Bridge network requests", async () => {
  const taskpaneSource = await readFile(path.join(process.cwd(), "src", "taskpane.js"), "utf8");
  assert.equal(networkPatterns.test(taskpaneSource), false);
});
