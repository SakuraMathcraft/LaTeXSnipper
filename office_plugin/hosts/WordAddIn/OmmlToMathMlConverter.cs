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

    public OmmlToMathMlConverter(string? stylesheetPath = null)
    {
        string path = stylesheetPath ?? ResolveOfficeStylesheet();
        _transform = new XslCompiledTransform();
        using XmlReader stylesheet = XmlReader.Create(path, SecureReaderSettings());
        _transform.Load(stylesheet);
    }

    public string Convert(string omml)
    {
        if (string.IsNullOrWhiteSpace(omml))
        {
            throw new ArgumentException("OMML is required.", nameof(omml));
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
            throw new InvalidOperationException("Office OMML transform returned empty MathML.");
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
            throw new InvalidOperationException("Office OMML transform did not return MathML.");
        }

        return math.ToString(SaveOptions.DisableFormatting);
    }

    private static string ResolveOfficeStylesheet()
    {
        string[] roots =
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86)
        };
        string[] relativePaths =
        {
            @"Microsoft Office\root\Office16\OMML2MML.XSL",
            @"Microsoft Office\Office16\OMML2MML.XSL"
        };
        foreach (string root in roots)
        {
            foreach (string relativePath in relativePaths)
            {
                string candidate = Path.Combine(root, relativePath);
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }
        }

        throw new FileNotFoundException("Microsoft Office OMML2MML.XSL was not found.");
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
