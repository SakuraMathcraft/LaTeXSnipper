import { ConversionResult } from "../services/bridgeClient";
import { loadEquationSource, saveEquationSource } from "../services/equationSession";

const EQUATION_TAG_PREFIX = "latexsnipper-eq-";
const NUMBER_CONTROL_TAG_PREFIX = "latexsnipper-eqn-";
const NUMBER_CONTROL_ALIAS_PREFIX = "LaTeXSnipperEqNum-";

export type EquationDraft = {
  latex: string;
  display: boolean;
  numbering: "none" | "auto" | "manual";
  manualNumber?: string;
  equationId?: string;
  numberValue?: string;
};

export type SelectedEquation = {
  equationId: string;
  latex: string;
  display: boolean;
  numbering: string;
  numberValue?: string;
};

export async function insertEquationIntoWord(draft: EquationDraft, conversion: ConversionResult): Promise<void> {
  if (!conversion.omml || !looksLikeOmml(conversion.omml)) {
    throw new Error("The bridge did not return editable OMML.");
  }
  const number = await resolveNumber(draft);
  const equationId = await saveEquationSource(draft.latex, draft.equationId, draft.display, draft.numbering, number || draft.manualNumber);
  const ooxml = buildEquationOoxml(conversion.omml, { display: draft.display, equationId, number });

  if (typeof Word !== "undefined" && Word.run) {
    await Word.run(async (context) => {
      const targetRange = await getInsertionTargetRange(context);
      const insertedRange = targetRange.insertOoxml(ooxml, Word.InsertLocation.replace);
      moveSelectionAfterInsertedEquation(insertedRange, draft.display);
      await context.sync();
    });
    return;
  }
  await setSelectedOoxml(ooxml);
}

export async function updateEquationInWord(draft: EquationDraft, conversion: ConversionResult): Promise<void> {
  if (!conversion.omml || !looksLikeOmml(conversion.omml)) {
    throw new Error("The bridge did not return editable OMML.");
  }
  if (!draft.equationId) throw new Error("Equation ID is required for update.");
  const equationId = draft.equationId;
  const omml = conversion.omml;

  const record = loadEquationSource(equationId);
  const wasNumbered = !!(record?.numbering && record.numbering !== "none");

  const number = draft.manualNumber || draft.numberValue || await resolveNumber(draft);
  await saveEquationSource(draft.latex, equationId, draft.display, draft.numbering, number);

  const tag = `${EQUATION_TAG_PREFIX}${equationId}`;

  // Rebuild when numbering structure changes (none <-> numbered).
  const willBeNumbered = !!number;
  if ((willBeNumbered && !wasNumbered) || (!willBeNumbered && wasNumbered)) {
    const newOoxml = buildEquationOoxml(omml, {
      display: draft.display,
      equationId,
      number,
    });
    await setSelectedOoxml(newOoxml);
    await moveSelectionAfterRebuiltEquation(equationId, draft.display);

    if (draft.numbering === "auto" && !draft.numberValue) {
      await renumberWordEquations();
    }
    return;
  }

  if (typeof Word !== "undefined" && Word.run) {
    await Word.run(async (context) => {
      const eqCcs = context.document.contentControls.getByTag(tag);
      eqCcs.load("items");
      await context.sync();
      if (eqCcs.items.length === 0) {
        throw new Error("The equation could not be found in this document.");
      }
      const equationControl = eqCcs.items[0];
      const existingOoxml = equationControl.getOoxml();
      await context.sync();
      const updatedOoxml = replaceContentControlBody(existingOoxml.value, omml);
      equationControl.getRange(Word.RangeLocation.whole).insertOoxml(updatedOoxml, Word.InsertLocation.replace);
      await context.sync();
    });
    if (number) {
      await updateNumberControlViaWordApi(equationId, number);
    }
  } else {
    await setSelectedOoxml(buildEquationOoxml(omml, {
      display: draft.display,
      equationId,
      number,
    }));
  }

  if (draft.numbering === "auto" && !draft.numberValue) {
    await renumberWordEquations();
  }
}

export async function loadSelectedEquationFromWord(): Promise<SelectedEquation> {
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    throw new Error("Select a LaTeXSnipper equation first.");
  }
  const record = loadEquationSource(equationId);
  if (!record || !record.latex) {
    throw new Error("The selected equation does not have saved LaTeX source.");
  }
  return {
    equationId: record.id,
    latex: record.latex,
    display: record.display !== false,
    numbering: record.numbering || "none",
    numberValue: record.numberValue,
  };
}

export async function getSelectedEquationIdFromWord(): Promise<string> {
  const ooxml = await getSelectedOoxml();
  const id = extractEquationId(ooxml);
  if (id) return id;

  // Drag-selection may not expose the tag in OOXML. Inspect only controls
  // contained in that selection; never infer selection from the whole body.
  if (typeof Word !== "undefined" && Word.run) {
    return Word.run(async (context) => {
      const selection = context.document.getSelection();
      const ccs = selection.contentControls;
      ccs.load("items");
      await context.sync();
      for (const cc of ccs.items) {
        cc.load("tag");
      }
      await context.sync();
      for (const cc of ccs.items) {
        if (cc.tag.startsWith(EQUATION_TAG_PREFIX)) {
          return cc.tag.slice(EQUATION_TAG_PREFIX.length);
        }
      }
      return "";
    });
  }

  return "";
}

export async function renumberWordEquations(): Promise<number> {
  if (typeof Word === "undefined" || !Word.run) {
    throw new Error("Renumbering is available in Word only.");
  }
  return Word.run(async (context) => {
    const body = context.document.body.getOoxml();
    await context.sync();
    const eqIds = extractNumberedEquationIds(body.value);
    if (eqIds.length === 0) return 0;

    // Keep equations in document order and filter out manually-numbered ones.
    const ordered: { id: string; pos: number }[] = [];
    for (const id of eqIds) {
      const pos = body.value.indexOf(`${NUMBER_CONTROL_TAG_PREFIX}${id}`);
      if (pos >= 0) ordered.push({ id, pos });
    }
    ordered.sort((a, b) => a.pos - b.pos);
    const autoIds = ordered
      .map((e) => e.id)
      .filter((id) => {
        const rec = loadEquationSource(id);
        return rec?.numbering === "auto";
      });

    // Load content controls for auto-numbered equations only.
    const collections: Word.ContentControlCollection[] = [];
    for (const id of autoIds) {
      const c = context.document.contentControls.getByTag(`${NUMBER_CONTROL_TAG_PREFIX}${id}`);
      c.load("items");
      collections.push(c);
    }
    await context.sync();
    const controls = collections.flatMap((c: Word.ContentControlCollection) => c.items);
    if (controls.length === 0) return 0;

    // Pass 1: fix table-level properties, update numbers, queue row loads
    for (let i = 0; i < controls.length; i++) {
      const control = controls[i];
      normalizeNumberedEquationTable(control);
      control.insertText(`(${i + 1})`, Word.InsertLocation.replace);
      control.parentTable.rows.load("items");
    }
    await context.sync();

    // Pass 2: queue cell loads
    const rowsPerTable: Word.TableRow[][] = [];
    for (const control of controls) {
      const tableRows = control.parentTable.rows.items;
      rowsPerTable.push(tableRows);
      for (const row of tableRows) {
        row.cells.load("items");
      }
    }
    await context.sync();

    // Pass 3: collect cells, set vertical alignment, queue paragraph loads
    const cellAlignments: { cell: Word.TableCell; alignment: Word.Alignment }[] = [];
    for (const rows of rowsPerTable) {
      for (const row of rows) {
        const cells = row.cells.items;
        if (cells.length >= 2) {
          cellAlignments.push({ cell: cells[0], alignment: Word.Alignment.centered });
          cellAlignments.push({ cell: cells[1], alignment: Word.Alignment.right });
        }
      }
    }
    for (const entry of cellAlignments) {
      entry.cell.verticalAlignment = Word.VerticalAlignment.center;
      entry.cell.body.paragraphs.load("items");
    }
    await context.sync();

    // Pass 4: set paragraph alignment
    for (const entry of cellAlignments) {
      for (const para of entry.cell.body.paragraphs.items) {
        para.alignment = entry.alignment;
      }
    }
    await context.sync();

    return controls.length;
  });
}

function looksLikeOmml(value: string): boolean {
  return /<m:oMath(?:Para)?[\s>]/.test(value);
}

async function resolveNumber(draft: EquationDraft): Promise<string | undefined> {
  if (draft.numbering === "manual") {
    const value = (draft.manualNumber || "").trim();
    return value || undefined;
  }
  if (draft.numbering === "auto") {
    return `(${(await countExistingNumberedEquations()) + 1})`;
  }
  return undefined;
}

async function countExistingNumberedEquations(): Promise<number> {
  if (typeof Word === "undefined" || !Word.run) {
    return 0;
  }
  return Word.run(async (context) => {
    const body = context.document.body.getOoxml();
    await context.sync();
    return extractNumberedEquationIds(body.value).length;
  });
}

async function getInsertionTargetRange(context: Word.RequestContext): Promise<Word.Range> {
  const selection = context.document.getSelection();
  selection.paragraphs.load("items");
  await context.sync();
  if (selection.paragraphs.items.length === 0) {
    return selection;
  }
  const paragraph = selection.paragraphs.items[0];
  paragraph.load("parentTableOrNullObject");
  await context.sync();
  return paragraph.parentTableOrNullObject.isNullObject
    ? selection
    : paragraph.parentTableOrNullObject.getRange(Word.RangeLocation.after);
}

function buildEquationOoxml(omml: string, options: { display: boolean; equationId: string; number?: string }): string {
  const body = options.display
    ? buildDisplayBody(omml, options.equationId, options.number)
    : buildInlineBody(omml, options.equationId);
  const documentXml = [
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
    ' xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">',
    "<w:body>",
    body,
    "</w:body>",
    "</w:document>"
  ].join("");
  return wrapFlatOpc(documentXml);
}

function buildInlineBody(omml: string, equationId: string): string {
  return `<w:p>${wrapEquationContentControl(omml, equationId)}</w:p>`;
}

function buildDisplayBody(omml: string, equationId: string, number?: string): string {
  if (!number) {
    return `<w:p><w:pPr><w:jc w:val="center"/></w:pPr>${wrapEquationContentControl(omml, equationId)}</w:p>`;
  }
  const table = [
    '<w:tbl><w:tblPr>',
    '<w:tblW w:w="5000" w:type="pct"/>',
    '<w:jc w:val="center"/>',
    '<w:tblInd w:w="0" w:type="dxa"/>',
    '<w:tblLayout w:type="fixed"/>',
    '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>',
    '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar>',
    "</w:tblPr>",
    '<w:tblGrid><w:gridCol w:w="8500"/><w:gridCol w:w="1500"/></w:tblGrid>',
    "<w:tr>",
    '<w:tc><w:tcPr><w:tcW w:w="4250" w:type="pct"/><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr>',
    wrapEquationContentControl(omml, equationId),
    "</w:p></w:tc>",
    '<w:tc><w:tcPr><w:tcW w:w="750" w:type="pct"/><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:jc w:val="right"/></w:pPr>',
    wrapTextContentControl(
      `${NUMBER_CONTROL_TAG_PREFIX}${equationId}`,
      `${NUMBER_CONTROL_ALIAS_PREFIX}${equationId}`,
      number
    ),
    "</w:p></w:tc>",
    "</w:tr></w:tbl>"
  ].join("");
  return table;
}

function moveSelectionAfterInsertedEquation(insertedRange: Word.Range, display: boolean): void {
  if (!display) {
    insertedRange.select(Word.SelectionMode.end);
    return;
  }
  const nextParagraph = insertedRange.insertParagraph("", Word.InsertLocation.after);
  nextParagraph.select(Word.SelectionMode.start);
}

async function moveSelectionAfterRebuiltEquation(equationId: string, display: boolean): Promise<void> {
  if (typeof Word === "undefined" || !Word.run) {
    return;
  }
  await Word.run(async (context) => {
    const controls = context.document.contentControls.getByTag(`${EQUATION_TAG_PREFIX}${equationId}`);
    controls.load("items");
    await context.sync();
    if (controls.items.length === 0) {
      return;
    }
    const equation = controls.items[0];
    equation.load("parentTableOrNullObject");
    await context.sync();
    const containerRange = equation.parentTableOrNullObject.isNullObject
      ? equation.getRange(Word.RangeLocation.whole)
      : equation.parentTableOrNullObject.getRange(Word.RangeLocation.whole);
    moveSelectionAfterInsertedEquation(containerRange, display);
    await context.sync();
  });
}

function normalizeNumberedEquationTable(numberControl: Word.ContentControl): void {
  const table = numberControl.parentTable;
  table.alignment = Word.Alignment.centered;
  table.verticalAlignment = Word.VerticalAlignment.center;
  table.setCellPadding("Top", 0);
  table.setCellPadding("Bottom", 0);
  table.setCellPadding("Left", 0);
  table.setCellPadding("Right", 0);
  table.autoFitWindow();
  table.autoFitBehavior(Word.AutoFitBehavior.fixedSize);
}

function wrapEquationContentControl(omml: string, equationId: string): string {
  return wrapTaggedBlock(`${EQUATION_TAG_PREFIX}${equationId}`, normalizeOmmlForWord(omml), "LaTeXSnipper Equation");
}

function replaceContentControlBody(controlOoxml: string, omml: string): string {
  const startToken = "<w:sdtContent>";
  const start = controlOoxml.indexOf(startToken);
  const end = controlOoxml.indexOf("</w:sdtContent>", start);
  if (start === -1 || end === -1) {
    throw new Error("The equation content control has an invalid OOXML structure.");
  }
  return [
    controlOoxml.slice(0, start + startToken.length),
    normalizeOmmlForWord(omml),
    controlOoxml.slice(end),
  ].join("");
}

function normalizeOmmlForWord(omml: string): string {
  return omml.replace(/\s+xmlns:mml=(["'])http:\/\/www\.w3\.org\/1998\/Math\/MathML\1/g, "");
}

function wrapTextContentControl(tag: string, alias: string, text: string): string {
  return [
    "<w:sdt>",
    "<w:sdtPr>",
    `<w:alias w:val="${escapeXml(alias)}"/>`,
    `<w:tag w:val="${escapeXml(tag)}"/>`,
    "</w:sdtPr>",
    "<w:sdtContent><w:r><w:t>",
    escapeXml(text),
    "</w:t></w:r></w:sdtContent>",
    "</w:sdt>"
  ].join("");
}

function wrapTaggedBlock(tag: string, content: string, alias = "LaTeXSnipper Equation"): string {
  return [
    "<w:sdt>",
    "<w:sdtPr>",
    `<w:alias w:val="${escapeXml(alias)}"/>`,
    `<w:tag w:val="${escapeXml(tag)}"/>`,
    "</w:sdtPr>",
    "<w:sdtContent>",
    content,
    "</w:sdtContent>",
    "</w:sdt>"
  ].join("");
}

function extractEquationId(ooxml: string): string {
  return (
    extractFirstMatch(ooxml, /latexsnipper-eq-([^"&<\s]+)/) ||
    extractFirstMatch(ooxml, /LaTeXSnipperEqNum-([^"&<\s]+)/) ||
    ""
  );
}

function extractFirstMatch(value: string, pattern: RegExp): string {
  return pattern.exec(value)?.[1] || "";
}

function extractNumberedEquationIds(ooxml: string): string[] {
  return uniqueMatches(ooxml, /latexsnipper-eqn-([^"&<\s]+)/g);
}

async function updateNumberControlViaWordApi(equationId: string, number: string): Promise<void> {
  await Word.run(async (context) => {
    const controls = context.document.contentControls.getByTag(`${NUMBER_CONTROL_TAG_PREFIX}${equationId}`);
    controls.load("items");
    await context.sync();
    if (controls.items.length > 0) {
      controls.items[0].insertText(number, Word.InsertLocation.replace);
      await context.sync();
    }
  });
}

function uniqueMatches(value: string, pattern: RegExp): string[] {
  const seen = new Set<string>();
  const matches: string[] = [];
  for (const match of value.matchAll(pattern)) {
    const item = match[1] || match[0];
    if (!seen.has(item)) {
      seen.add(item);
      matches.push(item);
    }
  }
  return matches;
}

function wrapFlatOpc(documentXml: string): string {
  return [
    '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">',
    '<pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml" pkg:padding="512">',
    "<pkg:xmlData>",
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
    "</Relationships>",
    "</pkg:xmlData>",
    "</pkg:part>",
    '<pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">',
    "<pkg:xmlData>",
    documentXml,
    "</pkg:xmlData>",
    "</pkg:part>",
    "</pkg:package>"
  ].join("");
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function setSelectedOoxml(ooxml: string): Promise<void> {
  return new Promise((resolve, reject) => {
    Office.context.document.setSelectedDataAsync(
      ooxml,
      { coercionType: Office.CoercionType.Ooxml },
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve();
          return;
        }
        reject(new Error(result.error?.message || "Failed to insert OOXML."));
      }
    );
  });
}

function getSelectedOoxml(): Promise<string> {
  return new Promise((resolve, reject) => {
    Office.context.document.getSelectedDataAsync(
      Office.CoercionType.Ooxml,
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve(String(result.value || ""));
          return;
        }
        reject(new Error(result.error?.message || "Failed to read selected OOXML."));
      }
    );
  });
}
