using System;
using System.IO;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class EditorTypographyTests
{
    [TestMethod]
    public void AcceptedStyleIsAnIndependentSnapshotAndKeepsFormulaIdentity()
    {
        var original = new FormulaMetadata(new FormulaIdentity("doc", "eq"), "x", FormulaDisplayMode.Inline,
            NumberingMode.None, "", RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion);
        FormulaTypography draft = FormulaTypography.Default.WithFontSize(18);
        var accepted = new FormulaEditorAcceptedEventArgs(original, true, "y", false, 2, draft);
        FormulaMetadata updated = original.WithTypography(accepted.Typography);
        Assert.AreSame(draft, accepted.Typography);
        Assert.AreEqual(12d, original.Typography.FontSizePoints);
        Assert.AreEqual(18d, updated.Typography.FontSizePoints);
        Assert.AreSame(original.Identity, updated.Identity);
        Assert.AreEqual(original.DisplayMode, updated.DisplayMode);
        Assert.AreEqual(original.SchemaVersion, updated.SchemaVersion);
    }

    [TestMethod]
    public void SymbolFontsAreReadFromThePackagedConfiguration()
    {
        string root = Path.Combine(Path.GetTempPath(), "office-font-catalog-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, "startup.js"), "");
            File.WriteAllText(Path.Combine(root, "config.js"),
                "globalThis.LaTeXSnipperMathJaxConfig = {\"fonts\":[\"test-font-a\",\"test-font-b\"]};");
            CollectionAssert.AreEqual(new[] { "test-font-a", "test-font-b" },
                new System.Collections.Generic.List<string>(new MathJaxAssetResolver(root).SymbolFonts));
        }
        finally { Directory.Delete(root, true); }
    }
}
