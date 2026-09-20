using System;
using System.Linq;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class OmmlTypographyTests
{
    private static readonly XNamespace M = "http://schemas.openxmlformats.org/officeDocument/2006/math";
    private static readonly XNamespace W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

    [TestMethod]
    public void RunPropertiesPreserveLocalStylesAndFormulaStructure()
    {
        var numerator = new XElement(M + "r", new XElement(M + "rPr", new XElement(M + "sty", new XAttribute(M + "val", "b"))),
            new XElement(W + "rPr", new XElement(W + "color", new XAttribute(W + "val", "FF0000"))), new XElement(M + "t", "123"));
        var denominator = new XElement(M + "r", new XElement(M + "t", "x"));
        var text = new XElement(M + "r", new XElement(M + "rPr", new XElement(M + "nor")), new XElement(M + "t", "12汉字"));
        string source = new XElement(M + "oMath", new XAttribute("id", "unchanged"),
            new XElement(M + "f", new XElement(M + "num", numerator), new XElement(M + "den", denominator)), text).ToString();
        var style = new FormulaTypography("mathjax-stix2", "Arial", "SimSun", FormulaMathStyle.Bold, 10.5, "#112233");
        string result = OmmlTypographyMapper.Apply(source, style);
        XElement root = XElement.Parse(result);
        XElement[] runs = root.Descendants(M + "r").ToArray();
        Assert.AreEqual("unchanged", (string?)root.Attribute("id"));
        Assert.AreEqual(1, root.Descendants(M + "f").Count());
        Assert.AreEqual("Arial", (string?)runs[0].Element(W + "rPr")?.Element(W + "rFonts")?.Attribute(W + "ascii"));
        Assert.AreEqual("STIX Two Math", (string?)runs[1].Element(W + "rPr")?.Element(W + "rFonts")?.Attribute(W + "ascii"));
        Assert.AreEqual("Times New Roman", (string?)runs[2].Element(W + "rPr")?.Element(W + "rFonts")?.Attribute(W + "ascii"));
        Assert.AreEqual("FF0000", (string?)runs[0].Element(W + "rPr")?.Element(W + "color")?.Attribute(W + "val"));
        Assert.AreEqual("b", (string?)runs[0].Element(M + "rPr")?.Element(M + "sty")?.Attribute(M + "val"));
        foreach (XElement run in runs)
        {
            Assert.AreEqual("SimSun", (string?)run.Element(W + "rPr")?.Element(W + "rFonts")?.Attribute(W + "eastAsia"));
            Assert.AreEqual("21", (string?)run.Element(W + "rPr")?.Element(W + "sz")?.Attribute(W + "val"));
        }
        Assert.IsTrue(XNode.DeepEquals(XElement.Parse(result), XElement.Parse(OmmlTypographyMapper.Apply(result, style))));
    }

    [TestMethod]
    public void RejectsUnrelatedXmlAndUnknownFontSchemes()
    {
        Assert.ThrowsExactly<ArgumentException>(() => OmmlTypographyMapper.Apply("<root/>", FormulaTypography.Default));
        var unknown = new FormulaTypography("unknown-font", null, "SimSun", FormulaMathStyle.Automatic, 12, "#000000");
        Assert.ThrowsExactly<ArgumentException>(() => OmmlTypographyMapper.Apply(new XElement(M + "oMath").ToString(), unknown));
    }
}
