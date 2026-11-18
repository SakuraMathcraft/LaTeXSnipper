using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Xml;
using System.Xml.Linq;
using System.Xml.Xsl;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class MathMlToOmmlConverter
{
    private static readonly XNamespace MathMl = "http://www.w3.org/1998/Math/MathML";
    private static readonly XNamespace Word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    private static readonly XNamespace Xsl = "http://www.w3.org/1999/XSL/Transform";
    private static readonly XNamespace ColorAnnotations = "urn:latexsnipper:omml-color";
    private readonly XslCompiledTransform _transform;

    public MathMlToOmmlConverter(string stylesheetPath)
    {
        _transform = new XslCompiledTransform();
        using XmlReader stylesheet = XmlReader.Create(stylesheetPath, SecureReaderSettings());
        var document = XDocument.Load(stylesheet, LoadOptions.PreserveWhitespace);
        if (document.Root != null) AddColorRules(document.Root);
        using var prepared = document.CreateReader();
        _transform.Load(prepared);
    }

    public string Convert(string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new ArgumentException("MathML 内容不能为空。", nameof(mathMl));
        }

        using var input = XmlReader.Create(new StringReader(mathMl), SecureReaderSettings());
        var document = XDocument.Load(input, LoadOptions.PreserveWhitespace);
        if (document.Root != null) ProjectColors(document.Root, inherited: null);
        using var normalized = document.CreateReader();
        var output = new StringBuilder();
        using (XmlWriter writer = XmlWriter.Create(output, _transform.OutputSettings))
        {
            _transform.Transform(normalized, writer);
        }

        string omml = output.ToString();
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new InvalidOperationException("Office MathML 转换未返回 OMML 内容。");
        }

        return omml;
    }

    private static void ProjectColors(XElement element, string? inherited)
    {
        if (element.Name.Namespace != MathMl || element.Name.LocalName is "annotation" or "annotation-xml") return;
        var ownColor = element.Attribute("mathcolor") ?? element.Attribute("color");
        string? color = ParseColor(ownColor?.Value) ?? inherited;
        element.SetAttributeValue(ColorAnnotations + "color", color);
        foreach (var child in element.Elements()) ProjectColors(child, color);
    }

    private static string? ParseColor(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        try
        {
            Color color = ColorTranslator.FromHtml(value);
            return color.A == 0 ? null : (color.ToArgb() & 0xFFFFFF).ToString("X6");
        }
        catch (ArgumentException)
        {
            // Word run color is opaque RGB. Unsupported CSS values inherit the surrounding color.
            return null;
        }
    }

    private static void AddColorRules(XElement stylesheet)
    {
        var templates = stylesheet.Elements(Xsl + "template");
        var run = templates.FirstOrDefault(template => (string?)template.Attribute("name") == "CreateRunProp");
        var runLimit = templates.FirstOrDefault(template => (string?)template.Attribute("name") == "CreateRunWithSameProp")
            ?.Elements(Xsl + "variable").FirstOrDefault(variable => (string?)variable.Attribute("name") == "nndBeforeLim")
            ?.Attribute("select");
        const string limitStart = "count($ndTokenFirst/following-sibling::*";
        if (run == null || runLimit == null || !runLimit.Value.StartsWith(limitStart, StringComparison.Ordinal)) return;
        int predicate = runLimit.Value.IndexOf('[', limitStart.Length);
        if (predicate < 0) return;

        // Keep Word's native structure transform. Supply the run color and stop
        // its token aggregation when siblings have different effective colors.
        stylesheet.SetAttributeValue(XNamespace.Xmlns + "lsfmt", ColorAnnotations.NamespaceName);
        string excluded = ((string?)stylesheet.Attribute("exclude-result-prefixes") ?? "") + " lsfmt";
        stylesheet.SetAttributeValue("exclude-result-prefixes", excluded.Trim());
        runLimit.Value = runLimit.Value.Insert(predicate + 1, "string(@lsfmt:color) != string($ndTokenFirst/@lsfmt:color) or ");
        run.Add(new XElement(Xsl + "if", new XAttribute("test", "$ndCur/@lsfmt:color"),
            new XElement(Word + "rPr",
                new XElement(Word + "color", new XAttribute(Word + "val", "{$ndCur/@lsfmt:color}")))));
    }

    private static XmlReaderSettings SecureReaderSettings()
    {
        return new XmlReaderSettings
        {
            DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null
        };
    }
}
