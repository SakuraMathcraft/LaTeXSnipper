import { afterEach, describe, expect, it, vi } from "vitest";

import { createDebouncedTask } from "../src/utils/debounce";

afterEach(() => {
  vi.useRealTimers();
});

describe("createDebouncedTask", () => {
  it("coalesces repeated preview updates", () => {
    vi.useFakeTimers();
    const task = vi.fn();
    const debounced = createDebouncedTask(task, 180);

    debounced.schedule();
    debounced.schedule();
    vi.advanceTimersByTime(179);
    expect(task).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(task).toHaveBeenCalledOnce();
  });

  it("can flush or cancel pending work", () => {
    vi.useFakeTimers();
    const task = vi.fn();
    const debounced = createDebouncedTask(task, 180);
    debounced.schedule();
    debounced.flush();
    expect(task).toHaveBeenCalledOnce();

    debounced.schedule();
    debounced.cancel();
    vi.runAllTimers();
    expect(task).toHaveBeenCalledOnce();
  });
});
