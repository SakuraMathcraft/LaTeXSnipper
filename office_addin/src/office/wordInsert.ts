import { ConversionResult } from "../services/bridgeClient";
import { loadEquationSource, saveEquationSource } from "../services/equationSession";

const EQUATION_TAG_PREFIX = "latexsnipper-equation:";
const LEGACY_NUMBER_TAG_PREFIX = "latexsnipper-equation-number:";
const NUMBER_CONTROL_TAG = "latexsnipper-equation-number";
const NUMBER_CONTROL_ALIAS_PREFIX = "LaTeXSnipper Equation Number:";

export type EquationDraft = {
  latex: string;
  display: boolean;
  numbering: "none" | "auto" | "manual";
  manualNumber?: string;
  equationId?: string;
};

export type SelectedEquation = {
  equationId: string;
  latex: string;
};

export async function insertEquationIntoWord(draft: EquationDraft, conversion: ConversionResult): Promise<void> {
  if (!conversion.omml || !looksLikeOmml(conversion.omml)) {
    throw new Error("The bridge did not return editable OMML.");
  }
  const number = await resolveNumber(draft);
  const equationId = await saveEquationSource(draft.latex, draft.equationId);
  const ooxml = buildEquationOoxml(conversion.omml, {
    display: draft.display,
    equationId,
    number
  });

  if (typeof Word !== "undefined" && Word.run) {
    await Word.run(async (context) => {
      const range = context.document.getSelection();
      const insertedRange = range.insertOoxml(ooxml, Word.InsertLocation.replace);
      moveSelectionAfterInsertedEquation(insertedRange, draft.display);
      await context.sync();
    });
    return;
  }

  await setSelectedOoxml(ooxml);
}

export async function loadSelectedEquationFromWord(): Promise<SelectedEquation> {
  const equationId = await getSelectedEquationIdFromWord();
  if (!equationId) {
    throw new Error("Select a LaTeXSnipper equation first.");
  }
  const latex = loadEquationSource(equationId);
  if (!latex) {
    throw new Error("The selected equation does not have saved LaTeX source.");
  }
  return { equationId, latex };
}

export async function getSelectedEquationIdFromWord(): Promise<string> {
  const ooxml = await getSelectedOoxml();
  return extractEquationId(ooxml);
}

export async function renumberWordEquations(): Promise<number> {
  if (typeof Word === "undefined" || !Word.run) {
    throw new Error("Renumbering is available in Word only.");
  }
  return Word.run(async (context) => {
    const modernControls = context.document.contentControls.getByTag(NUMBER_CONTROL_TAG);
    modernControls.load("items");
    await context.sync();

    let controls = modernControls.items;
    if (controls.length === 0) {
      controls = await loadLegacyNumberControls(context);
    }
    controls.forEach((control, index) => {
      normalizeNumberedEquationTable(control);
      control.insertText(`(${index + 1})`, Word.InsertLocation.replace);
    });
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
    return countNumberControls(body.value);
  });
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
      NUMBER_CONTROL_TAG,
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
  table.autoFitWindow();
  table.autoFitBehavior(Word.AutoFitBehavior.fixedSize);
}

function wrapEquationContentControl(omml: string, equationId: string): string {
  return wrapTaggedBlock(`${EQUATION_TAG_PREFIX}${equationId}`, omml, "LaTeXSnipper Equation");
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
    extractFirstMatch(ooxml, /latexsnipper-equation:([^"&<\s]+)/) ||
    extractFirstMatch(ooxml, /latexsnipper-equation-row:([^"&<\s]+)/) ||
    extractFirstMatch(ooxml, /latexsnipper-equation-number:([^"&<\s]+)/) ||
    extractFirstMatch(ooxml, /LaTeXSnipper Equation Number:([^"&<\s]+)/) ||
    ""
  );
}

function extractFirstMatch(value: string, pattern: RegExp): string {
  return pattern.exec(value)?.[1] || "";
}

async function loadLegacyNumberControls(context: Word.RequestContext): Promise<Word.ContentControl[]> {
  const body = context.document.body.getOoxml();
  await context.sync();
  const ids = extractLegacyNumberControlIds(body.value);
  if (ids.length === 0) {
    return [];
  }
  const collections = ids.map((id) => {
    const collection = context.document.contentControls.getByTag(`${LEGACY_NUMBER_TAG_PREFIX}${id}`);
    collection.load("items");
    return collection;
  });
  await context.sync();
  return collections.flatMap((collection) => collection.items);
}

function extractLegacyNumberControlIds(ooxml: string): string[] {
  return uniqueMatches(ooxml, /latexsnipper-equation-number:([^"&<\s]+)/g);
}

function countNumberControls(ooxml: string): number {
  const modern = (ooxml.match(/w:tag w:val="latexsnipper-equation-number"/g) || []).length;
  const legacy = extractLegacyNumberControlIds(ooxml).length;
  return modern + legacy;
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
