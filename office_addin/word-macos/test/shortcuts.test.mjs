import test from "node:test";
import assert from "node:assert/strict";

import {
  shouldClearInputShortcut,
  shouldDismissShortcut,
  shouldInsertFormulaShortcut,
} from "../src/shortcuts.js";

test("shouldInsertFormulaShortcut detects Command Enter", () => {
  assert.equal(
    shouldInsertFormulaShortcut({ key: "Enter", metaKey: true, ctrlKey: false }),
    true,
  );
});

test("shouldInsertFormulaShortcut ignores plain Enter", () => {
  assert.equal(
    shouldInsertFormulaShortcut({ key: "Enter", metaKey: false, ctrlKey: false }),
    false,
  );
});

test("shouldClearInputShortcut detects Command K case-insensitively", () => {
  assert.equal(
    shouldClearInputShortcut({ key: "K", metaKey: true, ctrlKey: false }),
    true,
  );
});

test("shouldClearInputShortcut ignores Control K", () => {
  assert.equal(
    shouldClearInputShortcut({ key: "k", metaKey: false, ctrlKey: true }),
    false,
  );
});

test("shouldDismissShortcut detects Escape", () => {
  assert.equal(shouldDismissShortcut({ key: "Escape" }), true);
});
