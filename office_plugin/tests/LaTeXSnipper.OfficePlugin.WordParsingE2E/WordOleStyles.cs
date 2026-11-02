using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordOleStyles
{
    public static async Task VerifyAsync(object application, string outputPath)
    {
        dynamic word = application;
        dynamic? document = word.Documents.Add();
        using var adapter = new DynamicWordApplicationAdapter(application);
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("WordOleStyles"));
        var expected = new List<FormulaMetadata>();
        var token = CancellationToken.None;
        try
        {
            foreach (string font in new[] { "mathjax-tex", "mathjax-stix2" })
            foreach (FormulaMathStyle style in Enum.GetValues(typeof(FormulaMathStyle)))
            {
                var typography = new FormulaTypography(font, "Times New Roman", "SimSun", style, 12, "#000000");
                var metadata = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
                    @"\lim_{n\to\infty}a_n=L", FormulaDisplayMode.Inline, NumberingMode.None, "",
                    RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, typography);
                word.Selection.EndKey(6);
                int start = Convert.ToInt32(word.Selection.Start);
                word.Selection.TypeText("prefix suffix\r");
                document.Range(start, start + 6).Font.Superscript = -1;
                document.Range(start + 7, start + 13).Font.Subscript = -1;
                int position = start + 7;
                word.Selection.SetRange(position, position);
                var svg = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode,
                    metadata.RenderEngine, typography), token);
                var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                    new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
                await adapter.InsertOleFormulaObjectAsync(metadata, emf, false, token);
                VerifySurroundingText(document, start, expected.Count + 1);
                document.InlineShapes.Item(expected.Count + 1).Range.Select();
                var target = await adapter.LoadSelectedFormulaTargetAsync(token);
                E2EAssert.Equal(typography, target.Metadata.Typography, "Inserted OLE style");
                metadata = new FormulaMetadata(metadata.Identity, @"e^{i\pi}+1=0", metadata.DisplayMode,
                    metadata.NumberingMode, "", metadata.RenderEngine, metadata.SchemaVersion, typography);
                svg = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode,
                    metadata.RenderEngine, typography), token);
                emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                    new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
                await adapter.UpdateOleFormulaObjectAsync(target, metadata, emf, false, token);
                VerifySurroundingText(document, start, expected.Count + 1);
                expected.Add(metadata);
                Console.WriteLine($"PASS|Word OLE insert/update|{font}|{style}");
            }
            string path = Path.Combine(Path.GetDirectoryName(outputPath)!, "word-ole-styles.docx");
            document.SaveAs2(path, 16);
            document.Close(0);
            document = null;
            document = word.Documents.Open(path);
            E2EAssert.Equal(expected.Count, Convert.ToInt32(document.InlineShapes.Count), "Reopened OLE count");
            for (int index = 0; index < expected.Count; index++)
            {
                document.InlineShapes.Item(index + 1).Range.Select();
                var actual = await adapter.LoadSelectedFormulaTargetAsync(token);
                E2EAssert.Equal(expected[index].Typography, actual.Metadata.Typography, "Reopened OLE style");
                E2EAssert.Equal(expected[index].Latex, actual.Metadata.Latex, "Reopened OLE source");
            }
            Console.WriteLine("PASS|Word all mathematical styles survive insert, update and save/reopen");
            document.Range(0, 6).Select();
            await adapter.ActivateForEditingAsync(token);
            VerifySurroundingText(document, 0, 1);
            Console.WriteLine("PASS|Restoring focus preserves selected text formatting");
        }
        finally { if (document != null) document.Close(0); }
    }

    private static void VerifySurroundingText(dynamic document, int start, int shapeIndex)
    {
        E2EAssert.Equal(-1, Convert.ToInt32(document.Range(start, start + 6).Font.Superscript),
            "OLE operation changed preceding superscript");
        int suffixStart = Convert.ToInt32(document.InlineShapes.Item(shapeIndex).Range.End);
        E2EAssert.Equal("suffix", Convert.ToString(document.Range(suffixStart, suffixStart + 6).Text), "Following text");
        E2EAssert.Equal(-1, Convert.ToInt32(document.Range(suffixStart, suffixStart + 6).Font.Subscript),
            "OLE operation changed following subscript");
    }
}
