using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathTypeLayoutRoundTrip
{
    public static async Task VerifyAsync(object application, string output)
    {
        dynamic app = application, previous = app.ActivePresentation;
        dynamic? source = app.Presentations.Add(), copied = null;
        using var adapter = new DynamicPowerPointApplicationAdapter(application);
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointMathTypeLayoutE2E"));
        var status = new BatchStatusSink();
        using var controller = new PowerPointPluginController(new FormulaEditorSession(new MathTypeRoundTrip.UnusedEditor()),
            new AutomationApiClient(new AutomationApiOptions()), adapter, renderer,
            new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() }), status);
        var token = CancellationToken.None;
        try
        {
            dynamic slide = source.Slides.Add(1, 12);
            slide.Shapes.AddTextbox(1, 40, 30, 500, 30).TextFrame.TextRange.Text = "MathType conversion";
            string[] formulas = { @"\frac{x}{y}+\text{端}", @"\sqrt{x^2+1}",
                @"\begin{pmatrix}a&b\\c&d\end{pmatrix}", @"\begin{cases}x&x>0\\-x&x<0\end{cases}",
                @"\begin{aligned}x&=12\\y&=\frac{1}{2}\end{aligned}", @"\frac{x}{y}+\text{端}" };
            var geometry = new List<(float Left, float Top, float Width, float Height)>();
            var content = new List<string>();
            for (int index = 0; index < formulas.Length; index++)
            {
                var typography = FormulaTypography.Default.WithFontSize(16 + index);
                var metadata = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
                    formulas[index], FormulaDisplayMode.Display, NumberingMode.None, "", RenderEngineKind.MathJaxSvg,
                    FormulaMetadata.CurrentSchemaVersion, typography);
                var svg = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode, metadata.RenderEngine, typography), token);
                var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
                await adapter.InsertOleFormulaObjectOnSlideAsync(1, metadata, emf, 80 + index % 2 * 350, 100 + index / 2 * 120, 1.2f, token);
                dynamic shape = slide.Shapes.Item(index + 2);
                geometry.Add((Convert.ToSingle(shape.Left), Convert.ToSingle(shape.Top), Convert.ToSingle(shape.Width), Convert.ToSingle(shape.Height)));
                string mathMl = await renderer.ConvertTypographyToMathMlAsync(metadata.Latex, metadata.DisplayMode, typography, token);
                content.Add(MathTypeNativeEquation.ReadMathMl(MathTypeNativeEquation.Create(mathMl, typography.FontSizePoints)));
            }
            slide.Shapes.AddTextbox(1, 40, 490, 500, 30).TextFrame.TextRange.Text = "After formulas";
            slide.Shapes.Range().Select();
            using (var cancellation = new CancellationTokenSource())
            {
                status.CancelAfterNextBatch(cancellation);
                bool cancelled = false;
                try { await Task.Run(() => controller.ConvertSelectedToMathTypeAsync(cancellation.Token)); }
                catch (OperationCanceledException) { cancelled = true; }
                Check(cancelled, "MathType batch cancellation was not propagated");
            }
            Check((await adapter.LoadFormulaEntriesAsync(true, token)).Count == 1, "Cancellation changed an unprocessed formula");
            Check(Convert.ToInt32(slide.Shapes.Count) == 8, "Cancellation left duplicate shapes");
            slide.Shapes.Range().Select();
            await Task.Run(() => controller.ConvertSelectedToMathTypeAsync(token));
            for (int index = 0; index < formulas.Length; index++)
            {
                dynamic shape = slide.Shapes.Item(index + 2);
                Check(MathTypeOleBridge.IsEquation((object)shape), "Conversion changed the original layer order");
                VerifyGeometry((object)shape, geometry[index]);
            }
            source.SaveAs(Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype-layout.pdf"), 32);
            slide.Shapes.Range().Copy();
            copied = app.Presentations.Add();
            copied.Slides.Add(1, 12);
            dynamic targetSlide = copied.Slides.Add(2, 12);
            targetSlide.Shapes.Paste();
            source.Saved = -1;
            source.Close();
            source = null;
            copied.Windows.Item(1).View.GotoSlide(2);
            copied.Saved = -1;
            for (int index = 0; index < formulas.Length; index++)
            {
                dynamic shape = targetSlide.Shapes.Item(index + 2);
                var native = await adapter.ReadMathTypeAsync(new MathTypeFormulaTarget((object)copied, adapter.GetCurrentDocumentId(),
                    Convert.ToInt32(shape.Id), 2), token);
                Check(native.MathMl == content[index] && Math.Abs(native.FontSizePoints - (16 + index)) < 0.001,
                    "Copied MathType content changed after the source closed");
                geometry[index] = (Convert.ToSingle(shape.Left), Convert.ToSingle(shape.Top), Convert.ToSingle(shape.Width), Convert.ToSingle(shape.Height));
            }
            Check(Convert.ToInt32(copied.Saved) == -1, "Reading MathType content changed the document saved state");
            targetSlide.Shapes.Range().Select();
            await Task.Run(() => controller.ConvertSelectedToOleAsync(token));
            for (int index = 0; index < formulas.Length; index++)
            {
                dynamic shape = targetSlide.Shapes.Item(index + 2);
                Check(OleFormulaContent.IsFormula((object)shape), "Import changed the original layer order");
                VerifyGeometry((object)shape, geometry[index]);
            }
            Check((await adapter.LoadFormulaEntriesAsync(true, token)).Count == formulas.Length, "Copied MathType import did not finish");
            copied.SaveAs(Path.Combine(Path.GetDirectoryName(output)!, "powerpoint-mathtype-layout-import.pptx"), 24);
            Console.WriteLine("PASS|PPT MathType roots/matrix/cases/alignment/twins, cancellation/retry, layers, saved state, copy after source closed");
        }
        finally
        {
            if (source != null) Close((object)source);
            if (copied != null) Close((object)copied);
            previous.Windows.Item(1).Activate();
        }
    }

    private static void VerifyGeometry(object shapeObject, (float Left, float Top, float Width, float Height) expected)
    {
        dynamic shape = shapeObject;
        Check(Math.Abs(Convert.ToSingle(shape.Left) - expected.Left) < 0.1
            && Math.Abs(Convert.ToSingle(shape.Top) - expected.Top) < 0.1
            && Math.Abs(Convert.ToSingle(shape.Width) - expected.Width) < 0.1
            && Math.Abs(Convert.ToSingle(shape.Height) - expected.Height) < 0.1, "Conversion changed formula geometry");
    }

    private static void Close(object presentation)
    {
        try { ((dynamic)presentation).Saved = -1; ((dynamic)presentation).Close(); }
        catch (COMException) { }
    }

    private static void Check(bool condition, string message) { if (!condition) throw new InvalidOperationException(message); }
}
