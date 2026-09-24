using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.WordAddIn;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class TypographyPersistenceTests
{
    [TestMethod]
    public void OlePayloadPreservesCompleteStyleAndEscapedSource()
    {
        var style = new FormulaTypography("mathjax-stix2", "Times New Roman", "宋体", FormulaMathStyle.Upright, 10.5, "#ABCDEF");
        var metadata = new FormulaMetadata(new FormulaIdentity("doc", "eq"), "\\text{汉字 \"A\"}\n+x", FormulaDisplayMode.Display,
            NumberingMode.None, string.Empty, RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, style);
        var presentation = new OlePresentationResult(OlePresentationKind.EnhancedMetafile, "image/emf", new byte[] { 1, 2 }, 20, 10, 2, "4.1.3");
        var fields = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(OleFormulaPayloadJson.Serialize(metadata, presentation));
        Assert.AreEqual(style, FormulaTypographyFields.Read(fields));
        Assert.AreEqual(metadata.Latex, fields["latex"]);
        Assert.AreEqual(FormulaMetadata.CurrentSchemaVersion.ToString(), fields["schemaVersion"]);
        Assert.AreEqual("20", fields["widthPoints"]);
    }

    [TestMethod]
    public void WordRejectsMissingAndUnsupportedTypographyWithoutChangingStoredPayload()
    {
        var document = new FakeWordDocument();
        string id = WordDocumentIdentityStore.GetOrCreate(document);
        var metadata = new FormulaMetadata(new FormulaIdentity(id, "eq"), "x", FormulaDisplayMode.Inline,
            NumberingMode.None, string.Empty, RenderEngineKind.Omml, FormulaMetadata.CurrentSchemaVersion);
        var serializer = new JavaScriptSerializer();
        var fields = serializer.Deserialize<Dictionary<string, object>>(WordFormulaMetadataStore.Serialize(metadata));
        var style = (Dictionary<string, object>)fields["typography"];
        style["typographyVersion"] = 99;
        string unsupported = serializer.Serialize(fields);
        document.Variables.Add("LS.E.eq.unsupported", unsupported);
        Assert.ThrowsExactly<InvalidOperationException>(() => WordFormulaMetadataStore.Load(document, "latexsnipper-eq-eq|unsupported"));
        Assert.AreEqual(unsupported, document.Variables.Item("LS.E.eq.unsupported").Value);
        fields.Remove("typography");
        document.Variables.Add("LS.E.eq.missing", serializer.Serialize(fields));
        Assert.ThrowsExactly<InvalidOperationException>(() => WordFormulaMetadataStore.Load(document, "latexsnipper-eq-eq|missing"));
    }

    [TestMethod]
    public void PowerPointPreservesFontCaseThroughUppercaseTagsAndRejectsMissingStyleChunks()
    {
        var shape = new FakePowerPointShape();
        var style = new FormulaTypography("mathjax-tex", "Times New Roman", "微软雅黑", FormulaMathStyle.BoldItalic, 18.5, "#123ABC");
        var metadata = new FormulaMetadata(new FormulaIdentity("doc", "eq"), "x", FormulaDisplayMode.Display,
            NumberingMode.None, string.Empty, RenderEngineKind.Image, FormulaMetadata.CurrentSchemaVersion, style);
        PowerPointFormulaMetadataStore.ApplyToShape(shape, metadata, 30, 20);
        string chunk = shape.Tags["LaTeXSnipperTypography0000"];
        shape.Tags.Add("LaTeXSnipperTypography0000", chunk.ToUpperInvariant());
        var restored = PowerPointFormulaMetadataStore.LoadFromShape(shape).Typography;
        Assert.AreEqual("Times New Roman", restored.NumberFontFamily);
        Assert.AreEqual(style, restored);
        shape.Tags.Remove("LaTeXSnipperTypography0000");
        Assert.ThrowsExactly<InvalidOperationException>(() => PowerPointFormulaMetadataStore.LoadFromShape(shape));
    }
}
