declare module "*mathlive.min.mjs" {
  export class MathfieldElement extends HTMLElement {
    static fontsDirectory: string;

    defaultMode: string;
    mathModeSpace: string;
    mathVirtualKeyboardPolicy: string;
    smartFence: boolean;
    smartMode: boolean;
    value: string;

    executeCommand(command: string): boolean;
    getValue(format?: string): string;
    insert(
      value: string,
      options?: {
        format?: string;
        insertionMode?: string;
        selectionMode?: string;
      },
    ): boolean;
    setValue(value: string, options?: { silenceNotifications?: boolean }): void;
  }
}
