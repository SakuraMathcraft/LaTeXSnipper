using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class FormulaTypographyTests
{
    [TestMethod]
    [DataRow(@"\textcolor{#ed3507}{\displaylines{x\\y+\textcolor{blue}{z}}}", @"\textcolor{#000000}{\displaylines{x\\y+\textcolor{blue}{z}}}")]
    [DataRow(@"\textcolor{red}{\textcolor{red}{x}}", @"\textcolor{#000000}{\textcolor{red}{x}}")]
    [DataRow(@"\textcolor[RGB]{255,0,0}{\mathbf{x}}", @"\textcolor{#000000}{\mathbf{x}}")]
    [DataRow(@"{\color{red}x}", @"\textcolor{#000000}{{x}}")]
    [DataRow(@"\textcolor{red}{x}+y", @"\textcolor{red}{x}+y")]
    public void FormattingResetsOnlyWholeFormulaColorEvenWhenTypographyAlreadyMatches(string source, string expected)
    {
        var metadata = CreateMetadata(source);
        var formatted = metadata.FormatWith(metadata.Typography);
        Assert.AreEqual(expected, formatted.Latex);
        Assert.AreSame(formatted, formatted.FormatWith(metadata.Typography));
        Assert.AreEqual(metadata.Identity, formatted.Identity);
        Assert.AreEqual(metadata.NumberText, formatted.NumberText);
    }

    [TestMethod]
    public void FormattingCopiesDefaultFontSizeAndColorAndPreservesLocalStyleAndComments()
    {
        var defaults = Create(symbol: "mathjax-stix2", size: 17.5, color: "#184FA0");
        var metadata = CreateMetadata(@"\textbf{x}+\textcolor{red}{y}% keep }");
        var formatted = metadata.FormatWith(defaults);
        Assert.AreEqual(defaults, formatted.Typography);
        Assert.AreEqual(@"\textcolor{#184FA0}{\textbf{x}+\textcolor{red}{y}% keep }" + "\n}", formatted.Latex);
        Assert.AreSame(formatted, formatted.FormatWith(defaults));
    }

    [TestMethod]
    public void FormattingMathMlResetsTheRootAndOuterStyleColor()
    {
        const string source = "<math xmlns='http://www.w3.org/1998/Math/MathML' color='#FF3300'><mstyle mathcolor='#ED3507' displaystyle='true'><mi>x</mi><mi mathcolor='#FF3300'>y</mi></mstyle></math>";
        var defaults = Create(color: "#184FA0");
        var formatted = CreateMetadata(source).FormatWith(defaults);
        var math = XElement.Parse(formatted.Latex);
        Assert.AreEqual("#184FA0", (string?)math.Attribute("mathcolor"));
        Assert.IsNull(math.Attribute("color"));
        var style = math.Elements().Single();
        Assert.AreEqual("true", (string?)style.Attribute("displaystyle"));
        Assert.IsNull(style.Attribute("mathcolor"));
        Assert.AreEqual("#FF3300", (string?)style.Elements().Last().Attribute("mathcolor"));
        Assert.AreSame(formatted, formatted.FormatWith(defaults));
    }

    private static FormulaMetadata CreateMetadata(string source) => new(new FormulaIdentity("test-doc", "test-equation"),
        source, FormulaDisplayMode.Display, NumberingMode.Manual, "3.1", RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion);

    [TestMethod]
    [DataRow("初号", 42d)]
    [DataRow("小初", 36d)]
    [DataRow("一号", 26d)]
    [DataRow("小一", 24d)]
    [DataRow("二号", 22d)]
    [DataRow("小二", 18d)]
    [DataRow("三号", 16d)]
    [DataRow("小三", 15d)]
    [DataRow("四号", 14d)]
    [DataRow("小四", 12d)]
    [DataRow("五号", 10.5d)]
    [DataRow("小五", 9d)]
    [DataRow("六号", 7.5d)]
    [DataRow("小六", 6.5d)]
    [DataRow("七号", 5.5d)]
    [DataRow("八号", 5d)]
    public void NamedSizeAndNumericInputProduceEqualSnapshots(string name, double expected)
    {
        double named = FormulaFontSize.Parse(name);
        Assert.AreEqual(expected, named);
        Assert.AreEqual(FormulaTypography.Default.WithFontSize(named), FormulaTypography.Default.WithFontSize(
            FormulaFontSize.Parse(expected.ToString(CultureInfo.InvariantCulture))));
    }

    [TestMethod]
    [DataRow(null)]
    [DataRow("")]
    [DataRow("NaN")]
    [DataRow("Infinity")]
    [DataRow("0")]
    [DataRow("-12")]
    [DataRow("1639")]
    [DataRow("100%")]
    [DataRow("12pt")]
    [DataRow("1,200")]
    [DataRow("1e2")]
    public void InvalidSizeInputDoesNotBecomeADefault(string? input)
    {
        Assert.IsFalse(FormulaFontSize.TryParse(input, out double size));
        Assert.AreEqual(0d, size);
        Assert.ThrowsExactly<FormatException>(() => FormulaFontSize.Parse(input!));
    }

    [TestMethod]
    public void SizeRulesAreCultureIndependentAndTheTableIsReadOnly()
    {
        CultureInfo original = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = new CultureInfo("de-DE");
            Assert.AreEqual(10.5, FormulaFontSize.Parse(" 10.5 "));
            Assert.AreEqual(12d, FormulaFontSize.Parse(" 小四 "));
            Assert.IsFalse(FormulaFontSize.TryParse("10,5", out _));
            Assert.AreEqual(1d, FormulaFontSize.Parse("1"));
            Assert.AreEqual(1638d, FormulaFontSize.Parse("1638"));
            var table = (IDictionary<string, double>)FormulaFontSize.NamedSizes;
            Assert.ThrowsExactly<NotSupportedException>(() => table["小四"] = 99);
        }
        finally { CultureInfo.CurrentCulture = original; }
    }

    [TestMethod]
    public void InvalidSnapshotFieldsAreRejected()
    {
        foreach (double size in new[] { double.NaN, double.PositiveInfinity, double.NegativeInfinity, 0, -1, 0.9, 9999999 })
            Assert.ThrowsExactly<ArgumentOutOfRangeException>(() => FormulaTypography.Default.WithFontSize(size));
        Assert.ThrowsExactly<ArgumentException>(() => Create(symbol: "TeX 数学字体"));
        Assert.ThrowsExactly<ArgumentException>(() => Create(symbol: "mathjax-tex\n"));
        Assert.ThrowsExactly<ArgumentException>(() => Create(cjk: " "));
        Assert.ThrowsExactly<ArgumentException>(() => Create(number: ""));
        Assert.ThrowsExactly<ArgumentException>(() => Create(number: "Arial\n"));
        Assert.ThrowsExactly<ArgumentException>(() => Create(color: "red"));
        Assert.ThrowsExactly<ArgumentException>(() => Create(color: "#00000000"));
        Assert.ThrowsExactly<ArgumentOutOfRangeException>(() => Create(style: (FormulaMathStyle)999));
    }

    [TestMethod]
    public void EveryStyleFieldParticipatesInSnapshotEquality()
    {
        FormulaTypography original = Create();
        foreach (FormulaTypography changed in new[] {
            Create(symbol: "mathjax-stix2"), Create(number: "Times New Roman"), Create(cjk: "SimSun"),
            Create(style: FormulaMathStyle.Bold), Create(size: 10.5), Create(color: "#112233") })
            Assert.AreNotEqual(original, changed);
        FormulaTypography normalized = Create(cjk: " microsoft yahei ", color: "#abcdef");
        FormulaTypography canonical = Create(color: "#ABCDEF");
        Assert.AreEqual(canonical, normalized);
        Assert.AreEqual(canonical.GetHashCode(), normalized.GetHashCode());
        Assert.AreEqual("#ABCDEF", normalized.Color);
        Assert.AreEqual(Create(number: "Times New Roman"), Create(number: " times new roman "));
    }

    [TestMethod]
    public void LocalStyleOverridesDefaultsWhileAutomaticPreservesNodeSemantics()
    {
        FormulaTypography bold = Create(style: FormulaMathStyle.Bold, color: "#0000FF");
        Assert.AreEqual(FormulaMathStyle.Bold, bold.ResolveMathStyle(FormulaMathStyle.Italic));
        Assert.AreEqual(FormulaMathStyle.Upright, bold.ResolveMathStyle(FormulaMathStyle.Italic, FormulaMathStyle.Upright));
        Assert.AreEqual(FormulaMathStyle.Italic, bold.ResolveMathStyle(FormulaMathStyle.Italic, FormulaMathStyle.Automatic));
        Assert.AreEqual(FormulaMathStyle.Italic, Create().ResolveMathStyle(FormulaMathStyle.Italic));
        Assert.AreEqual(FormulaMathStyle.Upright, Create().ResolveMathStyle(FormulaMathStyle.Upright));
        Assert.AreEqual("#FF0000", bold.ResolveColor("#ff0000"));
        Assert.AreEqual("#0000FF", bold.ResolveColor());
        Assert.ThrowsExactly<ArgumentException>(() => bold.ResolveMathStyle(FormulaMathStyle.Automatic));
        Assert.ThrowsExactly<ArgumentOutOfRangeException>(() => bold.ResolveMathStyle(FormulaMathStyle.Italic, (FormulaMathStyle)999));
    }

    [TestMethod]
    public void HostChangesOnlyAffectNewSnapshots()
    {
        FormulaTypography template = Create(number: "Times New Roman", cjk: "SimSun", color: "#123456");
        var defaults = new FormulaTypographyDefaults(template, followHostFontSize: true);
        FormulaTypographyResolution first = defaults.ResolveForNewFormula(10.5);
        FormulaTypographyResolution next = defaults.ResolveForNewFormula(24);
        Assert.AreEqual(10.5, first.Typography.FontSizePoints);
        Assert.AreEqual(24d, next.Typography.FontSizePoints);
        Assert.AreEqual(12d, template.FontSizePoints);
        Assert.AreEqual(template.WithFontSize(10.5), first.Typography);
        Assert.AreEqual(FormulaFontSizeSource.Host, first.FontSizeSource);
        Assert.AreNotEqual(first.Typography, next.Typography); // Submit can detect changed preview context.
        Assert.AreEqual(template, new FormulaTypographyDefaults(template, false).ResolveForNewFormula(99).Typography);
        Assert.AreEqual(FormulaFontSizeSource.Fixed,
            new FormulaTypographyDefaults(template, false).ResolveForNewFormula(null).FontSizeSource);
    }

    [TestMethod]
    public void AbsentMixedAndInvalidHostSizesHaveAnExplicitFallbackDiagnostic()
    {
        var defaults = new FormulaTypographyDefaults(Create(size: 15), true);
        foreach (double? host in new double?[] { null, 0, -1, double.NaN, double.PositiveInfinity, 9999999 })
        {
            FormulaTypographyResolution result = defaults.ResolveForNewFormula(host);
            Assert.AreEqual(15d, result.Typography.FontSizePoints);
            Assert.AreEqual(FormulaFontSizeSource.Fallback, result.FontSizeSource);
        }
        Assert.AreEqual(FormulaFontSizeSource.Host, defaults.ResolveForNewFormula(200).FontSizeSource);
    }

    private static FormulaTypography Create(string symbol = "mathjax-tex", string? number = null,
        string cjk = "Microsoft YaHei", FormulaMathStyle style = FormulaMathStyle.Automatic,
        double size = 12, string color = "#000000") => new FormulaTypography(symbol, number, cjk, style, size, color);
}
