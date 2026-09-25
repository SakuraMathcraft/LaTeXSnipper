using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class PowerPointRoundTrip
{
    private static readonly CancellationToken Token = CancellationToken.None;

    public static async Task RunAsync(string output, bool includeOle)
    {
        if (Process.GetProcessesByName("POWERPNT").Length != 0)
            throw new InvalidOperationException("Close PowerPoint before running this isolated test.");
        if (File.Exists(output)) throw new IOException("Output already exists: " + output);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        string imagePath = Path.Combine(Path.GetTempPath(), "latexsnipper-ppt-" + Guid.NewGuid().ToString("N") + ".png");
        dynamic app = Activator.CreateInstance(Type.GetTypeFromProgID("PowerPoint.Application")!);
        dynamic? presentation = null;
        try
        {
            app.Visible = -1;
            presentation = app.Presentations.Add();
            presentation.Slides.Add(1, 12);
            presentation.Slides.Add(2, 12);
            var adapter = new DynamicPowerPointApplicationAdapter(app);
            using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointE2E"));
            using var controller = new PowerPointPluginController(new FormulaEditorSession(new UnusedEditor()),
                new AutomationApiClient(new AutomationApiOptions()), adapter, renderer,
                new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() }));
            var style = new FormulaTypography("mathjax-stix2", "Times New Roman", "SimSun",
                FormulaMathStyle.BoldItalic, 15.5, "#123ABC");
            string[] sources = { @"\mathrm{\delta}+\text{条件概率 }P(A\mid B)",
                @"\begin{align}x&=12\\y&=\frac{1}{2}\end{align}" };
            var originals = new Dictionary<string, string>();
            for (int index = 0; index < sources.Length; index++)
            {
                var metadata = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
                    sources[index], FormulaDisplayMode.Display, NumberingMode.None, "", RenderEngineKind.Image,
                    FormulaMetadata.CurrentSchemaVersion, style);
                PowerPointRenderedImage image = await RenderAsync(renderer, metadata, imagePath);
                await adapter.InsertFormulaImageOnSlideAsync(index + 1, image, metadata, 80, 90, 1.5f, Token);
                originals.Add(metadata.Identity.EquationId, metadata.Latex);
            }
            await VerifyAsync(adapter, style, originals, 1.5f);
            presentation.Windows.Item(1).View.GotoSlide(1);
            presentation.Slides.Item(1).Shapes.Item(1).Select();
            var target = await adapter.LoadSelectedFormulaAsync(Token);
            var edited = new FormulaMetadata(target.Metadata.Identity, target.Metadata.Latex + "+1",
                FormulaDisplayMode.Display, NumberingMode.None, "", RenderEngineKind.Image,
                FormulaMetadata.CurrentSchemaVersion, style);
            await adapter.UpdateFormulaImageAsync(target, await RenderAsync(renderer, edited, imagePath), edited, Token);
            originals[edited.Identity.EquationId] = edited.Latex;
            await VerifyAsync(adapter, style, originals, 1.5f);
            Console.WriteLine("PASS|PPT insert, selection, edit, scale and full typography");

            if (includeOle)
            {
                await ConvertSlidesAsync((object)presentation, controller, toOle: true);
                await VerifyAsync(adapter, style, originals, 1.5f, RenderEngineKind.MathJaxSvg);
                presentation.Windows.Item(1).View.GotoSlide(1);
                presentation.Slides.Item(1).Shapes.Item(1).Select();
                presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.DoVerb(0);
                var oleTarget = await adapter.LoadSelectedFormulaAsync(Token);
                var oleEdit = new FormulaMetadata(oleTarget.Metadata.Identity, oleTarget.Metadata.Latex + "+2",
                    FormulaDisplayMode.Display, NumberingMode.None, "", RenderEngineKind.MathJaxSvg,
                    FormulaMetadata.CurrentSchemaVersion, style);
                var vector = await renderer.RenderAsync(new RenderRequest(oleEdit.Latex, oleEdit.DisplayMode,
                    RenderEngineKind.MathJaxSvg, style), Token);
                var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                    new OlePresentationRequest(vector, OlePresentationKind.EnhancedMetafile), Token);
                await adapter.UpdateOleFormulaObjectAsync(oleTarget, oleEdit, emf, Token);
                originals[oleEdit.Identity.EquationId] = oleEdit.Latex;
                string olePath = Path.Combine(Path.GetDirectoryName(output)!, Path.GetFileNameWithoutExtension(output) + "-ole.pptx");
                if (File.Exists(olePath)) throw new IOException("Output already exists: " + olePath);
                presentation.SaveAs(olePath, 24);
                presentation.Close();
                presentation = app.Presentations.Open(olePath, 0, 0, -1);
                await VerifyAsync(adapter, style, originals, 1.5f, RenderEngineKind.MathJaxSvg);
                presentation.Windows.Item(1).View.GotoSlide(1);
                presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.DoVerb(0);
                await ConvertSlidesAsync((object)presentation, controller, toOle: false);
                await VerifyAsync(adapter, style, originals, 1.5f);
                Console.WriteLine("PASS|PPT PNG/OLE conversion, activation, edit, save and reopen");
            }

            FormulaTypography defaults = PowerPointPluginSettings.Load().Typography;
            await controller.FormatAllAsync(Token);
            await VerifyAsync(adapter, defaults, originals, 1);
            await controller.FormatAllAsync(Token);
            await VerifyAsync(adapter, defaults, originals, 1);
            presentation.SaveAs(output, 24);
            presentation.Close();
            presentation = app.Presentations.Open(output, 0, 0, -1);
            await VerifyAsync(adapter, defaults, originals, 1);
            Check(Convert.ToInt32(presentation.Slides.Count) == 2, "Slide count changed");
            Console.WriteLine("PASS|PPT repeated format, save and reopen|" + output);
        }
        finally
        {
            if (presentation != null) { presentation.Saved = -1; presentation.Close(); }
            app.Quit();
            if (File.Exists(imagePath)) File.Delete(imagePath);
        }
    }

    private static async Task<PowerPointRenderedImage> RenderAsync(MathJaxSvgRenderer renderer, FormulaMetadata metadata, string path)
    {
        RenderResult result = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode,
            RenderEngineKind.MathJaxSvg, metadata.Typography), Token);
        File.WriteAllBytes(path, SvgPngRasterizer.Rasterize(result, Token));
        return new PowerPointRenderedImage(path, (float)result.WidthPoints, (float)result.HeightPoints);
    }

    private static async Task VerifyAsync(DynamicPowerPointApplicationAdapter adapter, FormulaTypography typography,
        IReadOnlyDictionary<string, string> sources, float scale, RenderEngineKind engine = RenderEngineKind.Image)
    {
        var entries = await adapter.LoadFormulaEntriesAsync(true, Token);
        Check(entries.Count == sources.Count, "Formula count changed");
        Check(entries.Select(entry => entry.SlideIndex).Distinct().Count() == 2, "Formula moved between slides");
        foreach (var entry in entries)
        {
            Check(entry.Metadata.Typography.Equals(typography), "Typography snapshot changed");
            Check(entry.Metadata.Latex == sources[entry.Metadata.Identity.EquationId], "Source or identity changed");
            Check(entry.Metadata.RenderEngine == engine, "Unexpected formula backend");
            Check(Math.Abs(entry.Scale - scale) < .01, "User scale changed");
            Check(Math.Abs(entry.Left - 80) < .01 && Math.Abs(entry.Top - 90) < .01, "Position changed");
        }
    }

    private static async Task ConvertSlidesAsync(object document, PowerPointPluginController controller, bool toOle)
    {
        dynamic presentation = document;
        for (int index = 1; index <= Convert.ToInt32(presentation.Slides.Count); index++)
        {
            presentation.Windows.Item(1).View.GotoSlide(index);
            presentation.Slides.Item(index).Shapes.Item(1).Select();
            if (toOle) await controller.ConvertSelectedToOleAsync(Token);
            else await controller.ConvertSelectedToPngAsync(Token);
        }
    }

    private static void Check(bool value, string message)
    {
        if (!value) throw new InvalidOperationException(message);
    }

    private sealed class UnusedEditor : IFormulaEditor
    {
        public Task WarmUpAsync(CancellationToken token) => Task.CompletedTask;
        public Task OpenAsync(FormulaMetadata metadata, bool updateMode, long generation, CancellationToken token)
            => throw new InvalidOperationException("Document commands must not open the formula editor.");
        public void Dispose() { }
    }
}
