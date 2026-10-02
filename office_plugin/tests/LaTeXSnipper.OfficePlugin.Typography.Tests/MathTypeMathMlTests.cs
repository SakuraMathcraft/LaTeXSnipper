using System;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class MathTypeMathMlTests
{
    [TestMethod]
    public void OneSidedFenceKeepsTableAndStyleWithoutEmptyOperator()
    {
        const string source = "<math xmlns='http://www.w3.org/1998/Math/MathML' display='block'><mstyle mathcolor='#d52020'><mrow>"
            + "<mo>{</mo><mtable><mtr><mtd><mi>μ</mi></mtd></mtr></mtable><mo fence='true'/></mrow></mstyle></math>";
        var expected = XDocument.Parse(source);
        XNamespace ns = expected.Root!.Name.Namespace;
        expected.Root.Element(ns + "mstyle")!.Element(ns + "mrow")!.Element(ns + "mtable")!.NextNode!.Remove();
        var actual = XDocument.Parse(MathTypeMathMl.PrepareForImport(source));
        Assert.IsTrue(XNode.DeepEquals(expected, actual));
    }

    [TestMethod]
    public void OrdinaryOperatorsAndExplicitSpaceRemainIntact()
    {
        const string source = "<math xmlns='http://www.w3.org/1998/Math/MathML'><msup><mi>e</mi><mi>i</mi></msup>"
            + "<mo>+</mo><mn>1</mn><mspace width='1em'/><mo>=</mo><mn>0</mn></math>";
        Assert.IsTrue(XNode.DeepEquals(XDocument.Parse(source), XDocument.Parse(MathTypeMathMl.PrepareForImport(source))));
    }

    [TestMethod]
    public void NonMathMlInputIsRejected()
        => Assert.ThrowsExactly<ArgumentException>(() => MathTypeMathMl.PrepareForImport("<math><mi>x</mi></math>"));
}
