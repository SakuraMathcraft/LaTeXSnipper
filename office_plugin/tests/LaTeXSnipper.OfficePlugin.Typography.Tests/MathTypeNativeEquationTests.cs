using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class MathTypeNativeEquationTests
{
    [TestMethod]
    public void ReadsEquationNativeProducedByInstalledMathType()
    {
        using var fixture = typeof(MathTypeNativeEquationTests).Assembly.GetManifestResourceStream(
            "LaTeXSnipper.OfficePlugin.Typography.Tests.Fixtures.MathTypeChineseEquationNative.bin")!;
        using var buffer = new MemoryStream();
        fixture.CopyTo(buffer);
        byte[] native = buffer.ToArray();
        Assert.AreEqual("端", XDocument.Parse(MathTypeNativeEquation.ReadMathMl(native)).Root!.Value);
        Assert.AreEqual(12d, MathTypeNativeEquation.ReadFontSizePoints(native), 0.001);
    }

    [TestMethod]
    public void ScopedColorsDoNotLeakIntoFollowingTokens()
    {
        byte[] native = MathTypeNativeEquation.Create("<math><mstyle mathcolor='#ff0000'><mi>x</mi><mstyle mathcolor='#0000ff'><mi>y</mi></mstyle><mi>z</mi></mstyle><mi>w</mi></math>", 12);
        var tokens = XDocument.Parse(MathTypeNativeEquation.ReadMathMl(native)).Descendants().Where(e => e.Name.LocalName == "mi").ToArray();
        CollectionAssert.AreEqual(new[] { "#ff0000", "#0000ff", "#ff0000", "" }, tokens.Select(e => (string?)e.Attribute("mathcolor") ?? "").ToArray());
    }

    [TestMethod]
    public void LocalSizeIsRejectedRatherThanSilentlyDiscarded()
        => Assert.ThrowsExactly<InvalidDataException>(() => MathTypeNativeEquation.Create("<math><mstyle mathsize='20pt'><mi>x</mi></mstyle></math>", 12));
    [TestMethod]
    [DataRow("<msup><mi>e</mi><mrow><mi>i</mi><mi>π</mi></mrow></msup><mo>+</mo><mn>1</mn><mo>=</mo><mn>0</mn>", "msup")]
    [DataRow("<mfrac><mi>x</mi><mi>y</mi></mfrac><mtext>端</mtext>", "mfrac")]
    [DataRow("<msqrt><mi>x</mi><mo>+</mo><mn>1</mn></msqrt>", "msqrt")]
    [DataRow("<mtable><mtr><mtd><mi>a</mi></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi></mtd><mtd><mi>d</mi></mtd></mtr></mtable>", "mtable")]
    public void NativeContentRetainsStructureColorSizeAndNamespace(string body, string structure)
    {
        string mathMl = "<math xmlns='http://www.w3.org/1998/Math/MathML'><mstyle mathcolor='#d52020'>" + body + "</mstyle></math>";
        byte[] native = MathTypeNativeEquation.Create(mathMl, 18);
        var decoded = XDocument.Parse(MathTypeNativeEquation.ReadMathMl(native));
        Assert.AreEqual(18d, MathTypeNativeEquation.ReadFontSizePoints(native), 0.001);
        Assert.IsTrue(decoded.Descendants().Any(e => e.Name.LocalName == structure));
        Assert.IsTrue(decoded.Descendants().All(e => e.Name.NamespaceName == "http://www.w3.org/1998/Math/MathML"));
        Assert.IsTrue(decoded.Descendants().Attributes("mathcolor").Any(a => a.Value == "#d52020"));
        if (body.Contains("端")) Assert.IsTrue(decoded.Root!.Value.Contains("端"));
    }

    [TestMethod]
    public void TruncatedNativeDataIsRejected()
    {
        var native = MathTypeNativeEquation.Create("<math><mi>x</mi></math>", 12);
        Assert.ThrowsExactly<InvalidDataException>(() => MathTypeNativeEquation.ReadMathMl(native.Take(native.Length - 2).ToArray()));
    }

    [TestMethod]
    public void UnsupportedStructureIsRejected()
        => Assert.ThrowsExactly<InvalidDataException>(() => MathTypeNativeEquation.Create("<math><unknown><mi>x</mi></unknown></math>", 12));
}
