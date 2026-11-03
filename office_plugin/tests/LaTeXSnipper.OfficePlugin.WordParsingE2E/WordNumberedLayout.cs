using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordNumberedLayout
{
    private const string TestOmml = "<m:oMath xmlns:m='http://schemas.openxmlformats.org/officeDocument/2006/math'><m:r><m:t>y+2</m:t></m:r></m:oMath>";
    public static async Task VerifyAsync(object application, WordPluginSettings settings, string output)
    {
        dynamic word = application;
        foreach (string layout in new[] { "body", "columns", "unequal-left", "unequal-right", "section", "table" })
        foreach (bool automatic in new[] { false, true })
        {
            dynamic document = word.Documents.Add();
            using var adapter = new DynamicWordApplicationAdapter(application);
            var options = new TestFormulaOptionsProvider { CurrentLatex = "x+1",
                Options = new WordFormulaOptions(true, automatic ? NumberingMode.Automatic : NumberingMode.Manual, automatic ? "" : "N") };
            using var controller = WordAddInFactory.CreateController(application,
                optionsProvider: options, settingsLoader: () => settings,
                applicationAdapter: adapter, mathJaxHostName: "NumberLayout-" + Guid.NewGuid().ToString("N"));
            try
            {
                if (layout == "columns") document.PageSetup.TextColumns.SetCount(2);
                dynamic range = document.Range(0, 0);
                if (layout == "section")
                {
                    range.InsertBreak(2);
                    range = document.Sections.Item(2).Range;
                    range.Collapse(1);
                    range.Sections.Item(1).PageSetup.LeftMargin = 110;
                    range.Sections.Item(1).PageSetup.RightMargin = 95;
                }
                if (layout.StartsWith("unequal-"))
                {
                    dynamic columns = document.PageSetup.TextColumns;
                    columns.SetCount(2);
                    columns.EvenlySpaced = 0;
                    columns.Item(1).Width = 160;
                    columns.Item(1).SpaceAfter = 30;
                    if (layout == "unequal-right")
                    {
                        range.InsertBreak(8);
                        range = document.Range(1, 1);
                    }
                }
                double expected;
                if (layout == "table")
                {
                    dynamic table = document.Tables.Add(range, 1, 2);
                    table.AllowAutoFit = false;
                    dynamic cell = table.Cell(1, 1);
                    range = cell.Range;
                    expected = Convert.ToDouble(cell.Width) - Convert.ToDouble(cell.LeftPadding) - Convert.ToDouble(cell.RightPadding);
                }
                else expected = Convert.ToDouble(range.Sections.Item(1).PageSetup.TextColumns.Item(layout == "unequal-right" ? 2 : 1).Width);
                range.Collapse(1);
                range.Select();
                await controller.InsertOmmlAsync(CancellationToken.None);
                var entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single();
                dynamic paragraph = document.Range(entry.Start, entry.Start + 1).Paragraphs.Item(1).Range;
                double actual = Convert.ToDouble(paragraph.ParagraphFormat.TabStops.Item(2).Position);
                E2EAssert.True(Math.Abs(actual - expected) < 1, layout + " number tab width");
                dynamic numberBookmark = document.Bookmarks.Item(1);
                string numberName = Convert.ToString(numberBookmark.Name);
                int numberStart = Convert.ToInt32(numberBookmark.Range.Start);
                int end = Convert.ToInt32(numberBookmark.Range.End);
                document.Range(end, end).Text = "TAIL";
                document.Bookmarks.Add(numberName, document.Range(numberStart, end));
                document.Bookmarks.Add("KeepTail", document.Range(end, end + 4));
                int start = Convert.ToInt32(paragraph.Start);
                document.Range(start, start).Text = "HEAD";
                document.Bookmarks.Add("KeepHead", document.Range(start, start + 4));
                document.Bookmarks.Item("KeepTail").Range.Font.Superscript = -1;
                await controller.FormatAllAsync(CancellationToken.None);
                VerifySurrounding(document);
                if (settings.InsertionBackend == FormulaInsertionBackend.Ole)
                {
                    foreach (bool toOle in new[] { false, true })
                    {
                        entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single();
                        word.Selection.SetRange(entry.Start, entry.Start + 1);
                        if (toOle) await controller.ConvertSelectedToOleAsync(CancellationToken.None);
                        else await controller.ConvertSelectedToOmmlAsync(CancellationToken.None);
                        VerifySurrounding(document);
                        E2EAssert.Equal(1, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "Converted equation count");
                    }
                }
                if (settings.InsertionBackend == FormulaInsertionBackend.WordOmml)
                {
                    foreach (var mode in new[] { NumberingMode.None, NumberingMode.Automatic, NumberingMode.Manual })
                    {
                        var previous = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single().Metadata!;
                        var updated = new FormulaMetadata(previous.Identity, "y+2", FormulaDisplayMode.Display, mode,
                            mode == NumberingMode.Manual ? "Q" : "", previous.RenderEngine, previous.SchemaVersion, previous.Typography);
                        await adapter.UpdateFormulaAsync(updated.Identity.EquationId,
                            WordOmmlDocumentBuilder.BuildFlatOpcDocument(TestOmml, updated, true),
                            WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(TestOmml, updated),
                            WordOmmlDocumentBuilder.BuildFlatOpcEquationContentDocument(TestOmml), updated, true, CancellationToken.None);
                        VerifySurrounding(document);
                        E2EAssert.Equal(mode, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single().Metadata!.NumberingMode, "Updated number mode");
                    }
                }
                else if (layout == "body" || layout == "table")
                {
                    using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("NumberModes"));
                    foreach (var mode in new[] { NumberingMode.None, NumberingMode.Automatic, NumberingMode.Manual })
                    {
                        var previous = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single().Metadata!;
                        var updated = new FormulaMetadata(previous.Identity, "y+2", FormulaDisplayMode.Display, mode,
                            mode == NumberingMode.Manual ? "Q" : "", mode == NumberingMode.None ? RenderEngineKind.Omml : RenderEngineKind.MathJaxSvg, previous.SchemaVersion, previous.Typography);
                        var svg = await renderer.RenderAsync(new RenderRequest("y+2", FormulaDisplayMode.Display,
                            RenderEngineKind.MathJaxSvg, updated.Typography), CancellationToken.None);
                        var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                            new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), CancellationToken.None);
                        if (mode == NumberingMode.None)
                            await adapter.UpdateFormulaAsync(updated.Identity.EquationId,
                                WordOmmlDocumentBuilder.BuildFlatOpcDocument(TestOmml, updated, true),
                                WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(TestOmml, updated),
                                WordOmmlDocumentBuilder.BuildFlatOpcEquationContentDocument(TestOmml), updated, true, CancellationToken.None);
                        else
                            await adapter.UpdateOleFormulaObjectAsync(updated.Identity.EquationId, updated, emf, true, CancellationToken.None);
                        VerifySurrounding(document);
                        E2EAssert.Equal(mode, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single().Metadata!.NumberingMode, "Updated OLE number mode");
                    }
                }
                string path = Path.Combine(Path.GetDirectoryName(output)!, $"numbered-{settings.InsertionBackend}-{layout}-{automatic}.docx");
                document.SaveAs2(path, 16);
                document.Close(0);
                document = word.Documents.Open(path);
                document.Activate();
                VerifySurrounding(document);
                Console.WriteLine($"PASS|Numbered width and surrounding text, modes, conversions, reopen|{settings.InsertionBackend}|{layout}|automatic={automatic}");
            }
            finally { document.Close(0); }
        }
    }

    private static void VerifySurrounding(dynamic document)
    {
        E2EAssert.Equal("HEAD", Convert.ToString(document.Bookmarks.Item("KeepHead").Range.Text), "Numbered update prefix");
        E2EAssert.Equal("TAIL", Convert.ToString(document.Bookmarks.Item("KeepTail").Range.Text), "Numbered update suffix");
        E2EAssert.Equal(-1, Convert.ToInt32(document.Bookmarks.Item("KeepTail").Range.Font.Superscript), "Numbered update formatting");
        E2EAssert.True(!Convert.ToString(document.Content.Text).Contains("\u2060"), "Conversion left a placeholder in the document");
    }
}
