using System;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Applies supported Word run properties to freshly converted semantic OMML; Word owns its layout.</summary>
public static class OmmlTypographyMapper
{
    private static readonly XNamespace Math = "http://schemas.openxmlformats.org/officeDocument/2006/math";
    private static readonly XNamespace Word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

    /// <summary>
    /// Input must be freshly converted from styled MathML, not previously formatted document XML.
    /// Source-local style and color properties emitted by the converter remain authoritative.
    /// </summary>
    public static string Apply(string omml, FormulaTypography typography)
    {
        if (typography == null) throw new ArgumentNullException(nameof(typography));
        XElement root = XElement.Parse(omml, LoadOptions.PreserveWhitespace);
        if (root.Name != Math + "oMath" && root.Name != Math + "oMathPara")
            throw new ArgumentException("需要 OMML 公式根节点。", nameof(omml));
        string symbolFamily = typography.SymbolFontId switch
        {
            "mathjax-tex" => "Cambria Math",
            "mathjax-stix2" => "STIX Two Math",
            _ => throw new ArgumentException("不支持的数学字体方案。", nameof(typography))
        };
        string size = System.Math.Round(typography.FontSizePoints * 2, MidpointRounding.AwayFromZero)
            .ToString(CultureInfo.InvariantCulture);
        foreach (XElement run in root.Descendants(Math + "r"))
        {
            string text = string.Concat(run.Elements(Math + "t").Select(t => t.Value));
            XElement? normal = run.Element(Math + "rPr")?.Element(Math + "nor");
            bool isText = normal != null && (string?)normal.Attribute(Math + "val") != "0"
                && (string?)normal.Attribute(Math + "val") != "false";
            bool isNumber = !isText && Regex.IsMatch(text, @"\A\p{Nd}+(?:[.,]\p{Nd}+)*\z");
            string family = isText ? "Times New Roman" : isNumber && typography.NumberFontFamily != null
                ? typography.NumberFontFamily : symbolFamily;
            XElement? properties = run.Element(Word + "rPr");
            if (properties == null)
            {
                properties = new XElement(Word + "rPr");
                XElement? mathProperties = run.Element(Math + "rPr");
                if (mathProperties == null) run.AddFirst(properties);
                else mathProperties.AddAfterSelf(properties);
            }
            XElement? fonts = properties.Element(Word + "rFonts");
            if (fonts == null) { fonts = new XElement(Word + "rFonts"); properties.AddFirst(fonts); }
            fonts.SetAttributeValue(Word + "ascii", family);
            fonts.SetAttributeValue(Word + "hAnsi", family);
            fonts.SetAttributeValue(Word + "eastAsia", typography.CjkFontFamily);
            foreach (string theme in new[] { "asciiTheme", "hAnsiTheme", "eastAsiaTheme" }) fonts.Attribute(Word + theme)?.Remove();
            SetDefault(properties, "color", typography.Color.Substring(1));
            SetDefault(properties, "sz", size);
            SetDefault(properties, "szCs", size);
        }
        return root.ToString(SaveOptions.DisableFormatting);
    }

    private static void SetDefault(XElement properties, string name, string value)
    {
        if (properties.Element(Word + name) == null)
            properties.Add(new XElement(Word + name, new XAttribute(Word + "val", value)));
    }
}
