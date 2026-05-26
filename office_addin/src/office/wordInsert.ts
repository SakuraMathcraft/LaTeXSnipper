import { ConversionResult } from "../services/bridgeClient";
import { loadEquationSource, saveEquationSource } from "../services/equationSession";

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
      range.insertOoxml(ooxml, Word.InsertLocation.replace);
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
    const body = context.document.body;
    const current = body.getOoxml();
    await context.sync();
    const { ooxml, count } = renumberTaggedEquationOoxml(current.value);
    if (count === 0) {
      return 0;
    }
    body.insertOoxml(ooxml, Word.InsertLocation.replace);
    await context.sync();
    return count;
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
    return `(${(await countExistingLaTeXSnipperEquations()) + 1})`;
  }
  return undefined;
}

async function countExistingLaTeXSnipperEquations(): Promise<number> {
  if (typeof Word === "undefined" || !Word.run) {
    return 0;
  }
  return Word.run(async (context) => {
    const body = context.document.body.getOoxml();
    await context.sync();
    return (body.value.match(/latexsnipper-equation:/g) || []).length;
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
    '<w:tblW w:w="0" w:type="auto"/>',
    '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>',
    "</w:tblPr>",
    '<w:tblGrid><w:gridCol w:w="8500"/><w:gridCol w:w="1500"/></w:tblGrid>',
    "<w:tr>",
    '<w:tc><w:tcPr><w:tcW w:w="8500" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr>',
    wrapEquationContentControl(omml, equationId),
    "</w:p></w:tc>",
    '<w:tc><w:tcPr><w:tcW w:w="1500" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="right"/></w:pPr>',
    wrapTextContentControl(`latexsnipper-equation-number:${equationId}`, number),
    "</w:p></w:tc>",
    "</w:tr></w:tbl>"
  ].join("");
  return wrapTaggedBlock(`latexsnipper-equation-row:${equationId}`, table);
}

function wrapEquationContentControl(omml: string, equationId: string): string {
  return wrapTaggedBlock(`latexsnipper-equation:${equationId}`, omml, "LaTeXSnipper Equation");
}

function wrapTextContentControl(tag: string, text: string): string {
  return [
    "<w:sdt>",
    "<w:sdtPr>",
    '<w:alias w:val="LaTeXSnipper Equation Number"/>',
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
  const match = /latexsnipper-equation(?:-row|-number)?:([^"&<\s]+)/.exec(ooxml);
  return match?.[1] || "";
}

function renumberTaggedEquationOoxml(ooxml: string): { ooxml: string; count: number } {
  let index = 0;
  const updated = ooxml.replace(
    /(<w:sdt\b(?:(?!<\/w:sdt>).)*?latexsnipper-equation-number:[^"&<\s]+(?:(?!<\/w:sdt>).)*?<w:t(?:\s[^>]*)?>)(?:\(\d+\)|[^<]*)(<\/w:t>)/gs,
    (_match, prefix: string, suffix: string) => {
      index += 1;
      return `${prefix}(${index})${suffix}`;
    }
  );
  return { ooxml: updated, count: index };
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
