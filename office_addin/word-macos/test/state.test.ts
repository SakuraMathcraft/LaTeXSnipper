import { describe, expect, it, vi } from "vitest";

import { createInitialAppState, StateStore } from "../src/state/appState";

describe("StateStore", () => {
  it("emits the initial state and immutable updates", () => {
    const store = new StateStore(createInitialAppState());
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.update((state) => ({
      ...state,
      editor: { ...state.editor, status: "ready", detail: "ready" },
    }));
    unsubscribe();
    store.update((state) => ({ ...state, operation: { ...state.operation, busy: true } }));

    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener.mock.calls[0]?.[0].editor.status).toBe("loading");
    expect(listener.mock.calls[1]?.[0].editor.status).toBe("ready");
  });

  it("does not emit when the updater returns the same object", () => {
    const store = new StateStore(createInitialAppState());
    const listener = vi.fn();
    store.subscribe(listener, false);
    store.update((state) => state);
    expect(listener).not.toHaveBeenCalled();
  });
});
