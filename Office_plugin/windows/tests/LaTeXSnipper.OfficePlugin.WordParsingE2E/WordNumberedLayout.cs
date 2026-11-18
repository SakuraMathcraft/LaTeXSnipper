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
        if (settings.InsertionBackend == FormulaInsertionBackend.WordOmml)
            await VerifyInlineEditingAsync(application);
        else
            await VerifyOleSelectionInsertionAsync(application, settings);
        dynamic word = application;
        foreach (string layout in Layouts)
        foreach (bool automatic in new[] { false, true })
        {
            dynamic document = word.Documents.Add();
            using var adapter = new DynamicWordApplicationAdapter(application);
            var options = new TestFormulaOptionsProvider { CurrentLatex = "x+1",
                Options = new WordFormulaOptions(true, automatic ? NumberingMode.Automatic : NumberingMode.Manual, automatic ? "" : "N") };
            var status = new RecordingStatusSink();
            using var controller = WordAddInFactory.CreateController(application, status,
                optionsProvider: options, settingsLoader: () => settings,
                applicationAdapter: adapter, mathJaxHostName: "NumberLayout-" + Guid.NewGuid().ToString("N"));
            try
            {
                var (targetRange, expected) = CreateLayout((object)document, layout);
                dynamic range = targetRange;
                range.Collapse(1);
                range.Select();
                await controller.InsertOmmlAsync(CancellationToken.None);
                var entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single();
                if (settings.InsertionBackend == FormulaInsertionBackend.WordOmml && layout == "body" && !automatic)
                {
                    word.Selection.SetRange(entry.Start, entry.Start + 1);
                    await controller.ConvertSelectedToMathTypeAsync(CancellationToken.None);
                    E2EAssert.Equal(MathTypeText.Get("WordMathTypeUnsupported"), status.Entries.Last().Message,
                        "OMML is not already in the MathType format");
                }
                dynamic paragraph = document.Range(entry.Start, entry.Start + 1).Paragraphs.Item(1).Range;
                double actual = Convert.ToDouble(paragraph.ParagraphFormat.TabStops.Item(2).Position);
                E2EAssert.True(Math.Abs(actual - expected) < 1, $"{layout} number tab width: expected {expected}, actual {actual}");
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
                        var targets = await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None);
                        E2EAssert.Equal(1, targets.Count,
                            $"Numbered conversion targets in {document.Name}, active document {word.ActiveDocument.Name}: " +
                            string.Join(", ", targets.Select(target => $"{target.Start}:{target.Metadata?.Identity.EquationId}")));
                        entry = targets.Single();
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
                entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single();
                dynamic formulaParagraph = document.Range(entry.Start, entry.Start + 1).Paragraphs.Item(1).Range;
                int neighborStart = Convert.ToInt32(formulaParagraph.Start);
                document.Range(neighborStart, neighborStart).Text = "DELETE_KEEP";
                document.Bookmarks.Add("DeleteNeighbor", document.Range(neighborStart, neighborStart + 11));
                document.Bookmarks.Item("DeleteNeighbor").Range.Font.Subscript = -1;
                entry = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Single();
                word.Selection.SetRange(entry.Start, entry.Start + 1);
                await adapter.DeleteSelectedFormulaAsync(CancellationToken.None);
                E2EAssert.Equal("DELETE_KEEP", Convert.ToString(document.Bookmarks.Item("DeleteNeighbor").Range.Text), "Deleting equation preserves its paragraph neighbor");
                E2EAssert.Equal(-1, Convert.ToInt32(document.Bookmarks.Item("DeleteNeighbor").Range.Font.Subscript), "Deleting equation preserves neighbor formatting");
                E2EAssert.Equal(0, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "Deleted equation count");
                VerifySurrounding(document);
                Console.WriteLine($"PASS|Numbered width and surrounding text, modes, conversions, reopen|{settings.InsertionBackend}|{layout}|automatic={automatic}");
            }
            finally { document.Close(0); }
        }
    }

    private static async Task VerifyInlineEditingAsync(object application)
    {
        dynamic word = application, document = word.Documents.Add();
        using var adapter = new DynamicWordApplicationAdapter(application);
        var token = CancellationToken.None;
        try
        {
            document.Range(0, 0).Text = "left right";
            word.Selection.SetRange(5, 5);
            string documentId = adapter.GetCurrentDocumentId();
            FormulaMetadata NewFormula() => new(new FormulaIdentity(documentId, Guid.NewGuid().ToString("N")),
                "y+2", FormulaDisplayMode.Inline, NumberingMode.None, "", RenderEngineKind.Omml,
                FormulaMetadata.CurrentSchemaVersion, FormulaTypography.Default);
            Task InsertAsync(FormulaMetadata formula) => adapter.InsertManagedEquationAsync(
                WordOmmlDocumentBuilder.BuildFlatOpcDocument(TestOmml, formula, false), formula, false, token);

            FormulaMetadata original = NewFormula();
            await InsertAsync(original);
            document.ContentControls.Item(1).Range.Select();
            var target = await adapter.LoadSelectedFormulaTargetAsync(token);
            using (adapter.BeginUndoRecord())
                await adapter.UpdateFormulaAsync(target, WordOmmlDocumentBuilder.BuildFlatOpcDocument(TestOmml, original, false),
                    WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(TestOmml, original),
                    WordOmmlDocumentBuilder.BuildFlatOpcEquationContentDocument(TestOmml), original, false, token);
            int start = Convert.ToInt32(document.ContentControls.Item(1).Range.Start);
            int end = Convert.ToInt32(document.ContentControls.Item(1).Range.End);
            int caret = Convert.ToInt32(word.Selection.Start);
            E2EAssert.True(caret >= end && caret == Convert.ToInt32(word.Selection.End), "OMML update caret is outside the formula");
            E2EAssert.Equal("right", ((string)document.Range(caret, document.Content.End).Text).Trim('\r'), "OMML update caret precedes the following text");

            word.Selection.SetRange(start + 1, start + 1);
            FormulaMetadata appended = NewFormula();
            await InsertAsync(appended);
            var formulas = await adapter.LoadFormulaEntriesAsync(true, token);
            E2EAssert.Equal(2, formulas.Count, "A collapsed OMML selection adds a formula");
            E2EAssert.True(formulas.Any(e => e.Metadata!.Identity.EquationId == appended.Identity.EquationId),
                "Word inserts a formula with the caret inside another OMML formula");

            document.ContentControls.Item(1).Range.Select();
            FormulaMetadata replacement = NewFormula();
            await InsertAsync(replacement);
            formulas = await adapter.LoadFormulaEntriesAsync(true, token);
            E2EAssert.Equal(2, formulas.Count, "A complete OMML selection is replaced by Word");
            E2EAssert.True(formulas.Any(e => e.Metadata!.Identity.EquationId == replacement.Identity.EquationId),
                "Word inserts a formula while another OMML formula is selected");
            string text = Convert.ToString(document.Content.Text);
            E2EAssert.True(text.StartsWith("left ", StringComparison.Ordinal) && text.TrimEnd('\r').EndsWith("right", StringComparison.Ordinal),
                "Insertion and replacement preserve neighboring text");
            Console.WriteLine("PASS|OMML edit caret and insertion inside a formula or over a formula selection");
        }
        finally { document.Close(0); }
    }

    private static async Task VerifyOleSelectionInsertionAsync(object application, WordPluginSettings settings)
    {
        dynamic word = application, document = word.Documents.Add();
        var options = new TestFormulaOptionsProvider
        {
            CurrentLatex = "x+1",
            Options = new WordFormulaOptions(false, NumberingMode.None, "")
        };
        using var adapter = new DynamicWordApplicationAdapter(application);
        using var controller = WordAddInFactory.CreateController(application, optionsProvider: options,
            settingsLoader: () => settings, applicationAdapter: adapter, mathJaxHostName: "OleSelectionInsertion");
        try
        {
            await controller.InsertOmmlAsync(CancellationToken.None);
            document.InlineShapes.Item(1).Range.Select();
            options.CurrentLatex = "x+2";
            await controller.InsertOmmlAsync(CancellationToken.None);
            var formulas = await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None);
            E2EAssert.True(formulas.Any(e => e.Metadata!.Latex == "x+2"), "Word inserts an OLE formula while another is selected");
            Console.WriteLine($"PASS|OLE insertion while another formula is selected|{formulas.Count} formulas");
        }
        finally { document.Close(0); }
    }

    internal static readonly string[] Layouts = { "body", "columns", "unequal-left", "unequal-right", "section", "table" };

    internal static (object Range, double Width) CreateLayout(object targetDocument, string layout)
    {
        dynamic document = targetDocument;
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
        return ((object)range, expected);
    }

    private static void VerifySurrounding(dynamic document)
    {
        E2EAssert.Equal("HEAD", Convert.ToString(document.Bookmarks.Item("KeepHead").Range.Text), "Numbered update prefix");
        E2EAssert.Equal("TAIL", Convert.ToString(document.Bookmarks.Item("KeepTail").Range.Text), "Numbered update suffix");
        E2EAssert.Equal(-1, Convert.ToInt32(document.Bookmarks.Item("KeepTail").Range.Font.Superscript), "Numbered update formatting");
        E2EAssert.True(!Convert.ToString(document.Content.Text).Contains("\u2060"), "Conversion left a placeholder in the document");
    }
}
