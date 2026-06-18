const UNAVAILABLE_MESSAGE = "Math editor unavailable; using LaTeX source";

export function getMathEditorUnavailableMessage() {
  return UNAVAILABLE_MESSAGE;
}

export function canUseMathLive(globalScope = globalThis) {
  return Boolean(globalScope?.customElements?.get?.("math-field"));
}

export function createMathEditorState({ mathLiveAvailable = false } = {}) {
  if (mathLiveAvailable) {
    return {
      available: true,
      message: "Math editor ready",
    };
  }

  return {
    available: false,
    message: UNAVAILABLE_MESSAGE,
  };
}
