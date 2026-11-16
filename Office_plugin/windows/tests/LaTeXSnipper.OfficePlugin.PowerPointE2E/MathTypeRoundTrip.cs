using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using System.Windows.Forms;
using System.Diagnostics;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.Testing;

internal static class MathTypeRoundTrip
{
    public static async Task VerifyAsync(object application, object mainPresentation,
        PowerPointPluginController controller, MathJaxSvgRenderer renderer, string output, bool nativeEdit)
    {
        dynamic app = application, main = mainPresentation;
        dynamic presentation = app.Presentations.Add();
        presentation.Slides.Add(1, 12);
        using var adapter = new DynamicPowerPointApplicationAdapter(application);
        var originalMathTypeProcesses = Process.GetProcessesByName("MathType").Select(p => p.Id).ToArray();
        string clipboardText = "MathType conversion clipboard " + Guid.NewGuid().ToString("N");
        Clipboard.SetText(clipboardText);
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
            original.LockAspectRatio = 0;
            original.Width *= 1.2f;
            float width = original.Width, height = original.Height;
            var second = new FormulaMetadata(new FormulaIdentity(metadata.Identity.DocumentId, Guid.NewGuid().ToString("N")),
                @"\textcolor{#ff0000}{e^{i\pi}+1=0}", metadata.DisplayMode, metadata.NumberingMode, metadata.NumberText,
                metadata.RenderEngine, metadata.SchemaVersion, metadata.Typography.WithFontSize(24));
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
            Check(Clipboard.GetText() == clipboardText, "MathType conversion changed the clipboard");
            dynamic converted = presentation.Slides.Item(1).Shapes.Item(1);
            Check(Convert.ToInt32(presentation.Slides.Item(1).Shapes.Count) == 2, "MathType conversion duplicated the object");
            Check(Math.Abs(Convert.ToSingle(converted.Width) - width) < 0.1
                && Math.Abs(Convert.ToSingle(converted.Height) - height) < 0.1
                && Math.Abs(Convert.ToSingle(converted.Rotation)) < 0.1,
                "MathType conversion changed instance geometry: " + width + "x" + height + " -> " + converted.Width + "x" + converted.Height);
            await VerifyNativeAsync(adapter, (object)presentation, (object)converted, token);
            await VerifyNativeAsync(adapter, (object)presentation, (object)presentation.Slides.Item(1).Shapes.Item(2), token);
            string path = Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype.pptx");
            presentation.SaveAs(path, 24);
            presentation.Close();
            presentation = app.Presentations.Open(path, 0, 0, -1);
            await VerifyNativeAsync(adapter, (object)presentation, (object)presentation.Slides.Item(1).Shapes.Item(1), token);
            await VerifyNativeAsync(adapter, (object)presentation, (object)presentation.Slides.Item(1).Shapes.Item(2), token);
            presentation.SaveAs(Path.ChangeExtension(path, ".pdf"), 32);
            string changed = await renderer.ConvertTypographyToMathMlAsync(@"z^2+\text{新}", FormulaDisplayMode.Display, FormulaTypography.Default, token);
            if (nativeEdit)
            {
                presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.Activate();
                object server = presentation.Slides.Item(1).Shapes.Item(1).OLEFormat.Object;
                try { MathTypeNativeServer.WriteMathMl(server, changed); }
                finally { Marshal.ReleaseComObject(server); }
                Console.WriteLine("PASS|PowerPoint MathType native server opened and edited independently generated MTEF");
            }
            else
            {
                // Replace the persisted native payload to verify reading current content without a server.
                presentation.Close();
                ReplacePersistedNative(path, MathTypeCompoundFile.Create(MathTypeNativeEquation.Create(changed, FormulaTypography.Default.FontSizePoints)));
                presentation = app.Presentations.Open(path, 0, 0, -1);
            }
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
            Check(Math.Abs(edited.Metadata.Typography.FontSizePoints - FormulaTypography.Default.FontSizePoints) < 0.001, "Import lost the native font size");
            presentation.SaveAs(Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype-import.pptx"), 24);
            Console.WriteLine("PASS|PPT MathType to OLE: current edited content, mixed selection, first failure continues, worker thread");
            Console.WriteLine("PASS|PPT MathType native fraction/Chinese, geometry and save/reopen");
            await MathTypeLayoutRoundTrip.VerifyAsync(application, output);
            if (!nativeEdit)
            {
                Check(Process.GetProcessesByName("MathType").All(p => originalMathTypeProcesses.Contains(p.Id)), "Conversion activated the MathType server");
                Check(!Process.GetCurrentProcess().Modules.Cast<ProcessModule>().Any(m => m.ModuleName.Equals("MT6.dll", StringComparison.OrdinalIgnoreCase)),
                    "Conversion loaded the MathType SDK");
                Console.WriteLine("PASS|PowerPoint MathType conversion did not activate a server or load its SDK");
            }
        }
        finally
        {
            try { presentation.Saved = -1; presentation.Close(); }
            catch (COMException) { }
            main.Windows.Item(1).Activate();
        }
    }

    private static async Task VerifyNativeAsync(DynamicPowerPointApplicationAdapter adapter, object presentation, object shapeObject, CancellationToken token)
    {
        dynamic shape = shapeObject;
        Check(Convert.ToString(shape.OLEFormat.ProgID) == MathTypeOleBridge.ProgId, "MathType class identity");
        var content = await adapter.ReadMathTypeAsync(new MathTypeFormulaTarget(presentation, adapter.GetCurrentDocumentId(),
            Convert.ToInt32(shape.Id), Convert.ToInt32(shape.Parent.SlideIndex)), token);
        var xml = XDocument.Parse(content.MathMl);
        bool fraction = xml.Descendants().Any(e => e.Name.LocalName == "mfrac") && xml.Root!.Value.Contains("端");
        bool euler = xml.Descendants().Any(e => e.Name.LocalName == "msup") && xml.Root!.Value.Contains("e")
            && xml.Root.Value.Contains("π") && xml.Root.Value.Contains("1") && xml.Root.Value.Contains("0");
        Check(fraction || euler, "MathType lost fraction/Chinese or part of the Euler formula");
        Check(Math.Abs(content.FontSizePoints - (euler ? 24 : FormulaTypography.Default.FontSizePoints)) < 0.001,
            "MathType font size was not preserved");
        if (euler) Check(xml.Descendants().Attributes("mathcolor").Any(a => a.Value == "#ff0000"), "MathType lost the Euler color");
    }

    internal sealed class UnusedEditor : IFormulaEditor
    {
        public Task WarmUpAsync(CancellationToken token) => Task.CompletedTask;
        public Task OpenAsync(FormulaMetadata metadata, bool updateMode, long generation, CancellationToken token)
            => throw new InvalidOperationException("Conversion must not open the formula editor");
        public void Dispose() { }
    }

    private static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }

    private static void ReplacePersistedNative(string path, byte[] compoundFile)
    {
        using var zip = ZipFile.Open(path, ZipArchiveMode.Update);
        var slideEntry = zip.GetEntry("ppt/slides/slide1.xml")!;
        XDocument slide;
        using (var stream = slideEntry.Open()) slide = XDocument.Load(stream);
        XNamespace p = "http://schemas.openxmlformats.org/presentationml/2006/main";
        XNamespace r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
        string id = (string)slide.Descendants(p + "oleObj").First().Attribute(r + "id")!;
        XDocument relations;
        using (var stream = zip.GetEntry("ppt/slides/_rels/slide1.xml.rels")!.Open()) relations = XDocument.Load(stream);
        string target = (string)relations.Root!.Elements().Single(e => (string?)e.Attribute("Id") == id).Attribute("Target")!;
        string part = new Uri(new Uri("http://package/ppt/slides/slide1.xml"), target).AbsolutePath.TrimStart('/');
        zip.GetEntry(part)!.Delete();
        using var native = zip.CreateEntry(part).Open();
        native.Write(compoundFile, 0, compoundFile.Length);
    }
}
