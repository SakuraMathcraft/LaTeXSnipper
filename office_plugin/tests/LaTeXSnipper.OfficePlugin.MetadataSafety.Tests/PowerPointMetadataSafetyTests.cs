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
            PowerPointFormulaMetadataStore.LoadFromShape(shape);

        MetadataAssert.AreEqual(expected, actual);
        Assert.AreEqual("120", shape.Tags[PowerPointFormulaMetadataStore.NaturalWidthPointsTag]);
        Assert.AreEqual("40", shape.Tags[PowerPointFormulaMetadataStore.NaturalHeightPointsTag]);
        Assert.AreEqual(
            FormulaMetadata.CurrentSchemaVersion.ToString(),
            shape.Tags[PowerPointFormulaMetadataStore.SchemaVersionTag]);
    }

    [TestMethod]
    public void ApplyRejectsUnsupportedSchema()
    {
        var shape = new FakePowerPointShape();
        FormulaMetadata unsupported = CreateMetadata("presentation", "unsupported-write", "x", schemaVersion: 99);

        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.ApplyToShape(shape, unsupported, 100, 30));
    }

    [TestMethod]
    public void Schema2CopiedToAnotherPresentationRetainsSourceIdentityForReconciliation()
    {
        var shape = new FakePowerPointShape();
        FormulaMetadata expected = CreateMetadata("source-presentation", "copied-equation", "x");
        PowerPointFormulaMetadataStore.ApplyToShape(shape, expected, 100, 30);

        FormulaMetadata copied =
            PowerPointFormulaMetadataStore.LoadFromShape(shape);

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
            () => PowerPointFormulaMetadataStore.LoadFromShape(missingChunk));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.LoadFromShape(unknownSchema));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => PowerPointFormulaMetadataStore.LoadFromShape(missingDocument));
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
