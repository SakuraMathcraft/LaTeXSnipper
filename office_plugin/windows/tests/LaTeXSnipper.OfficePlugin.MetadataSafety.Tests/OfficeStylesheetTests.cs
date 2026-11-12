using System;
using System.IO;
using System.Text;
using System.Xml.Xsl;
using LaTeXSnipper.OfficePlugin.WordAddIn;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class OfficeStylesheetTests
{
    private string _root = string.Empty;
    private string _directory = string.Empty;

    [TestInitialize]
    public void Start()
    {
        _root = Path.Combine(Path.GetTempPath(), "latexsnipper-office-" + Guid.NewGuid().ToString("N"));
        _directory = Path.Combine(_root, "自定义 Office", "Office16");
        Directory.CreateDirectory(_directory);
        WriteStylesheet("MML2OMML.XSL", "<m:oMath xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\"><m:r><m:t>custom-office</m:t></m:r></m:oMath>");
        WriteStylesheet("OMML2MML.XSL", "<math xmlns=\"http://www.w3.org/1998/Math/MathML\"><mi>custom-office</mi></math>");
    }

    [TestCleanup]
    public void Finish() => Directory.Delete(_root, true);

    [STATestMethod]
    public void ConvertersUseTheRunningWordInstallationDirectory()
    {
        using var adapter = new DynamicWordApplicationAdapter(new WordApplicationPath(_directory));
        Assert.AreEqual(_directory, adapter.InstallationDirectory);
        var forward = new MathMlToOmmlConverter(Path.Combine(adapter.InstallationDirectory, "MML2OMML.XSL"));
        var reverse = new OmmlToMathMlConverter(Path.Combine(adapter.InstallationDirectory, "OMML2MML.XSL"));

        StringAssert.Contains(forward.Convert("<math/>"), "custom-office");
        StringAssert.Contains(reverse.Convert("<oMath/>"), "custom-office");
    }

    [STATestMethod]
    public void MissingStylesheetsDoNotPreventAdapterInitialization()
    {
        File.Delete(Path.Combine(_directory, "MML2OMML.XSL"));
        File.Delete(Path.Combine(_directory, "OMML2MML.XSL"));

        using var adapter = new DynamicWordApplicationAdapter(new WordApplicationPath(_directory));

        Assert.AreEqual(_directory, adapter.InstallationDirectory);
    }

    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public void MissingStylesheetFailsConversionSetup(bool forward)
    {
        string path = Path.Combine(_directory, forward ? "MML2OMML.XSL" : "OMML2MML.XSL");
        File.Delete(path);

        Assert.ThrowsExactly<FileNotFoundException>(() => LoadConverter(path, forward));
    }

    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public void InvalidStylesheetFailsConversionSetup(bool forward)
    {
        string path = Path.Combine(_directory, forward ? "MML2OMML.XSL" : "OMML2MML.XSL");
        File.WriteAllText(path, "<invalid-stylesheet/>", new UTF8Encoding(false, true));

        Assert.Throws<XsltException>(() => LoadConverter(path, forward));
    }

    private static void LoadConverter(string path, bool forward)
    {
        if (forward) _ = new MathMlToOmmlConverter(path);
        else _ = new OmmlToMathMlConverter(path);
    }

    private void WriteStylesheet(string file, string output)
    {
        string stylesheet = "<xsl:stylesheet version=\"1.0\" xmlns:xsl=\"http://www.w3.org/1999/XSL/Transform\">"
            + "<xsl:output omit-xml-declaration=\"yes\"/><xsl:template match=\"/\">"
            + output + "</xsl:template></xsl:stylesheet>";
        File.WriteAllText(Path.Combine(_directory, file), stylesheet, new UTF8Encoding(false, true));
    }
}

public sealed class WordApplicationPath
{
    public WordApplicationPath(string path) => Path = path;

    public string Path { get; }
}
