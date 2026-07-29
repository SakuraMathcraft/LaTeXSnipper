using System;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class PowerPointMetadataSafetyTests
{
    [TestMethod]
    public void Schema2RoundTripPreservesLongUnicodeMetadataAndNaturalSize()
    {
        var shape = new FakePowerPointShape();
        string latex = string.Concat(new string('数', 300), @"\frac{\partial f}{\partial x_i}");
        FormulaMetadata expected = CreateMetadata("presentation", "ppt-schema2", latex);

        PowerPointFormulaMetadataStore.ApplyToShape(shape, expected, 120, 40);
        FormulaMetadata actual =
            PowerPointFormulaMetadataStore.LoadFromShape(shape, "presentation");

        MetadataAssert.AreEqual(expected, actual);
        Assert.AreEqual("120", shape.Tags[PowerPointFormulaMetadataStore.NaturalWidthPointsTag]);
        Assert.AreEqual("40", shape.Tags[PowerPointFormulaMetadataStore.NaturalHeightPointsTag]);
        Assert.AreEqual(
            FormulaMetadata.CurrentSchemaVersion.ToString(),
            shape.Tags[PowerPointFormulaMetadataStore.SchemaVersionTag]);
    }

    [TestMethod]
    public void ApplyRejectsSchema1()
    {
        var shape = new FakePowerPointShape();
        FormulaMetadata legacy = CreateMetadata("presentation", "legacy-write", "x", schemaVersion: 1);

        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.ApplyToShape(shape, legacy, 100, 30));
    }

    [TestMethod]
    public void Schema1ReadCompatibilityUsesCurrentPresentationWithoutRewritingTags()
    {
        var shape = new FakePowerPointShape();
        shape.Tags.Add(PowerPointFormulaMetadataStore.EquationIdTag, "ppt-schema1");
        shape.Tags.Add(PowerPointFormulaMetadataStore.LatexByteLengthTag, "3");
        shape.Tags.Add(PowerPointFormulaMetadataStore.LatexChunkCountTag, "1");
        shape.Tags.Add("LaTeXSnipperLatex0000", "782B31");
        shape.Tags.Add(PowerPointFormulaMetadataStore.DisplayModeTag, "Display");
        shape.Tags.Add(PowerPointFormulaMetadataStore.SchemaVersionTag, "1");
        shape.Tags.Add(PowerPointFormulaMetadataStore.RenderEngineTag, "Image");
        shape.Tags.Add(PowerPointFormulaMetadataStore.FontScaleTag, "1");

        FormulaMetadata metadata =
            PowerPointFormulaMetadataStore.LoadFromShape(shape, "current-presentation");

        Assert.AreEqual("current-presentation", metadata.Identity.DocumentId);
        Assert.AreEqual("ppt-schema1", metadata.Identity.EquationId);
        Assert.AreEqual("x+1", metadata.Latex);
        Assert.AreEqual(FormulaMetadata.CurrentSchemaVersion, metadata.SchemaVersion);
        Assert.AreEqual("1", shape.Tags[PowerPointFormulaMetadataStore.SchemaVersionTag]);
        Assert.AreEqual(string.Empty, shape.Tags[PowerPointFormulaMetadataStore.DocumentIdTag]);
    }

    [TestMethod]
    public void Schema2CopiedToAnotherPresentationRetainsSourceIdentityForReconciliation()
    {
        var shape = new FakePowerPointShape();
        FormulaMetadata expected = CreateMetadata("source-presentation", "copied-equation", "x");
        PowerPointFormulaMetadataStore.ApplyToShape(shape, expected, 100, 30);

        FormulaMetadata copied =
            PowerPointFormulaMetadataStore.LoadFromShape(shape, "target-presentation");

        Assert.AreEqual("source-presentation", copied.Identity.DocumentId);
        Assert.AreNotEqual("target-presentation", copied.Identity.DocumentId);
    }

    [TestMethod]
    public void MissingCorruptAndUnknownMetadataFailClosed()
    {
        var missingChunk = new FakePowerPointShape();
        FormulaMetadata metadata = CreateMetadata("presentation", "missing-chunk", "x+1");
        PowerPointFormulaMetadataStore.ApplyToShape(missingChunk, metadata, 100, 30);
        missingChunk.Tags.Remove("LaTeXSnipperLatex0000");

        var unknownSchema = new FakePowerPointShape();
        PowerPointFormulaMetadataStore.ApplyToShape(unknownSchema, metadata, 100, 30);
        unknownSchema.Tags.Add(PowerPointFormulaMetadataStore.SchemaVersionTag, "99");

        var missingDocument = new FakePowerPointShape();
        PowerPointFormulaMetadataStore.ApplyToShape(missingDocument, metadata, 100, 30);
        missingDocument.Tags.Remove(PowerPointFormulaMetadataStore.DocumentIdTag);

        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.LoadFromShape(missingChunk, "presentation"));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.LoadFromShape(unknownSchema, "presentation"));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.LoadFromShape(missingDocument, "presentation"));
    }

    [TestMethod]
    public void PresentationIdentityIsStableForThePresentation()
    {
        var presentation = new FakePowerPointPresentation();

        string first = PowerPointDocumentIdentityStore.GetOrCreate(presentation);
        string second = PowerPointDocumentIdentityStore.GetOrCreate(presentation);

        Assert.AreEqual(first, second);
        Assert.IsFalse(string.IsNullOrWhiteSpace(first));
    }

    private static FormulaMetadata CreateMetadata(
        string documentId,
        string equationId,
        string latex,
        int schemaVersion = FormulaMetadata.CurrentSchemaVersion)
    {
        return new FormulaMetadata(
            new FormulaIdentity(documentId, equationId),
            latex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion,
            1.35);
    }
}
