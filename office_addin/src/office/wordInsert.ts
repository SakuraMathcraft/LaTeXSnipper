import { ConversionResult } from "../services/bridgeClient";
import { deleteEquationSource, loadEquationSource, saveEquationSource } from "../services/equationSession";

const EQUATION_TAG_PREFIX = "latexsnipper-eq-";
const NUMBER_CONTROL_TAG_PREFIX = "latexsnipper-eqn-";
const NUMBER_CONTROL_ALIAS_PREFIX = "LaTeXSnipperEqNum-";
const INSERT_IN_EQUATION_ERROR = "Place the cursor outside the LaTeXSnipper equation before inserting another formula.";
const INSERT_IN_NUMBERED_EQUATION_ERROR = "Place the cursor outside the numbered LaTeXSnipper equation before inserting another formula.";
const NUMBERED_LAYOUT_TRANSITION_ERROR = "This numbered equation shares a table with another formula. Delete or separate it before changing its numbering mode.";

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
  const omml = conversion.omml;
  const number = await resolveNumber(draft);
  if (typeof Word === "undefined" || typeof Word.run !== "function") {
    throw new Error("Word API 1.3 is required for editable equations.");
  }
  await Word.run(async (context) => {
    const targetRange = await getValidInsertionTargetRange(context);
    const equationId = await saveEquationSource(
      draft.latex,
      draft.equationId,
      draft.display,
      draft.numbering,
      number || draft.manualNumber
    );
    const ooxml = buildEquationOoxml(omml, { display: draft.display, equationId, number });
    const insertedRange = targetRange.insertOoxml(ooxml, Word.InsertLocation.replace);
    moveSelectionAfterInsertedEquation(insertedRange, draft.display);
    await context.sync();
  });
}

export async function updateEquationInWord(draft: EquationDraft, conversion: ConversionResult): Promise<void> {
  if (!conversion.omml || !looksLikeOmml(conversion.omml)) {
    throw new Error("The bridge did not return editable OMML.");
  }
  if (!draft.equationId) throw new Error("Equation ID is required for update.");
  const equationId = draft.equationId;
  const omml = conversion.omml;
  const previousRecord = loadEquationSource(equationId);

  const number = draft.manualNumber || draft.numberValue || await resolveNumber(draft);
  const newOoxml = buildEquationOoxml(omml, {
    display: draft.display,
    equationId,
    number,
  });

  if (typeof Word === "undefined" || typeof Word.run !== "function") {
    throw new Error("Word API 1.3 is required for editable equations.");
  }
  await replaceEquationContainer(equationId, newOoxml, omml, number);
  await saveEquationSource(draft.latex, equationId, draft.display, draft.numbering, number);

  const removedFromAutomaticSequence = previousRecord?.numbering === "auto" && draft.numbering !== "auto";
  if ((draft.numbering === "auto" && !draft.numberValue) || removedFromAutomaticSequence) {
    await renumberWordEquations();
  }
}

export async function deleteSelectedEquationFromWord(): Promise<void> {
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    throw new Error("Select a LaTeXSnipper equation to delete.");
  }
  if (typeof Word === "undefined" || !Word.run) {
    throw new Error("Deleting equations is available in Word only.");
  }
  const record = loadEquationSource(equationId);
  await Word.run(async (context) => {
    const controls = context.document.contentControls.getByTag(`${EQUATION_TAG_PREFIX}${equationId}`);
    controls.load("items");
    await context.sync();
    if (controls.items.length === 0) {
      throw new Error("The selected equation could not be found in this document.");
    }
    const equationControl = controls.items[0];
    equationControl.load("parentTableOrNullObject");
    await context.sync();
    if (equationControl.parentTableOrNullObject.isNullObject) {
      equationControl.delete(false);
    } else {
      const table = equationControl.parentTableOrNullObject;
      const layout = await inspectNumberedLayoutTable(context, table, equationId);
      if (!layout.isNumberedLayout) {
        equationControl.delete(false);
      } else if (layout.equationIds.length === 1) {
        table.delete();
      } else {
        equationControl.parentTableCell.parentRow.delete();
      }
    }
    await context.sync();
  });
  await deleteEquationSource(equationId);
  if (record?.numbering === "auto") {
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
  if (typeof Word === "undefined" || typeof Word.run !== "function") {
    throw new Error("Word API 1.3 is required for equation selection.");
  }
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    const parent = selection.parentContentControlOrNullObject;
    const ccs = selection.contentControls;
    parent.load("tag");
    ccs.load("items");
    await context.sync();
    if (!parent.isNullObject) {
      const parentId = equationIdFromTag(parent.tag);
      if (parentId) {
        return parentId;
      }
    }
    for (const cc of ccs.items) {
      cc.load("tag");
    }
    await context.sync();
    for (const cc of ccs.items) {
      const id = equationIdFromTag(cc.tag);
      if (id) {
        return id;
      }
    }
    return "";
  });
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

    const collections: Word.ContentControlCollection[] = [];
    for (const id of autoIds) {
      const c = context.document.contentControls.getByTag(`${NUMBER_CONTROL_TAG_PREFIX}${id}`);
      c.load("items");
      collections.push(c);
    }
    await context.sync();
    const controls = collections.flatMap((c: Word.ContentControlCollection) => c.items);
    if (controls.length === 0) return 0;

    for (let i = 0; i < controls.length; i++) {
      const control = controls[i];
      normalizeNumberedEquationTable(control);
      control.insertText(`(${i + 1})`, Word.InsertLocation.replace);
      control.parentTable.rows.load("items");
    }
    await context.sync();

    const rowsPerTable: Word.TableRow[][] = [];
    for (const control of controls) {
      const tableRows = control.parentTable.rows.items;
      rowsPerTable.push(tableRows);
      for (const row of tableRows) {
        row.cells.load("items");
      }
    }
    await context.sync();

    const cellAlignments: { cell: Word.TableCell; alignment: Word.Alignment }[] = [];
    for (const rows of rowsPerTable) {
      for (const row of rows) {
        const cells = row.cells.items;
        if (cells.length >= 2) {
          const equationCellIndex = cells.length >= 3 ? 1 : 0;
          cellAlignments.push({ cell: cells[equationCellIndex], alignment: Word.Alignment.centered });
          cellAlignments.push({ cell: cells[cells.length - 1], alignment: Word.Alignment.right });
        }
      }
    }
    for (const entry of cellAlignments) {
      entry.cell.verticalAlignment = Word.VerticalAlignment.center;
      entry.cell.body.paragraphs.load("items");
    }
    await context.sync();

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
  if (typeof Word === "undefined" || typeof Word.run !== "function") {
    throw new Error("Word API 1.3 is required for equation numbering.");
  }
  return Word.run(async (context) => {
    const body = context.document.body.getOoxml();
    await context.sync();
    return extractNumberedEquationIds(body.value).length;
  });
}

async function getValidInsertionTargetRange(context: Word.RequestContext): Promise<Word.Range> {
  const selection = context.document.getSelection();
  const parentControl = selection.parentContentControlOrNullObject;
  const parentTable = selection.parentTableOrNullObject;
  const selectedControls = selection.contentControls;
  selection.load("isEmpty");
  selection.paragraphs.load("items");
  parentControl.load("tag");
  parentTable.load("isNullObject");
  selectedControls.load("items");
  await context.sync();

  if (!parentTable.isNullObject && await tableContainsNumberControl(context, parentTable)) {
    throw new Error(INSERT_IN_NUMBERED_EQUATION_ERROR);
  }

  if (!parentControl.isNullObject && isEquationTag(parentControl.tag)) {
    throw new Error(INSERT_IN_EQUATION_ERROR);
  }
  for (const control of selectedControls.items) {
    control.load("tag");
  }
  await context.sync();
  if (selectedControls.items.some((control) => isEquationTag(control.tag))) {
    throw new Error(INSERT_IN_EQUATION_ERROR);
  }

  if (!selection.isEmpty || selection.paragraphs.items.length === 0) {
    return selection;
  }
  const paragraph = selection.paragraphs.items[0];
  paragraph.load("text");
  const previousParagraph = paragraph.getPreviousOrNullObject();
  previousParagraph.load("isNullObject");
  await context.sync();
  if (paragraph.text || previousParagraph.isNullObject) {
    return selection;
  }
  previousParagraph.load("parentTableOrNullObject");
  await context.sync();
  if (previousParagraph.parentTableOrNullObject.isNullObject) {
    return selection;
  }
  if (await tableContainsNumberControl(context, previousParagraph.parentTableOrNullObject)) {
    return paragraph.getRange(Word.RangeLocation.after);
  }
  return selection;
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
    '<w:tblGrid><w:gridCol w:w="1500"/><w:gridCol w:w="7000"/><w:gridCol w:w="1500"/></w:tblGrid>',
    "<w:tr>",
    '<w:tc><w:tcPr><w:tcW w:w="750" w:type="pct"/><w:vAlign w:val="center"/></w:tcPr><w:p/></w:tc>',
    '<w:tc><w:tcPr><w:tcW w:w="3500" w:type="pct"/><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr>',
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

function normalizeNumberedEquationTable(numberControl: Word.ContentControl): void {
  const table = numberControl.parentTable;
  table.alignment = Word.Alignment.centered;
  table.verticalAlignment = Word.VerticalAlignment.center;
  table.setCellPadding("Top", 0);
  table.setCellPadding("Bottom", 0);
  table.setCellPadding("Left", 0);
  table.setCellPadding("Right", 0);
  table.autoFitBehavior(Word.AutoFitBehavior.fixedSize);
}

function wrapEquationContentControl(omml: string, equationId: string): string {
  return wrapTaggedBlock(`${EQUATION_TAG_PREFIX}${equationId}`, normalizeOmmlForWord(omml), "LaTeXSnipper Equation");
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

function equationIdFromTag(tag: string): string {
  if (tag.startsWith(EQUATION_TAG_PREFIX)) {
    return tag.slice(EQUATION_TAG_PREFIX.length);
  }
  if (tag.startsWith(NUMBER_CONTROL_TAG_PREFIX)) {
    return tag.slice(NUMBER_CONTROL_TAG_PREFIX.length);
  }
  return "";
}

function extractNumberedEquationIds(ooxml: string): string[] {
  return uniqueMatches(ooxml, /latexsnipper-eqn-([^"&<\s]+)/g);
}

async function replaceEquationContainer(
  equationId: string,
  ooxml: string,
  omml: string,
  number?: string
): Promise<void> {
  await Word.run(async (context) => {
    const controls = context.document.contentControls.getByTag(`${EQUATION_TAG_PREFIX}${equationId}`);
    controls.load("items");
    await context.sync();
    if (controls.items.length === 0) {
      throw new Error("The equation could not be found in this document.");
    }
    const equationControl = controls.items[0];
    equationControl.load("parentTableOrNullObject");
    await context.sync();
    if (equationControl.parentTableOrNullObject.isNullObject) {
      equationControl.getRange(Word.RangeLocation.whole).insertOoxml(ooxml, Word.InsertLocation.replace);
      await context.sync();
      return;
    }
    const table = equationControl.parentTableOrNullObject;
    const layout = await inspectNumberedLayoutTable(context, table, equationId);
    if (!layout.isNumberedLayout) {
      equationControl.getRange(Word.RangeLocation.whole).insertOoxml(ooxml, Word.InsertLocation.replace);
      await context.sync();
      return;
    }
    if (number) {
      equationControl.getRange(Word.RangeLocation.whole).insertOoxml(
        buildEquationOoxml(omml, { display: true, equationId }),
        Word.InsertLocation.replace
      );
      const numberControls = context.document.contentControls.getByTag(`${NUMBER_CONTROL_TAG_PREFIX}${equationId}`);
      numberControls.load("items");
      await context.sync();
      if (numberControls.items.length === 0) {
        throw new Error("The numbered equation label could not be found in this document.");
      }
      numberControls.items[0].insertText(number, Word.InsertLocation.replace);
      normalizeNumberedEquationTable(numberControls.items[0]);
      await context.sync();
      return;
    }
    if (layout.equationIds.length > 1) {
      throw new Error(NUMBERED_LAYOUT_TRANSITION_ERROR);
    }
    const anchor = table.insertParagraph("", Word.InsertLocation.after);
    await context.sync();
    anchor.getRange(Word.RangeLocation.whole).insertOoxml(ooxml, Word.InsertLocation.replace);
    await context.sync();
    table.delete();
    await context.sync();
  });
}

type NumberedLayoutInspection = {
  isNumberedLayout: boolean;
  equationIds: string[];
};

async function inspectNumberedLayoutTable(
  context: Word.RequestContext,
  table: Word.Table,
  equationId: string
): Promise<NumberedLayoutInspection> {
  const tableOoxml = table.getRange(Word.RangeLocation.whole).getOoxml();
  await context.sync();
  return {
    isNumberedLayout: tableOoxml.value.includes(`${NUMBER_CONTROL_TAG_PREFIX}${equationId}`),
    equationIds: extractEquationIds(tableOoxml.value)
  };
}

async function tableContainsNumberControl(context: Word.RequestContext, table: Word.Table): Promise<boolean> {
  const tableOoxml = table.getRange(Word.RangeLocation.whole).getOoxml();
  await context.sync();
  return tableOoxml.value.includes(NUMBER_CONTROL_TAG_PREFIX);
}

function isEquationTag(tag: string): boolean {
  return tag.startsWith(EQUATION_TAG_PREFIX) || tag.startsWith(NUMBER_CONTROL_TAG_PREFIX);
}

function extractEquationIds(ooxml: string): string[] {
  return uniqueMatches(ooxml, /latexsnipper-eq-(?!n-)([^"&<\s]+)/g);
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
