import { describe, expect, it, vi } from "vitest";

import {
  createOfficeJsWordDocumentPort,
  WordDocumentOperationError,
  type WordJsBindings,
} from "../src/office/wordDocument";

describe("WordDocumentPort", () => {
  it("keeps the Word.run proxy sequence behind a narrow adapter", async () => {
    const calls: string[] = [];
    const insertOoxml = vi.fn(() => calls.push("insert"));
    const sync = vi.fn(async () => {
      calls.push("sync");
    });
    const fakeContext = {
      document: {
        getSelection() {
          calls.push("selection");
          return { insertOoxml };
        },
      },
      sync,
    };
    const bindings: WordJsBindings = {
      replace: "Replace",
      async run(batch) {
        calls.push("run");
        await batch(fakeContext as unknown as Word.RequestContext);
      },
    };

    await createOfficeJsWordDocumentPort(bindings).insertOoxmlAtSelection(
      "<pkg:package>known OMML fixture</pkg:package>",
    );

    expect(calls).toEqual(["run", "selection", "insert", "sync"]);
    expect(insertOoxml).toHaveBeenCalledWith(
      "<pkg:package>known OMML fixture</pkg:package>",
      "Replace",
    );
  });

  it("rejects empty OOXML before opening a Word batch", async () => {
    const run = vi.fn();
    const port = createOfficeJsWordDocumentPort({ replace: "Replace", run });
    await expect(port.insertOoxmlAtSelection("  ")).rejects.toThrow(TypeError);
    expect(run).not.toHaveBeenCalled();
  });

  it("maps host failures without copying OOXML into the message", async () => {
    const secretOoxml = "<pkg:package>document-content</pkg:package>";
    const port = createOfficeJsWordDocumentPort({
      replace: "Replace",
      run: async () => {
        throw new Error("host failure");
      },
    });

    const error = await port.insertOoxmlAtSelection(secretOoxml).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(WordDocumentOperationError);
    expect(String(error)).not.toContain(secretOoxml);
  });
});
