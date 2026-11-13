using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class PowerPointOleCopyRoundTrip
{
    public static async Task VerifyAsync(object application, object presentation, object formula, string output, MathJaxSvgRenderer renderer)
    {
        dynamic app = application, main = presentation, original = formula;
        var token = CancellationToken.None;
        var adapter = new DynamicPowerPointApplicationAdapter(application);
        original.Select();
        var before = await adapter.LoadSelectedFormulaAsync(token);
        dynamic? source = null, target = null;
        try
        {
            original.Copy();
            source = app.Presentations.Add();
            source.Slides.Add(1, 12);
            dynamic copiedSource = source.Slides.Item(1).Shapes.Paste().Item(1);
            copiedSource.Select();
            var sourceTarget = await adapter.LoadSelectedFormulaAsync(token);
            copiedSource.Copy();
            target = app.Presentations.Add();
            target.Slides.Add(1, 12);
            dynamic first = target.Slides.Item(1).Shapes.Paste().Item(1);
            first.Select();
            var copied = await adapter.LoadSelectedFormulaAsync(token);
            Check(copied.Metadata.Latex == before.Metadata.Latex && copied.Metadata.Typography.Equals(before.Metadata.Typography), "Cross-presentation content changed");
            Check(copied.Metadata.Identity.DocumentId != sourceTarget.Metadata.Identity.DocumentId
                && copied.Metadata.Identity.EquationId != sourceTarget.Metadata.Identity.EquationId, "Cross-presentation identity was retained");
            first.Copy();
            dynamic second = target.Slides.Item(1).Shapes.Paste().Item(1);
            second.Select();
            var duplicate = await adapter.LoadSelectedFormulaAsync(token);
            Check(duplicate.Metadata.Identity.EquationId != copied.Metadata.Identity.EquationId, "Duplicate identity was retained");
            source.Saved = -1;
            source.Close();
            source = null;
            first.Select();
            copied = await adapter.LoadSelectedFormulaAsync(token);
            var edited = new FormulaMetadata(copied.Metadata.Identity, copied.Metadata.Latex + "+3", copied.Metadata.DisplayMode,
                copied.Metadata.NumberingMode, copied.Metadata.NumberText, copied.Metadata.RenderEngine,
                copied.Metadata.SchemaVersion, copied.Metadata.Typography);
            var svg = await renderer.RenderAsync(new RenderRequest(edited.Latex, edited.DisplayMode, edited.RenderEngine, edited.Typography), token);
            var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
            main.Windows.Item(1).Activate();
            await adapter.UpdateOleFormulaObjectAsync(copied, edited, emf, token);
            target.Windows.Item(1).Activate();
            second.Select();
            Check((await adapter.LoadSelectedFormulaAsync(token)).Metadata.Latex == before.Metadata.Latex, "Editing a copy changed its duplicate");
            string path = Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-ole-copy.pptx");
            target.SaveAs(path, 24);
            target.Close();
            target = app.Presentations.Open(path, 0, 0, -1);
            var entries = await adapter.LoadFormulaEntriesAsync(true, token);
            Check(entries.Count == 2, "Copied formulas were lost after reopening");
            Check(System.Linq.Enumerable.Any(entries, e => e.Metadata.Latex == edited.Latex && e.Metadata.Typography.Equals(edited.Typography)), "Copied edit did not persist");
            Console.WriteLine("PASS|PPT OLE cross-presentation/duplicate copies, source close, fixed target edit, save/reopen");
        }
        finally
        {
            if (source != null) { source.Saved = -1; source.Close(); }
            if (target != null) { target.Saved = -1; target.Close(); }
            main.Windows.Item(1).Activate();
        }
    }

    private static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
}
