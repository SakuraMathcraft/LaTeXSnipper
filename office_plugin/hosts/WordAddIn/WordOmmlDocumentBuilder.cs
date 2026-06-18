using System;
using System.Linq;
using System.Security;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class WordOmmlDocumentBuilder
{
    public static string BuildFlatOpcDocument(string omml, string equationId, bool display)
    {
        return BuildFlatOpcDocument(
            omml,
            new FormulaMetadata(
                new FormulaIdentity("active-document", equationId),
                string.Empty,
                display ? FormulaDisplayMode.Display : FormulaDisplayMode.Inline,
                NumberingMode.None,
                string.Empty,
                RenderEngineKind.Omml,
                schemaVersion: 1),
            display);
    }

    public static string BuildFlatOpcDocument(string omml, FormulaMetadata metadata, bool display)
    {
        return BuildFlatOpcDocument(omml, metadata, display, WordPluginSettings.Load().NumberPlacement);
    }

    public static string BuildFlatOpcDocument(string omml, FormulaMetadata metadata, bool display, WordNumberPlacement numberPlacement)
    {
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new ArgumentException("OMML is required.", nameof(omml));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        string equationId = metadata.Identity.EquationId;
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(metadata));
        }

        string body = display
            ? BuildDisplayBody(omml, metadata, numberPlacement)
            : BuildInlineBody(omml, metadata);
        string documentXml =
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"" +
            " xmlns:w15=\"http://schemas.microsoft.com/office/word/2012/wordml\"" +
            " xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\">" +
            "<w:body>" + body + "</w:body></w:document>";
        return WrapFlatOpc(documentXml);
    }

    public static string BuildFlatOpcInlineEquationDocument(string omml, FormulaMetadata metadata)
    {
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new ArgumentException("OMML is required.", nameof(omml));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        string equationId = metadata.Identity.EquationId;
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(metadata));
        }

        string documentXml =
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"" +
            " xmlns:w15=\"http://schemas.microsoft.com/office/word/2012/wordml\"" +
            " xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\">" +
            "<w:body>" + BuildInlineBody(omml, metadata) + "</w:body></w:document>";
        return WrapFlatOpc(documentXml);
    }

    public static string BuildFlatOpcEquationContentDocument(string omml)
    {
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new ArgumentException("OMML is required.", nameof(omml));
        }

        string documentXml =
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"" +
            " xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\">" +
            "<w:body><w:p>" + ExtractEquationOmml(omml) + "</w:p></w:body></w:document>";
        return WrapFlatOpc(documentXml);
    }

    private static string BuildInlineBody(string omml, FormulaMetadata metadata)
    {
        return "<w:p>" +
            WrapEquationContentControl(omml, metadata) +
            "</w:p>";
    }

    private static string BuildDisplayBody(string omml, FormulaMetadata metadata, WordNumberPlacement numberPlacement)
    {
        if (metadata.NumberingMode != NumberingMode.None && !string.IsNullOrWhiteSpace(metadata.NumberText))
        {
            return BuildNumberedDisplayBody(omml, metadata, numberPlacement);
        }

        return "<w:p><w:pPr>" + ParagraphSpacing() + "<w:jc w:val=\"center\"/></w:pPr>" +
            WrapEquationContentControl(omml, metadata) +
            "</w:p>";
    }

    private static string BuildNumberedDisplayBody(string omml, FormulaMetadata metadata, WordNumberPlacement numberPlacement)
    {
        string equationId = metadata.Identity.EquationId;
        string numberControl = WrapNumberContentControl(
            WordFormulaMetadataStore.BuildNumberTag(equationId),
            WordFormulaMetadataStore.BuildNumberAlias(equationId),
            metadata.NumberText);
        string equationControl = WrapEquationContentControl(omml, metadata);
        string leftNumber = numberPlacement == WordNumberPlacement.Left ? numberControl : string.Empty;
        string rightNumber = numberPlacement == WordNumberPlacement.Right ? numberControl : string.Empty;
        return
            "<w:p><w:pPr>" + ParagraphSpacing() +
            "<w:jc w:val=\"left\"/>" +
            "</w:pPr>" +
            leftNumber +
            "<w:r><w:tab/></w:r>" +
            equationControl +
            (numberPlacement == WordNumberPlacement.Right ? "<w:r><w:tab/></w:r>" : string.Empty) +
            rightNumber +
            "</w:p>";
    }

    private static string WrapEquationContentControl(string omml, FormulaMetadata metadata)
    {
        return
            "<w:sdt><w:sdtPr>" +
            "<w:alias w:val=\"LaTeXSnipper Equation\"/>" +
            "<w:tag w:val=\"" + EscapeXml(WordFormulaMetadataStore.BuildEquationTag(metadata.Identity.EquationId)) + "\"/>" +
            "</w:sdtPr><w:sdtContent>" +
            ExtractEquationOmml(omml) +
            "</w:sdtContent></w:sdt>";
    }

    private static string WrapNumberContentControl(string tag, string alias, string text)
    {
        return
            "<w:sdt><w:sdtPr>" +
            "<w:alias w:val=\"" + EscapeXml(alias) + "\"/>" +
            "<w:tag w:val=\"" + EscapeXml(tag) + "\"/>" +
            "<w15:appearance w15:val=\"hidden\"/>" +
            "</w:sdtPr><w:sdtContent><w:r><w:t>" +
            EscapeXml(text) +
            "</w:t></w:r></w:sdtContent></w:sdt>";
    }

    private static string NormalizeOmmlForWord(string omml)
    {
        return omml.Replace(" xmlns:mml=\"http://www.w3.org/1998/Math/MathML\"", string.Empty);
    }

    private static string ExtractEquationOmml(string omml)
    {
        XElement root = XElement.Parse(NormalizeOmmlForWord(omml), LoadOptions.PreserveWhitespace);
        XElement? equation = root.Name.LocalName == "oMath"
            ? root
            : root.Descendants().FirstOrDefault(element => element.Name.LocalName == "oMath");
        if (equation == null)
        {
            throw new InvalidOperationException("OMML does not contain an m:oMath equation.");
        }

        return equation.ToString(SaveOptions.DisableFormatting);
    }

    private static string ParagraphSpacing()
    {
        return "<w:spacing w:before=\"0\" w:after=\"0\"/>";
    }

    private static string WrapFlatOpc(string documentXml)
    {
        return
            "<pkg:package xmlns:pkg=\"http://schemas.microsoft.com/office/2006/xmlPackage\">" +
            "<pkg:part pkg:name=\"/_rels/.rels\" pkg:contentType=\"application/vnd.openxmlformats-package.relationships+xml\" pkg:padding=\"512\">" +
            "<pkg:xmlData><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>" +
            "</Relationships></pkg:xmlData></pkg:part>" +
            "<pkg:part pkg:name=\"/word/document.xml\" pkg:contentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\">" +
            "<pkg:xmlData>" + documentXml + "</pkg:xmlData></pkg:part></pkg:package>";
    }

    private static string EscapeXml(string value)
    {
        return SecurityElement.Escape(value) ?? string.Empty;
    }
}
