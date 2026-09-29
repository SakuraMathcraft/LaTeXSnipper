using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
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
            var editor = new TrackingEditor();
            var options = new TestOptionsProvider { CurrentLatex = @"\sqrt{\alpha}" };
            using var controller = new PowerPointPluginController(new FormulaEditorSession(editor),
                new AutomationApiClient(new AutomationApiOptions()), adapter, renderer,
                new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() }),
                optionsProvider: options);
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
            Check(adapter.GetCurrentFontSizePoints() == 0, "Selected formula was treated as text font selection");
            await controller.InsertFormulaAsync(Token);
            Check(editor.OpenedForInsert, "Selected formula prevented the editor from opening");
            await controller.InsertFormulaFromTaskPaneAsync(Token);
            dynamic slide = presentation.Slides.Item(1);
            Check(Convert.ToInt32(slide.Shapes.Count) == 2, "Selected formula was replaced instead of adding a new formula");
            dynamic inserted = slide.Shapes.Item(2);
            float slideWidth = Convert.ToSingle(presentation.PageSetup.SlideWidth);
            float slideHeight = Convert.ToSingle(presentation.PageSetup.SlideHeight);
            Check(Math.Abs(Convert.ToSingle(inserted.Left) - (slideWidth - Convert.ToSingle(inserted.Width)) / 2) < 0.1,
                "New formula was not centered horizontally");
            Check(Math.Abs(Convert.ToSingle(inserted.Top) - (slideHeight - Convert.ToSingle(inserted.Height)) / 2) < 0.1,
                "New formula was not centered vertically");
            inserted.Delete();
            dynamic textBox = slide.Shapes.AddTextbox(1, 100, 250, 500, 100);
            string textBoxName = Convert.ToString(textBox.Name);
            textBox.TextFrame.TextRange.Text = "before after";
            textBox.TextFrame.TextRange.Font.Size = 28;
            textBox.TextFrame.TextRange.Characters(8, 0).Select();
            Check(adapter.GetCurrentFontSizePoints() == 28, "Text cursor font size was not read from PowerPoint");
            await controller.InsertFormulaAsync(Token);
            Check(editor.InitialFormula != null, "Text cursor did not open formula editor");
            slide.Shapes.Item(1).Select();
            await controller.AcceptEditorFormulaAsync(new FormulaEditorAcceptedEventArgs(
                editor.InitialFormula!, false, @"\frac{1}{2}", false, editor.Generation,
                editor.InitialFormula!.Typography.WithFontSize(28)), Token);
            Check(Convert.ToInt32(slide.Shapes.Count) == 2, "Inline equation created a floating shape");
            Check(Convert.ToString(textBox.TextFrame.TextRange.Text).StartsWith("before ", StringComparison.Ordinal)
                && Convert.ToString(textBox.TextFrame.TextRange.Text).EndsWith("after", StringComparison.Ordinal),
                "Inline equation damaged surrounding text");
            dynamic native = textBox.TextFrame2.TextRange.MathZones(1, 1);
            Check(Convert.ToDouble(native.Font.Size) == 28, "Inline equation did not use the chosen point size");
            Check(!Convert.ToString(native.Text).Contains(@"\frac"), "LaTeX was pasted as literal text");
            Console.WriteLine("PASS|PPT text cursor inserts native equation from editor and preserves host text");

            dynamic secondTextBox = slide.Shapes.AddTextbox(1, 100, 350, 500, 100);
            string secondTextBoxName = Convert.ToString(secondTextBox.Name);
            secondTextBox.TextFrame.TextRange.Text = "left right";
            secondTextBox.TextFrame.TextRange.Characters(6, 0).Select();
            await controller.InsertFormulaFromTaskPaneAsync(Token);
            Check(Convert.ToInt32(slide.Shapes.Count) == 3, "Task pane inline equation created a floating shape");
            Check(!Convert.ToString(secondTextBox.TextFrame2.TextRange.MathZones(1, 1).Text).Contains(@"\sqrt"),
                "Task pane LaTeX was pasted as literal text");
            Console.WriteLine("PASS|PPT task pane inserts native equation at text cursor");
            options.CurrentLatex = @"e^{i\pi}+1=0";
            dynamic noSpaceTextBox = slide.Shapes.AddTextbox(1, 100, 450, 500, 100);
            noSpaceTextBox.TextFrame.TextRange.Text = "sfasf";
            noSpaceTextBox.TextFrame.TextRange.Characters(6, 0).Select();
            using (var paneFocus = new Form { ShowInTaskbar = false, Width = 240, Height = 120 })
            {
                var paneInput = new TextBox { Dock = DockStyle.Fill };
                paneFocus.Controls.Add(paneInput);
                paneFocus.Show();
                paneInput.Focus();
                await controller.InsertFormulaFromTaskPaneAsync(Token);
            }
            Check(Convert.ToInt32(noSpaceTextBox.TextFrame2.TextRange.MathZones(1, 1).Length) > 0,
                "The default formula was not inserted at the end of a text box without trailing whitespace");
            Check(Convert.ToString(noSpaceTextBox.TextFrame.TextRange.Text).StartsWith("sfasf", StringComparison.Ordinal),
                "Inline equation changed the text before the caret");
            noSpaceTextBox.Delete();
            Console.WriteLine("PASS|PPT task pane inserts the default formula after plain text without a space");
            dynamic workerTextBox = slide.Shapes.AddTextbox(1, 100, 450, 500, 100);
            workerTextBox.TextFrame.TextRange.Text = "left right";
            workerTextBox.TextFrame.TextRange.Characters(6, 0).Select();
            PowerPointTextInsertionTarget workerTarget = adapter.CaptureTextInsertionTarget()
                ?? throw new InvalidOperationException("PowerPoint text caret was not captured");
            string mathMl = await renderer.ConvertTypographyToMathMlAsync("x+1", FormulaDisplayMode.Inline, style, Token);
            await Task.Run(() => adapter.InsertNativeEquationAsync(workerTarget, mathMl, 28, Token));
            Check(Convert.ToInt32(workerTextBox.TextFrame2.TextRange.MathZones(1, 1).Length) > 0,
                "Native equation insertion did not return to the Office STA thread");
            workerTextBox.Delete();
            Console.WriteLine("PASS|PPT native equation paste marshals from a worker to the Office STA thread");
            dynamic inlineTextBox = slide.Shapes.AddTextbox(1, 100, 450, 500, 100);
            inlineTextBox.TextFrame.TextRange.Text = "text ";
            inlineTextBox.TextFrame.TextRange.Characters(6, 0).Select();
            PowerPointTextInsertionTarget inlineTarget = adapter.CaptureTextInsertionTarget()
                ?? throw new InvalidOperationException("PowerPoint text caret was not captured at the end of a line");
            string inlineMathMl = await renderer.ConvertTypographyToMathMlAsync(@"e^{i\pi}+1=0",
                FormulaDisplayMode.Inline, style, Token);
            await Task.Run(() => adapter.InsertNativeEquationAsync(inlineTarget, inlineMathMl, 28, Token));
            Check(Convert.ToInt32(inlineTextBox.TextFrame2.TextRange.MathZones(1, 1).Length) > 0,
                "The default formula was not inserted as a native equation at the text caret");
            inlineTextBox.Delete();
            Console.WriteLine("PASS|PPT default formula inserts as a native equation at the end of text");
            presentation.Slides.Item(1).Shapes.Item(1).Select();
            Console.WriteLine("PASS|PPT selected formula still opens editor and inserts a centered formula");
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
            dynamic reopenedSlide = presentation.Slides.Item(1);
            Check(Convert.ToInt32(reopenedSlide.Shapes.Item(textBoxName).TextFrame2.TextRange.MathZones(1, 1).Length) > 0,
                "Native equation was lost after reopening PowerPoint");
            Check(Convert.ToInt32(reopenedSlide.Shapes.Item(secondTextBoxName).TextFrame2.TextRange.MathZones(1, 1).Length) > 0,
                "Task pane native equation was lost after reopening PowerPoint");
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

    private sealed class TrackingEditor : IFormulaEditor
    {
        public bool OpenedForInsert { get; private set; }
        public FormulaMetadata? InitialFormula { get; private set; }
        public long Generation { get; private set; }

        public Task WarmUpAsync(CancellationToken token) => Task.CompletedTask;
        public Task OpenAsync(FormulaMetadata metadata, bool updateMode, long generation, CancellationToken token)
        {
            OpenedForInsert = !updateMode;
            InitialFormula = metadata;
            Generation = generation;
            return Task.CompletedTask;
        }
        public void Dispose() { }
    }

    private sealed class TestOptionsProvider : IPowerPointFormulaOptionsProvider
    {
        public string CurrentLatex { get; set; } = string.Empty;
        public void ResetFormulaDraft() { }
    }
}
