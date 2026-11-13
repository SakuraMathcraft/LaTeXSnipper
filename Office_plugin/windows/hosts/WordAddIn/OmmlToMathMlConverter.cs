using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Xml;
using System.Xml.Linq;
using System.Xml.Xsl;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class OmmlToMathMlConverter
{
    private readonly XslCompiledTransform _transform;

    public OmmlToMathMlConverter(string stylesheetPath)
    {
        _transform = new XslCompiledTransform();
        using XmlReader stylesheet = XmlReader.Create(stylesheetPath, SecureReaderSettings());
        _transform.Load(stylesheet);
    }

    public string Convert(string omml)
    {
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new ArgumentException("OMML 内容不能为空。", nameof(omml));
        }

        using var input = XmlReader.Create(new StringReader(omml), SecureReaderSettings());
        var output = new StringBuilder();
        using (XmlWriter writer = XmlWriter.Create(output, _transform.OutputSettings))
        {
            _transform.Transform(input, writer);
        }

        string mathMl = NormalizeMathMl(output.ToString());
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new InvalidOperationException("Office OMML 转换未返回 MathML 内容。");
        }

        return mathMl;
    }

    private static string NormalizeMathMl(string value)
    {
        XDocument document = XDocument.Parse(value, LoadOptions.PreserveWhitespace);
        XElement? math = document.Root?.Name.LocalName == "math"
            ? document.Root
            : document.Descendants().FirstOrDefault(element => element.Name.LocalName == "math");
        if (math == null)
        {
            throw new InvalidOperationException("Office OMML 转换结果中缺少 MathML 内容。");
        }

        return math.ToString(SaveOptions.DisableFormatting);
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
