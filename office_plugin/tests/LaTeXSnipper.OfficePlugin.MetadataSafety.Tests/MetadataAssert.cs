using Microsoft.VisualStudio.TestTools.UnitTesting;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

internal static class MetadataAssert
{
    public static void AreEqual(FormulaMetadata expected, FormulaMetadata actual)
    {
        Assert.AreEqual(expected.Identity.DocumentId, actual.Identity.DocumentId);
        Assert.AreEqual(expected.Identity.EquationId, actual.Identity.EquationId);
        Assert.AreEqual(expected.Latex, actual.Latex);
        Assert.AreEqual(expected.DisplayMode, actual.DisplayMode);
        Assert.AreEqual(expected.NumberingMode, actual.NumberingMode);
        Assert.AreEqual(expected.NumberText, actual.NumberText);
        Assert.AreEqual(expected.RenderEngine, actual.RenderEngine);
        Assert.AreEqual(expected.SchemaVersion, actual.SchemaVersion);
        Assert.AreEqual(expected.FontScale, actual.FontScale, 0.000001);
    }
}
