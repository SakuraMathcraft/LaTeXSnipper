import test from "node:test";
import assert from "node:assert/strict";

import {
  createFormulaModel,
  isFormulaMode,
  normalizeFormulaMode,
} from "../src/formula/formulaModel.js";

test("normalizeFormulaMode accepts supported modes", () => {
  assert.equal(normalizeFormulaMode("inline"), "inline");
  assert.equal(normalizeFormulaMode("display"), "display");
  assert.equal(normalizeFormulaMode("numbered"), "numbered");
});

test("normalizeFormulaMode falls back to inline", () => {
  assert.equal(normalizeFormulaMode("unknown"), "inline");
});

test("isFormulaMode checks supported modes", () => {
  assert.equal(isFormulaMode("numbered"), true);
  assert.equal(isFormulaMode("ole"), false);
});

test("createFormulaModel stores normalized latex and manual number", () => {
  const model = createFormulaModel({
    latex: "  x^2  ",
    mode: "numbered",
    manualNumber: "3.4",
    now: () => "2026-06-18T00:00:00.000Z",
    idFactory: () => "formula-test-id",
  });

  assert.deepEqual(model, {
    id: "formula-test-id",
    latex: "x^2",
    mode: "numbered",
    manualNumber: "3.4",
    createdAt: "2026-06-18T00:00:00.000Z",
    updatedAt: "2026-06-18T00:00:00.000Z",
  });
});
