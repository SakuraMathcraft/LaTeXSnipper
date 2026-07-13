export interface DebouncedTask {
  schedule(): void;
  flush(): void;
  cancel(): void;
}

export function createDebouncedTask(task: () => void, delayMilliseconds: number): DebouncedTask {
  let timer: ReturnType<typeof setTimeout> | undefined;

  const cancel = () => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
  };

  const flush = () => {
    cancel();
    task();
  };

  return {
    schedule() {
      cancel();
      timer = setTimeout(flush, Math.max(0, delayMilliseconds));
    },
    flush,
    cancel,
  };
}
