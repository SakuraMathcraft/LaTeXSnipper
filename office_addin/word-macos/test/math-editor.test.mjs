import test from "node:test";
import assert from "node:assert/strict";

import {
  createMathEditorState,
  getMathEditorUnavailableMessage,
} from "../src/editor/mathEditor.js";

test("createMathEditorState reports fallback when MathLive is unavailable", () => {
  assert.deepEqual(createMathEditorState({ mathLiveAvailable: false }), {
    available: false,
    message: "Math editor unavailable; using LaTeX source",
  });
});

test("createMathEditorState reports availability when MathLive can load", () => {
  assert.deepEqual(createMathEditorState({ mathLiveAvailable: true }), {
    available: true,
    message: "Math editor ready",
  });
});

test("getMathEditorUnavailableMessage uses concise copy", () => {
  assert.equal(getMathEditorUnavailableMessage(), "Math editor unavailable; using LaTeX source");
});
