using System;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class WordMetadataSafetyTests
{
    [TestMethod]
    public void Schema2RoundTripPreservesMetadataAndNaturalSize()
    {
        var document = new FakeWordDocument();
        string documentId = WordDocumentIdentityStore.GetOrCreate(document);
        FormulaMetadata expected = CreateMetadata(documentId, "word-schema2", @"\boldsymbol{x+y}");

        string tag = WordFormulaMetadataStore.Save(document, expected, 42.5, 18.25);
        FormulaMetadata actual = WordFormulaMetadataStore.Load(document, tag);

        MetadataAssert.AreEqual(expected, actual);
        Assert.IsTrue(WordFormulaMetadataStore.TryLoadOleNaturalSize(
            document,
            tag,
            out double width,
            out double height));
        Assert.AreEqual(42.5, width, 0.000001);
        Assert.AreEqual(18.25, height, 0.000001);
    }

    [TestMethod]
    public void SaveCreatesNewRevisionAndKeepsBothPayloadsReadable()
    {
        var document = new FakeWordDocument();
        string documentId = WordDocumentIdentityStore.GetOrCreate(document);
        FormulaMetadata first = CreateMetadata(documentId, "word-update", "x");
        FormulaMetadata second = CreateMetadata(documentId, "word-update", "x+1");

        string firstTag = WordFormulaMetadataStore.Save(document, first);
        string secondTag = WordFormulaMetadataStore.Save(document, second);

        Assert.AreNotEqual(firstTag, secondTag);
        MetadataAssert.AreEqual(first, WordFormulaMetadataStore.Load(document, firstTag));
        MetadataAssert.AreEqual(second, WordFormulaMetadataStore.Load(document, secondTag));
    }

    [TestMethod]
    public void SaveRejectsUnsupportedSchemaAndForeignDocumentIdentity()
    {
        var document = new FakeWordDocument();
        string documentId = WordDocumentIdentityStore.GetOrCreate(document);
        FormulaMetadata unsupported = CreateMetadata(documentId, "unsupported-write", "x", schemaVersion: 99);
        FormulaMetadata foreign = CreateMetadata("foreign-document", "foreign-write", "x");

        Assert.ThrowsExactly<InvalidOperationException>(
            () => WordFormulaMetadataStore.Save(document, unsupported));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => WordFormulaMetadataStore.Save(document, foreign));
    }

    [TestMethod]
    public void MissingCorruptAndMismatchedMetadataFailClosed()
    {
        var document = new FakeWordDocument();
        _ = WordDocumentIdentityStore.GetOrCreate(document);
        document.Variables.Add(
            "LS.E.unknown.badrevision",
            "{\"schemaVersion\":99,\"documentId\":\"doc\",\"equationId\":\"unknown\"," +
            "\"latex\":\"x\",\"displayMode\":\"Inline\",\"numberingMode\":\"None\"," +
            "\"numberText\":\"\",\"renderEngine\":\"Omml\",\"fontScale\":1}");
        document.Variables.Add(
            "LS.E.payload-equation.mismatch001",
            "{\"schemaVersion\":2,\"documentId\":\"doc\",\"equationId\":\"payload-equation\"," +
            "\"latex\":\"x\",\"displayMode\":\"Inline\",\"numberingMode\":\"None\"," +
            "\"numberText\":\"\",\"renderEngine\":\"Omml\",\"fontScale\":1}");

        Assert.ThrowsExactly<InvalidOperationException>(
            () => WordFormulaMetadataStore.Load(document, "latexsnipper-eq-missing|revision01"));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => WordFormulaMetadataStore.Load(document, "latexsnipper-eq-unknown|badrevision"));
        Assert.ThrowsExactly<InvalidOperationException>(
            () => WordFormulaMetadataStore.Load(document, "latexsnipper-eq-tag-equation|mismatch001"));
    }

    [TestMethod]
    public void DocumentIdentityIsStableForTheDocument()
    {
        var document = new FakeWordDocument();

        string first = WordDocumentIdentityStore.GetOrCreate(document);
        string second = WordDocumentIdentityStore.GetOrCreate(document);

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
            FormulaDisplayMode.Inline,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Omml,
            schemaVersion,
            1.25);
    }
}
