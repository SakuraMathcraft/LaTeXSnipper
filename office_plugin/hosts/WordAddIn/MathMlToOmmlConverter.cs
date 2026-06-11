using System;
using System.IO;
using System.Text;
using System.Xml;
using System.Xml.Xsl;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class MathMlToOmmlConverter
{
    private readonly XslCompiledTransform _transform;

    public MathMlToOmmlConverter(string? stylesheetPath = null)
    {
        string path = stylesheetPath ?? ResolveOfficeStylesheet();
        _transform = new XslCompiledTransform();
        using XmlReader stylesheet = XmlReader.Create(path, SecureReaderSettings());
        _transform.Load(stylesheet);
    }

    public string Convert(string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new ArgumentException("MathML is required.", nameof(mathMl));
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
            throw new InvalidOperationException("Office MathML transform returned empty OMML.");
        }

        return omml;
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
            @"Microsoft Office\root\Office16\MML2OMML.XSL",
            @"Microsoft Office\Office16\MML2OMML.XSL"
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

        throw new FileNotFoundException("Microsoft Office MML2OMML.XSL was not found.");
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
