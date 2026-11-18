using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;
using Microsoft.Web.WebView2.WinForms;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static partial class MathTypeRoundTrip
{
    private static async Task VerifyWordScenariosAsync(object application, string output, MathJaxSvgRenderer renderer)
    {
        var cases = new[]
        {
            (FormulaDisplayMode.Display, NumberingMode.Manual, WordNumberPlacement.Left),
            (FormulaDisplayMode.Display, NumberingMode.Manual, WordNumberPlacement.Right),
            (FormulaDisplayMode.Display, NumberingMode.Automatic, WordNumberPlacement.Left),
            (FormulaDisplayMode.Display, NumberingMode.Automatic, WordNumberPlacement.Right),
            (FormulaDisplayMode.Inline, NumberingMode.None, WordNumberPlacement.Right),
            (FormulaDisplayMode.Display, NumberingMode.None, WordNumberPlacement.Right),
        };
        dynamic word = application;
        var token = CancellationToken.None;
        const string source = @"\frac{x}{y}";
        FormulaTypography typography = FormulaTypography.Default;
        var emfRenderer = new EnhancedMetafilePresentationRenderer();
        var presentations = new Dictionary<FormulaDisplayMode, OlePresentationResult>();
        foreach (var display in new[] { FormulaDisplayMode.Inline, FormulaDisplayMode.Display })
        {
            RenderResult svg = await renderer.RenderAsync(new RenderRequest(source, display, RenderEngineKind.MathJaxSvg, typography), token);
            presentations[display] = await emfRenderer.RenderPresentationAsync(new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
        }

        foreach (var (display, numbering, placement) in cases)
        {
            var settings = new WordPluginSettings(placement, FormulaInsertionBackend.Ole, WordNumberEnclosure.Parentheses,
                false, false, false, false, ".", typography.Color, typography.DefaultMathStyle, typography.FontSizePoints);
            using var adapter = new DynamicWordApplicationAdapter(application, settingsLoader: () => settings);
            string hostName = "MathTypeScenarios-" + Guid.NewGuid().ToString("N");
            var status = new RecordingStatusSink();
            using var controller = WordAddInFactory.CreateController(application, status, applicationAdapter: adapter,
                settingsLoader: () => settings, mathJaxHostName: hostName, editorProfileName: hostName + "-Editor");
            foreach (string layout in WordNumberedLayout.Layouts)
            {
                string stage = $"{layout}-{display}-{numbering}-{placement}";
                string path = Path.Combine(Path.GetDirectoryName(output)!, "math-type-" + stage + ".docx");
                dynamic? document = word.Documents.Add();
                try
                {
                    var (insertionRange, _) = WordNumberedLayout.CreateLayout((object)document, layout);
                    dynamic insertion = insertionRange;
                    insertion.Collapse(1);
                    insertion.Select();
                    var identity = new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N"));
                    var metadata = new FormulaMetadata(identity, source, display, numbering, numbering == NumberingMode.Manual ? "A.7" : "",
                        RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, typography);
                    await adapter.InsertOleFormulaObjectAsync(metadata, presentations[display], display == FormulaDisplayMode.Display, token);
                    string? bookmark = null;
                    if (numbering != NumberingMode.None)
                    {
                        bookmark = Convert.ToString((object)document.Bookmarks.Item(1).Name);
                        int position = Convert.ToInt32((object)document.Content.End) - 1;
                        document.Fields.Add(document.Range(position, position), -1, " REF " + bookmark + " ", true).Update();
                    }
                    string original = WordLayoutSnapshot((object)document, bookmark, placement);

                    document.InlineShapes.Item(1).Range.Select();
                    await controller.ConvertSelectedToMathTypeAsync(token);
                    VerifyWordScenario((object)document, bookmark, placement, stage + " MathType", original);
                    dynamic mathType = document.InlineShapes.Item(1);
                    if (numbering != NumberingMode.None)
                        E2EAssert.True(((string)mathType.Range.Paragraphs.Item(1).Range.WordOpenXML)
                            .Contains("MACROBUTTON MTPlaceRef"), stage + " MathType-native numbering");
                    byte[] native = MathTypeWordPackage.ReadNative(Convert.ToString((object)mathType.Range.WordOpenXML)!);
                    E2EAssert.Equal(display, MathTypeNativeEquation.ReadDisplayMode(native), stage + " MTEF display mode");

                    if (layout == "body" && numbering == NumberingMode.None)
                    {
                        mathType.Range.Select();
                        await controller.ConvertSelectedToMathTypeAsync(token);
                        E2EAssert.Equal(WordAddInText.Get("NoConversionNeededStatus"), status.Entries.Last().Message,
                            "An existing MathType equation already has the target format");
                        var target = adapter.CaptureMathTypeFormula(null)
                            ?? throw new InvalidOperationException("Cannot capture the MathType formula for editing");
                        await adapter.UpdateMathTypeAsync(target, metadata, MathTypeCompoundFile.Create(native), presentations[display], token);
                        dynamic updated = document.InlineShapes.Item(1).Range;
                        int end = Convert.ToInt32(display == FormulaDisplayMode.Display
                            ? updated.Paragraphs.Item(1).Range.End : updated.End);
                        E2EAssert.Equal(end, Convert.ToInt32(word.Selection.Start), stage + " MathType update caret");
                        E2EAssert.Equal(end, Convert.ToInt32(word.Selection.End), stage + " MathType update selection");
                    }

                    document.SaveAs2(path, 16);
                    document.Close(0);
                    document = null;
                    document = word.Documents.Open(path);
                    document.Activate();
                    VerifyWordScenario((object)document, bookmark, placement, stage + " reopened MathType", original);
                    document.InlineShapes.Item(1).Range.Select();
                    await controller.ConvertSelectedToOleAsync(token);
                    VerifyWordScenario((object)document, bookmark, placement, stage + " imported OLE", original);
                    var imported = (await adapter.LoadFormulaEntriesAsync(true, token)).Single().Metadata!;
                    E2EAssert.Equal(source, imported.Latex, stage + " editable LaTeX");
                    E2EAssert.Equal(display, imported.DisplayMode, stage + " imported display mode");
                    E2EAssert.Equal(numbering, imported.NumberingMode, stage + " imported numbering mode");
                    E2EAssert.Equal(metadata.NumberText, imported.NumberText, stage + " imported manual number");
                    if (numbering == NumberingMode.Automatic)
                        E2EAssert.True(((string)document.InlineShapes.Item(1).Range.Paragraphs.Item(1).Range.WordOpenXML)
                            .Contains("SEQ LaTeXSnipperEquation"), stage + " LaTeXSnipper-native sequence");
                    if (numbering != NumberingMode.None)
                        E2EAssert.Equal(identity.EquationId, imported.Identity.EquationId, stage + " numbering identity");

                    document.Save();
                    document.Close(0);
                    document = null;
                    document = word.Documents.Open(path);
                    document.Activate();
                    VerifyWordScenario((object)document, bookmark, placement, stage + " reopened OLE", original);
                    E2EAssert.Equal(source, (await adapter.LoadFormulaEntriesAsync(true, token)).Single().Metadata!.Latex, stage + " reopened editable source");
                    if (layout == "body" && display == FormulaDisplayMode.Display && numbering == NumberingMode.None)
                        await EditImportedFormulaAsync((object)document, controller, adapter);
                    Console.WriteLine("PASS|MathType Word layout and editable LaTeX|" + stage);
                }
                finally { if (document != null) document.Close(0); }
            }
        }
        await VerifyNativeWordNumberAsync(application, presentations[FormulaDisplayMode.Display], renderer, source);
    }

    private static async Task VerifyNativeWordNumberAsync(object application, OlePresentationResult presentation,
        MathJaxSvgRenderer renderer, string source)
    {
        dynamic word = application;
        var token = CancellationToken.None;
        string mathMl = await renderer.ConvertTypographyToMathMlAsync(source, FormulaDisplayMode.Display, FormulaTypography.Default, token);
        byte[] compound = MathTypeCompoundFile.Create(MathTypeNativeEquation.Create(mathMl, 12, FormulaDisplayMode.Display));
        foreach (WordNumberPlacement placement in new[] { WordNumberPlacement.Left, WordNumberPlacement.Right })
        {
            dynamic document = word.Documents.Add();
            using var adapter = new DynamicWordApplicationAdapter(application);
            using var controller = WordAddInFactory.CreateController(application, applicationAdapter: adapter,
                mathJaxHostName: "NativeNumber-" + Guid.NewGuid().ToString("N"));
            try
            {
                document.Range(0, 0).InsertXML(MathTypeWordPackage.Create(compound, presentation,
                    (float)presentation.WidthPoints, (float)presentation.HeightPoints));
                dynamic shape = document.InlineShapes.Item(1);
                dynamic paragraph = shape.Range.Paragraphs.Item(1).Range;
                paragraph.Style = document.Styles.Add("MTDisplayEquation", 1);
                bool left = placement == WordNumberPlacement.Left;
                int boundary = Convert.ToInt32((object)(left ? shape.Range.Start : shape.Range.End));
                document.Range(boundary, boundary).Text = "\t";
                int position = left ? boundary : boundary + 1;
                dynamic field = document.Fields.Add(document.Range(position, position), -1, " SEQ MTEqn ", true);
                field.Update();
                const string bookmark = "NativeEquationNumber";
                document.Bookmarks.Add(bookmark, field.Result);
                if (document.Paragraphs.Count == 1) document.Content.InsertParagraphAfter();
                int end = Convert.ToInt32((object)document.Content.End) - 1;
                document.Fields.Add(document.Range(end, end), -1, " REF " + bookmark + " ", true).Update();
                string original = WordLayoutSnapshot((object)document, bookmark, placement);

                shape.Range.Select();
                await controller.ConvertSelectedToOleAsync(token);
                VerifyWordScenario((object)document, bookmark, placement, "Native MathType number", original);
                var imported = (await adapter.LoadFormulaEntriesAsync(true, token)).Single().Metadata!;
                E2EAssert.Equal(NumberingMode.Automatic, imported.NumberingMode, "Native SEQ result was not recognized as an equation number");
                document.InlineShapes.Item(1).Range.Select();
                await controller.ConvertSelectedToMathTypeAsync(token);
                VerifyWordScenario((object)document, bookmark, placement, "Native MathType number round trip", original);
                Console.WriteLine("PASS|MathType Word MTDisplayEquation retains existing SEQ and REF|" + placement);
            }
            finally { document.Close(0); }
        }
    }

    private static async Task EditImportedFormulaAsync(object target, WordPluginController controller, DynamicWordApplicationAdapter adapter)
    {
        dynamic document = target;
        var token = CancellationToken.None;
        document.InlineShapes.Item(1).Range.Select();
        await controller.LoadSelectedAsync(token);
        Form editor = Application.OpenForms.Cast<Form>().Single(form => form.GetType().Name == "MathLiveFormulaEditorForm");
        WebView2 browser = editor.Controls.OfType<WebView2>().Single();
        const string source = "document.querySelector('#latexSource .cm-content')";
        string state = "WebView2 starting";
        await WaitForEditorAsync(async () =>
        {
            if (editor.IsDisposed) throw new InvalidOperationException("The Word formula editor closed during initialization.");
            if (browser.CoreWebView2 == null) return false;
            state = await browser.ExecuteScriptAsync("(() => { const source = " + source + "; const visual = document.querySelector('#mathfieldHost math-field');" +
                @"return { url: location.href, source: source?.textContent, readOnly: visual?.readOnly, status: document.getElementById('statusText')?.textContent,
                    ready: source?.textContent.includes('\\frac') === true && visual?.readOnly === false }; })()");
            return state.Contains("\"ready\":true");
        }, () => "Imported LaTeX did not open as editable math. " + state);
        await browser.ExecuteScriptAsync(source + ".focus()");
        await browser.CoreWebView2.CallDevToolsProtocolMethodAsync("Input.dispatchKeyEvent",
            """{"type":"keyDown","key":"End","code":"End","windowsVirtualKeyCode":35}""");
        await browser.CoreWebView2.CallDevToolsProtocolMethodAsync("Input.insertText", """{"text":"+17"}""");
        await WaitForEditorAsync(async () => await browser.ExecuteScriptAsync(source + ".textContent.endsWith('+17')") == "true",
            () => "Typing did not edit the imported LaTeX.");
        await browser.ExecuteScriptAsync("document.getElementById('acceptButton').click()");
        await WaitForEditorAsync(() => Task.FromResult(editor.IsDisposed), () => "Edited formula did not save and close.");
        E2EAssert.True((await adapter.LoadFormulaEntriesAsync(true, token)).Single().Metadata!.Latex.EndsWith("+17", StringComparison.Ordinal),
            "Editor changes were not saved to OLE.");

        document.InlineShapes.Item(1).Range.Select();
        await controller.ConvertSelectedToMathTypeAsync(token);
        byte[] native = MathTypeWordPackage.ReadNative(Convert.ToString((object)document.InlineShapes.Item(1).Range.WordOpenXML)!);
        E2EAssert.True(XDocument.Parse(MathTypeNativeEquation.ReadMathMl(native)).Descendants()
            .Any(node => node.Name.LocalName == "mn" && node.Value == "17"), "Re-export used an older version of the formula.");
        Console.WriteLine("PASS|Opened imported LaTeX in the editor, edited, saved and re-exported to MathType");
    }

    private static async Task WaitForEditorAsync(Func<Task<bool>> condition, Func<string> error)
    {
        var stopwatch = Stopwatch.StartNew();
        while (stopwatch.Elapsed < TimeSpan.FromSeconds(20))
        {
            if (await condition()) return;
            await Task.Delay(40);
        }
        throw new InvalidOperationException(error());
    }

    private static void VerifyWordScenario(object document, string? bookmark, WordNumberPlacement placement, string stage, string expected) =>
        E2EAssert.Equal(expected, WordLayoutSnapshot(document, bookmark, placement), stage + " paragraph, spacing, tabs, size, bookmarks and REF");

    private static string WordLayoutSnapshot(object target, string? bookmark, WordNumberPlacement placement)
    {
        dynamic document = target;
        dynamic shape = document.InlineShapes.Item(1);
        dynamic paragraph = shape.Range.Paragraphs.Item(1).Range;
        dynamic format = paragraph.ParagraphFormat;
        var tabs = new List<string>();
        for (int i = 1; i <= Convert.ToInt32((object)format.TabStops.Count); i++)
        {
            dynamic tab = format.TabStops.Item(i);
            if (Convert.ToInt32((object)tab.Alignment) == 0) continue; // Word exposes implicit default stops in some cells.
            tabs.Add($"{Convert.ToDouble((object)tab.Position):F1}:{tab.Alignment}");
        }
        string numberText = string.Empty, fields = string.Empty;
        if (bookmark != null)
        {
            dynamic number = document.Bookmarks.Item(bookmark).Range;
            bool onLeft = Convert.ToInt32((object)number.End) <= Convert.ToInt32((object)shape.Range.Start);
            E2EAssert.Equal(placement == WordNumberPlacement.Left, onLeft, "Number moved to the other side of the equation");
            numberText = Convert.ToString((object)number.Text) ?? "";
            var fieldCodes = new List<string>();
            foreach (dynamic field in document.Fields)
            {
                string code = Convert.ToString((object)field.Code.Text) ?? "";
                if (code.TrimStart().StartsWith("REF", StringComparison.OrdinalIgnoreCase))
                {
                    field.Update();
                    fieldCodes.Add(code + ":" + Convert.ToString((object)field.Result.Text));
                }
            }
            fields = string.Join("|", fieldCodes);
        }
        string text = bookmark == null ? Convert.ToString((object)paragraph.Text)! : "";
        return string.Join("|", (object)document.Paragraphs.Count, (object)document.InlineShapes.Count, (object)document.Tables.Count,
            text, (object)paragraph.Style.NameLocal, (object)format.Alignment, (object)format.LeftIndent,
            (object)format.RightIndent, (object)format.FirstLineIndent, (object)format.SpaceBefore, (object)format.SpaceAfter,
            string.Join(",", tabs), Convert.ToDouble((object)shape.Width).ToString("F1"), Convert.ToDouble((object)shape.Height).ToString("F1"),
            numberText, fields);
    }
}
