using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordOleCopyRoundTrip
{
    public static async Task VerifyAsync(object application, object sourceDocument, string outputPath)
    {
        dynamic word = application;
        dynamic source = sourceDocument;
        dynamic? target = null;
        dynamic? copySource = null;
        var token = CancellationToken.None;
        var adapter = new DynamicWordApplicationAdapter(application);
        var typography = new FormulaTypography("mathjax-stix2", "Times New Roman", "宋体", FormulaMathStyle.BoldItalic, 15.5, "#123ABC");
        copySource = word.Documents.Add();
        var original = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            @"\textcolor{#123abc}{\frac{端+x}{\textcolor{red}{y}}}", FormulaDisplayMode.Inline,
            NumberingMode.None, "", RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, typography);
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("WordOleCopy"));
        var rendered = await renderer.RenderAsync(new RenderRequest(original.Latex, original.DisplayMode, original.RenderEngine, typography), token);
        var presentation = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
            new OlePresentationRequest(rendered, OlePresentationKind.EnhancedMetafile), token);
        Console.WriteLine("STAGE|Copy test inserting original OLE");
        await adapter.InsertOleFormulaObjectAsync(original, presentation, false, token);
        copySource.InlineShapes.Item(1).Range.Select();
        var before = await adapter.LoadSelectedFormulaTargetAsync(token);
        E2EAssert.Equal(original.Latex, before.Metadata.Latex, "Original OLE source");
        Console.WriteLine("STAGE|Original OLE loaded");
        copySource.InlineShapes.Item(1).Range.Copy();
        target = word.Documents.Add();
        try
        {
            target.Range(0, 0).Paste();
            target.InlineShapes.Item(1).Range.Select();
            var copied = await adapter.LoadSelectedFormulaTargetAsync(token);
            E2EAssert.Equal(original.Latex, copied.Metadata.Latex, "Cross-document source");
            E2EAssert.Equal(typography, copied.Metadata.Typography, "Cross-document typography");
            E2EAssert.True(copied.Metadata.Identity.DocumentId != original.Identity.DocumentId, "Copy retained source document identity");
            E2EAssert.True(copied.Metadata.Identity.EquationId != original.Identity.EquationId, "Copy retained source equation identity");
            target.InlineShapes.Item(1).Range.Copy();
            target.Range(Convert.ToInt32(target.Content.End) - 1, Convert.ToInt32(target.Content.End) - 1).Paste();
            target.InlineShapes.Item(2).Range.Select();
            var duplicate = await adapter.LoadSelectedFormulaTargetAsync(token);
            E2EAssert.True(duplicate.Metadata.Identity.EquationId != copied.Metadata.Identity.EquationId, "Same-document copy retained equation identity");
            copySource.Close(0);
            copySource = null;
            target.InlineShapes.Item(1).Range.Select();
            copied = await adapter.LoadSelectedFormulaTargetAsync(token);
            var edited = new FormulaMetadata(copied.Metadata.Identity, original.Latex + "+1", original.DisplayMode,
                original.NumberingMode, original.NumberText, original.RenderEngine,
                original.SchemaVersion, typography);
            var editRender = await renderer.RenderAsync(new RenderRequest(edited.Latex, edited.DisplayMode,
                edited.RenderEngine, typography), token);
            var editPresentation = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                new OlePresentationRequest(editRender, OlePresentationKind.EnhancedMetafile), token);
            // Saving uses the captured object even when another document is active.
            source.Activate();
            await adapter.UpdateOleFormulaObjectAsync(copied, edited, editPresentation, false, token);
            target.Activate();
            target.InlineShapes.Item(2).Range.Select();
            var untouched = await adapter.LoadSelectedFormulaTargetAsync(token);
            E2EAssert.Equal(original.Latex, untouched.Metadata.Latex, "Editing a copy changed its duplicate");
            string copiedPath = Path.Combine(Path.GetDirectoryName(outputPath)!, "word-ole-copy.docx");
            target.SaveAs2(copiedPath, 16);
            target.Close(0);
            target = word.Documents.Open(copiedPath);
            target.InlineShapes.Item(1).Range.Select();
            var reopened = await adapter.LoadSelectedFormulaTargetAsync(token);
            E2EAssert.Equal(edited.Latex, reopened.Metadata.Latex, "Reopened copied source");
            E2EAssert.Equal(typography, reopened.Metadata.Typography, "Reopened copied typography");
            Console.WriteLine("PASS|Word OLE copy survives source close, independent edit and fixed document target, save/reopen");
        }
        finally
        {
            if (target != null) target.Close(0);
            if (copySource != null) copySource.Close(0);
            source.Activate();
        }
    }
}
