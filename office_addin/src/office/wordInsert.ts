import { ConversionResult } from "../services/bridgeClient";
import { allocateEquationNumber } from "../services/equationSession";

export type EquationDraft = {
  latex: string;
  display: boolean;
  numbering: "none" | "auto" | "manual";
  manualNumber?: string;
};

export async function insertEquationIntoWord(draft: EquationDraft, conversion: ConversionResult): Promise<void> {
  if (!conversion.omml || !looksLikeOmml(conversion.omml)) {
    throw new Error("The bridge did not return editable OMML.");
  }
  const number = await resolveNumber(draft);
  const ooxml = buildEquationOoxml(conversion.omml, {
    display: draft.display,
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

function looksLikeOmml(value: string): boolean {
  return /<m:oMath(?:Para)?[\s>]/.test(value);
}

async function resolveNumber(draft: EquationDraft): Promise<string | undefined> {
  if (draft.numbering === "manual") {
    const value = (draft.manualNumber || "").trim();
    return value || undefined;
  }
  if (draft.numbering === "auto") {
    return allocateEquationNumber();
  }
  return undefined;
}

function buildEquationOoxml(omml: string, options: { display: boolean; number?: string }): string {
  const body = options.display ? buildDisplayBody(omml, options.number) : buildInlineBody(omml);
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

function buildInlineBody(omml: string): string {
  return `<w:p>${omml}</w:p>`;
}

function buildDisplayBody(omml: string, number?: string): string {
  if (!number) {
    return `<w:p><w:pPr><w:jc w:val="center"/></w:pPr>${omml}</w:p>`;
  }
  return [
    '<w:tbl><w:tblPr>',
    '<w:tblW w:w="0" w:type="auto"/>',
    '<w:tblBorders><w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>',
    "</w:tblPr>",
    '<w:tblGrid><w:gridCol w:w="8500"/><w:gridCol w:w="1500"/></w:tblGrid>',
    "<w:tr>",
    '<w:tc><w:tcPr><w:tcW w:w="8500" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr>',
    omml,
    "</w:p></w:tc>",
    '<w:tc><w:tcPr><w:tcW w:w="1500" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:t>',
    escapeXml(number),
    "</w:t></w:r></w:p></w:tc>",
    "</w:tr></w:tbl>"
  ].join("");
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
