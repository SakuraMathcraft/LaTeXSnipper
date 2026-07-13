export interface WordDocumentPort {
  insertOoxmlAtSelection(ooxml: string): Promise<void>;
}

export interface WordJsBindings {
  readonly replace: Word.InsertLocation | "Replace";
  run(batch: (context: Word.RequestContext) => Promise<void>): Promise<void>;
}

export class WordDocumentOperationError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "WordDocumentOperationError";
  }
}

function defaultBindings(): WordJsBindings {
  if (typeof Word === "undefined") {
    throw new WordDocumentOperationError("Word API 尚未初始化。");
  }
  return {
    replace: Word.InsertLocation.replace,
    run: (batch) => Word.run(batch),
  };
}

export function createOfficeJsWordDocumentPort(
  bindings: WordJsBindings = defaultBindings(),
): WordDocumentPort {
  return {
    async insertOoxmlAtSelection(ooxml) {
      if (!ooxml.trim()) {
        throw new TypeError("OOXML must not be empty.");
      }

      try {
        await bindings.run(async (context) => {
          const selection = context.document.getSelection();
          selection.insertOoxml(ooxml, bindings.replace);
          await context.sync();
        });
      } catch (error) {
        throw new WordDocumentOperationError("Word 无法写入原生公式。", {
          cause: error,
        });
      }
    },
  };
}
