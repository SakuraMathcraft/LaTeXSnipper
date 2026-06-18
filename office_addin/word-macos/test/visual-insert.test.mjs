import test from "node:test";
import assert from "node:assert/strict";

import { insertFormula } from "../src/office/wordInsert.js";

function createOfficeApi() {
  return {
    AsyncResultStatus: {
      Failed: "failed",
      Succeeded: "succeeded",
    },
    CoercionType: {
      Html: "html",
      Text: "text",
    },
  };
}

test("insertFormula inserts visual formula as HTML image when available", async () => {
  const calls = [];
  const documentApi = {
    setSelectedDataAsync: (data, options, callback) => {
      calls.push({ data, options });
      callback({ status: "succeeded" });
    },
  };

  const result = await insertFormula({
    documentApi,
    latex: "x^2",
    mode: "inline",
    officeApi: createOfficeApi(),
    renderSvg: async () => "<svg></svg>",
    visual: true,
  });

  assert.equal(result.insertedAs, "visual");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.coercionType, "html");
  assert.match(calls[0].data, /<img /);
});

test("insertFormula falls back to text when visual insertion fails", async () => {
  const calls = [];
  const documentApi = {
    setSelectedDataAsync: (data, options, callback) => {
      calls.push({ data, options });
      if (calls.length === 1) {
        callback({ status: "failed", error: { message: "HTML blocked" } });
        return;
      }
      callback({ status: "succeeded" });
    },
  };

  const result = await insertFormula({
    documentApi,
    latex: "x^2",
    mode: "display",
    officeApi: createOfficeApi(),
    renderSvg: async () => "<svg></svg>",
    visual: true,
  });

  assert.equal(result.insertedAs, "text-fallback");
  assert.match(result.visualError.message, /HTML blocked/);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].options.coercionType, "html");
  assert.equal(calls[1].options.coercionType, "text");
  assert.equal(calls[1].data, "\n\\[ x^2 \\]\n");
});
