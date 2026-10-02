using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathTypeRoundTrip
{
    public static async Task VerifyAsync(object application, object mainPresentation,
        PowerPointPluginController controller, MathJaxSvgRenderer renderer, string output)
    {
        dynamic app = application, main = mainPresentation;
        dynamic presentation = app.Presentations.Add();
        presentation.Slides.Add(1, 12);
        var adapter = new DynamicPowerPointApplicationAdapter(application);
        var token = CancellationToken.None;
        try
        {
            var metadata = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
                @"\frac{x}{y}+\text{端}", FormulaDisplayMode.Display, NumberingMode.None, "", RenderEngineKind.MathJaxSvg,
                FormulaMetadata.CurrentSchemaVersion, FormulaTypography.Default);
            var svg = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode, metadata.RenderEngine, metadata.Typography), token);
            var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
            await adapter.InsertOleFormulaObjectOnSlideAsync(1, metadata, emf, 80, 90, 1.5f, token);
            dynamic original = presentation.Slides.Item(1).Shapes.Item(1);
            float width = original.Width, height = original.Height;
            var second = new FormulaMetadata(new FormulaIdentity(metadata.Identity.DocumentId, Guid.NewGuid().ToString("N")),
                @"\textcolor{#ff0000}{e^{i\pi}+1=0}", metadata.DisplayMode, metadata.NumberingMode, metadata.NumberText,
                metadata.RenderEngine, metadata.SchemaVersion, metadata.Typography);
            var secondSvg = await renderer.RenderAsync(new RenderRequest(second.Latex, second.DisplayMode, second.RenderEngine, second.Typography), token);
            var secondEmf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(new OlePresentationRequest(secondSvg, OlePresentationKind.EnhancedMetafile), token);
            await adapter.InsertOleFormulaObjectOnSlideAsync(1, second, secondEmf, 80, 180, 1.5f, token);
            presentation.Slides.Item(1).Shapes.Range().Select();
            var status = new BatchStatusSink();
            using (var failing = new PowerPointPluginController(new FormulaEditorSession(new UnusedEditor()),
                new AutomationApiClient(new AutomationApiOptions()),
                FailingPowerPointAdapter.Wrap(adapter, metadata.Identity.EquationId),
                new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointMathTypeE2E")),
                new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() }), status))
            {
                await Task.Run(() => failing.ConvertSelectedToMathTypeAsync(token));
            }
            Check(status.Message.Contains("Injected MathType conversion failure"), "MathType batch did not report failure");
            Check((await adapter.LoadFormulaEntriesAsync(true, token)).Count == 1, "MathType batch stopped after first failure");
            original.Select();
            await Task.Run(() => controller.ConvertSelectedToMathTypeAsync(token));
            dynamic converted = presentation.Slides.Item(1).Shapes.Item(2);
            Check(Convert.ToInt32(presentation.Slides.Item(1).Shapes.Count) == 2, "MathType conversion duplicated the object");
            Check(Math.Abs(Convert.ToSingle(converted.Width) - width) < 0.1
                && Math.Abs(Convert.ToSingle(converted.Height) - height) < 0.1
                && Math.Abs(Convert.ToSingle(converted.Rotation)) < 0.1,
                "MathType conversion changed instance geometry: " + width + "x" + height + " -> " + converted.Width + "x" + converted.Height);
            VerifyNative(converted);
            VerifyNative(presentation.Slides.Item(1).Shapes.Item(1));
            string path = Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype.pptx");
            presentation.SaveAs(path, 24);
            presentation.Close();
            presentation = app.Presentations.Open(path, 0, 0, -1);
            VerifyNative(presentation.Slides.Item(1).Shapes.Item(1));
            VerifyNative(presentation.Slides.Item(1).Shapes.Item(2));
            presentation.SaveAs(Path.ChangeExtension(path, ".pdf"), 32);
            string changed = await renderer.ConvertTypographyToMathMlAsync(@"z^2+\text{新}", FormulaDisplayMode.Display, FormulaTypography.Default, token);
            presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.Activate();
            object server = presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.Object;
            try { MathTypeOleBridge.WriteMathMl(server, changed); }
            finally { Marshal.ReleaseComObject(server); }
            presentation.Slides.Item(1).Shapes.Range().Select();
            string failedShapeId = Convert.ToInt32(presentation.Slides.Item(1).Shapes.Item(1).Id).ToString();
            status = new BatchStatusSink();
            using (var failing = new PowerPointPluginController(new FormulaEditorSession(new UnusedEditor()),
                new AutomationApiClient(new AutomationApiOptions()), FailingPowerPointAdapter.Wrap(adapter, failedShapeId),
                new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointMathTypeImportE2E")),
                new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() }), status))
                await Task.Run(() => failing.ConvertSelectedToOleAsync(token));
            Check(status.Message.Contains("Injected MathType import failure"), "MathType import did not report concrete failure");
            Check((await adapter.LoadFormulaEntriesAsync(true, token)).Count == 1, "MathType import stopped after first failure");
            presentation.Slides.Item(1).Shapes.Range().Select();
            await Task.Run(() => controller.ConvertSelectedToOleAsync(token));
            var imported = await adapter.LoadFormulaEntriesAsync(true, token);
            Check(imported.Count == 2, "Mixed OLE/MathType import did not finish");
            var edited = imported.Single(e => XDocument.Parse(e.Metadata.Latex).Root!.Value.Contains("新"));
            Check(XDocument.Parse(edited.Metadata.Latex).Root!.Value.Contains("z"), "Import restored stale content instead of MathType edit");
            presentation.SaveAs(Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype-import.pptx"), 24);
            Console.WriteLine("PASS|PPT MathType to OLE: current edited content, mixed selection, first failure continues, worker thread");
            Console.WriteLine("PASS|PPT MathType native fraction/Chinese, geometry and save/reopen");
        }
        finally
        {
            presentation.Saved = -1;
            presentation.Close();
            main.Windows.Item(1).Activate();
        }
    }

    private static void VerifyNative(dynamic shape)
    {
        Check(Convert.ToString(shape.OLEFormat.ProgID) == MathTypeOleBridge.ProgId, "MathType class identity");
        shape.OLEFormat.Activate();
        object server = shape.OLEFormat.Object;
        string mathMl;
        try
        {
            mathMl = MathTypeOleBridge.ReadAndCloseMathMl(server);
        }
        finally { Marshal.ReleaseComObject(server); }
        var xml = XDocument.Parse(mathMl);
        bool fraction = xml.Descendants().Any(e => e.Name.LocalName == "mfrac") && xml.Root!.Value.Contains("端");
        bool euler = xml.Descendants().Any(e => e.Name.LocalName == "msup") && xml.Root!.Value.Contains("e")
            && xml.Root.Value.Contains("π") && xml.Root.Value.Contains("1") && xml.Root.Value.Contains("0");
        Check(fraction || euler, "MathType lost fraction/Chinese or part of the Euler formula");
    }

    private sealed class UnusedEditor : IFormulaEditor
    {
        public Task WarmUpAsync(CancellationToken token) => Task.CompletedTask;
        public Task OpenAsync(FormulaMetadata metadata, bool updateMode, long generation, CancellationToken token)
            => throw new InvalidOperationException("Conversion must not open the formula editor");
        public void Dispose() { }
    }

    private static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
}
