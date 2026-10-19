using System;
using System.IO;
using System.Text;
using System.Xml;
using System.Xml.Xsl;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class MathMlToOmmlConverter
{
    private readonly XslCompiledTransform _transform;

    public MathMlToOmmlConverter(string stylesheetPath)
    {
        _transform = new XslCompiledTransform();
        using XmlReader stylesheet = XmlReader.Create(stylesheetPath, SecureReaderSettings());
        _transform.Load(stylesheet);
    }

    public string Convert(string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new ArgumentException("MathML 内容不能为空。", nameof(mathMl));
        }

        using var input = XmlReader.Create(new StringReader(mathMl), SecureReaderSettings());
        var output = new StringBuilder();
        using (XmlWriter writer = XmlWriter.Create(output, _transform.OutputSettings))
        {
            _transform.Transform(input, writer);
        }

        string omml = output.ToString();
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new InvalidOperationException("Office MathML 转换未返回 OMML 内容。");
        }

        return omml;
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
