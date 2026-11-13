using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordOleRoundTrip
{
    public static async Task VerifyAsync(object document, DynamicWordApplicationAdapter adapter,
        WordPluginController controller, IDictionary<string, string> sources)
    {
        var token = CancellationToken.None;
        var entries = await adapter.LoadFormulaEntriesAsync(true, token);
        var cases = new[] {
            entries.First(entry => entry.Metadata!.DisplayMode == FormulaDisplayMode.Inline),
            entries.First(entry => entry.Metadata!.NumberingMode == NumberingMode.Manual)
        };
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("WordOleRoundTrip"));
        foreach (var entry in cases)
        {
            FormulaMetadata original = entry.Metadata!;
            string id = original.Identity.EquationId;
            await SelectAsync(document, adapter, id);
            await controller.ConvertSelectedToOmmlAsync(token);
            await VerifyMetadataAsync(adapter, original, RenderEngineKind.Omml);
            await SelectAsync(document, adapter, id);
            await controller.ConvertSelectedToOleAsync(token);
            await VerifyMetadataAsync(adapter, original, RenderEngineKind.MathJaxSvg);
            await SelectAsync(document, adapter, id);
            dynamic wordDocument = document;
            wordDocument.Application.Selection.InlineShapes.Item(1).OLEFormat.Activate();
            var target = await adapter.LoadSelectedFormulaTargetAsync(token);
            E2EAssert.True(target.IsOle, "Loaded formula is not OLE");
            var edited = new FormulaMetadata(original.Identity, original.Latex + "+0", original.DisplayMode,
                original.NumberingMode, original.NumberText, RenderEngineKind.MathJaxSvg,
                FormulaMetadata.CurrentSchemaVersion, original.Typography);
            var rendered = await renderer.RenderAsync(new RenderRequest(edited.Latex, edited.DisplayMode,
                RenderEngineKind.MathJaxSvg, edited.Typography), token);
            var presentation = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                new OlePresentationRequest(rendered, OlePresentationKind.EnhancedMetafile), token);
            await adapter.UpdateOleFormulaObjectAsync(target, edited, presentation,
                edited.DisplayMode == FormulaDisplayMode.Display, token);
            sources[id] = edited.Latex;
            await VerifyMetadataAsync(adapter, edited, RenderEngineKind.MathJaxSvg);
        }
        Console.WriteLine("PASS|Word inline/numbered OMML-OLE conversion, activation and edit");
    }

    private static async Task SelectAsync(object document, DynamicWordApplicationAdapter adapter, string id)
    {
        var entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None))
            .Single(item => item.Metadata!.Identity.EquationId == id);
        ((dynamic)document).Application.Selection.SetRange(entry.Start, entry.Start + 1);
    }

    private static async Task VerifyMetadataAsync(DynamicWordApplicationAdapter adapter,
        FormulaMetadata expected, RenderEngineKind engine)
    {
        var actual = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None))
            .Single(entry => entry.Metadata!.Identity.EquationId == expected.Identity.EquationId).Metadata!;
        E2EAssert.Equal(expected.Latex, actual.Latex, "Conversion source");
        E2EAssert.Equal(expected.Typography, actual.Typography, "Conversion typography");
        E2EAssert.Equal(expected.DisplayMode, actual.DisplayMode, "Conversion display mode");
        E2EAssert.Equal(expected.NumberingMode, actual.NumberingMode, "Conversion numbering mode");
        E2EAssert.Equal(expected.NumberText, actual.NumberText, "Conversion number text");
        E2EAssert.Equal(expected.Identity.DocumentId, actual.Identity.DocumentId, "Conversion document identity");
        E2EAssert.Equal(engine, actual.RenderEngine, "Conversion backend");
    }
}
