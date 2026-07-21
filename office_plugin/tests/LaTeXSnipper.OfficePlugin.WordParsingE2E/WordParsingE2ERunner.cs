using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal sealed class WordParsingE2ERunner
{
    private const int WdDoNotSaveChanges = 0;
    private const int WdExportFormatPdf = 17;
    private const int WdFormatDocumentDefault = 16;

    private static readonly string[] ExpectedFailedSources =
    {
        @"$$E=T+V\tag{}$$",
        @"$$m\ddot q+kq=0\tag{A}\tag{B}$$",
        @"$$\ddot q+\omega^2q=0\tag{osc$$",
        @"$$\frac{\partial L}{\partial q}=0\tag*{star}$$",
    };

    private readonly E2EOptions _options;

    public WordParsingE2ERunner(E2EOptions options)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
    }

    public async Task RunAsync()
    {
        EnsureWordIsNotRunning();
        Directory.CreateDirectory(Path.GetDirectoryName(_options.OutputPath)
            ?? throw new InvalidOperationException("The output directory is invalid."));
        string pdfPath = Path.ChangeExtension(_options.OutputPath, ".pdf");

        dynamic? word = null;
        dynamic? document = null;
        WordPluginController? controller = null;
        try
        {
            Type wordType = Type.GetTypeFromProgID("Word.Application")
                ?? throw new InvalidOperationException("Microsoft Word is not installed.");
            word = Activator.CreateInstance(wordType)
                ?? throw new InvalidOperationException("Microsoft Word could not be started.");
            word.Visible = false;
            word.DisplayAlerts = 0;
            document = word.Documents.Add();
            WordParsingFixtureBuilder.Build(document, _options.Backend);

            var adapter = new DynamicWordApplicationAdapter(word);
            IReadOnlyList<WordLatexParseCandidate> initialCandidates =
                await adapter.FindLatexParseCandidatesAsync(all: true, CancellationToken.None)
                    .ConfigureAwait(true);
            E2EAssert.Equal(
                WordParsingFixtureBuilder.ExpectedCandidateCount,
                initialCandidates.Count,
                "Initial parse candidate count");
            await VerifySelectionBoundariesAsync(document, adapter, initialCandidates).ConfigureAwait(true);

            var statusSink = new RecordingStatusSink();
            WordPluginSettings settings = CreateSettings(_options.Backend);
            controller = WordAddInFactory.CreateController(
                (object)word,
                statusSink,
                new TestFormulaOptionsProvider(),
                () => settings,
                "WordParsingE2E-" + _options.Backend);

            bool cancellationObserved = false;
            using (var cancellation = new CancellationTokenSource())
            {
                statusSink.CancelAfterNextBatch(cancellation);
                try
                {
                    await controller.ParseAllAsync(cancellation.Token).ConfigureAwait(true);
                }
                catch (OperationCanceledException)
                {
                    cancellationObserved = true;
                }
            }
            E2EAssert.True(cancellationObserved, "The simulated batch timeout was not observed");

            await controller.ParseAllAsync(CancellationToken.None).ConfigureAwait(true);
            await VerifyFinalDocumentAsync(document, adapter).ConfigureAwait(true);

            int formulaCountBeforeRetry = await CountManagedFormulasAsync(document, adapter).ConfigureAwait(true);
            await controller.ParseAllAsync(CancellationToken.None).ConfigureAwait(true);
            await VerifyFinalDocumentAsync(document, adapter).ConfigureAwait(true);
            int formulaCountAfterRetry = await CountManagedFormulasAsync(document, adapter).ConfigureAwait(true);
            E2EAssert.Equal(
                formulaCountBeforeRetry,
                formulaCountAfterRetry,
                "Retry changed the managed formula count");

            if (File.Exists(_options.OutputPath))
            {
                File.Delete(_options.OutputPath);
            }
            if (File.Exists(pdfPath))
            {
                File.Delete(pdfPath);
            }

            document.SaveAs2(_options.OutputPath, WdFormatDocumentDefault);
            document.ExportAsFixedFormat(pdfPath, WdExportFormatPdf);

            document.Close(WdDoNotSaveChanges);
            document = null;
            document = word.Documents.Open(_options.OutputPath, false, true);
            await VerifyFinalDocumentAsync(document, adapter).ConfigureAwait(true);

            Console.WriteLine("PASS|BACKEND=" + _options.Backend);
            Console.WriteLine("DOCX|" + _options.OutputPath);
            Console.WriteLine("PDF|" + pdfPath);
        }
        finally
        {
            controller?.Dispose();
            if (document != null)
            {
                document.Close(WdDoNotSaveChanges);
            }
            if (word != null)
            {
                word.Quit(WdDoNotSaveChanges);
            }
        }
    }

    private static void EnsureWordIsNotRunning()
    {
        if (Process.GetProcessesByName("WINWORD").Length > 0)
        {
            throw new InvalidOperationException(
                "Close all Microsoft Word windows before running the isolated end-to-end test.");
        }
    }

    private static WordPluginSettings CreateSettings(FormulaInsertionBackend backend)
    {
        return new WordPluginSettings(
            WordNumberPlacement.Right,
            backend,
            WordNumberEnclosure.Parentheses,
            includeChapter: false,
            includeSection: false,
            hideChapterBoundary: false,
            hideSectionBoundary: false,
            numberSeparator: "-",
            formulaColor: "#000000",
            useSystemFormulaColor: false,
            FormulaFontStyle.TeX,
            formulaFontScale: 1);
    }

    private async Task VerifyFinalDocumentAsync(
        dynamic document,
        DynamicWordApplicationAdapter adapter)
    {
        E2EAssert.Equal(1, Convert.ToInt32(document.Tables.Count), "Word table count");

        IReadOnlyList<WordLatexParseCandidate> remaining =
            await adapter.FindLatexParseCandidatesAsync(all: true, CancellationToken.None)
                .ConfigureAwait(true);
        Console.WriteLine(
            "REMAINING|" + string.Join(" | ", remaining.Select(candidate => candidate.OriginalText)));
        E2EAssert.Equal(
            WordParsingFixtureBuilder.ExpectedFailedCandidateCount,
            remaining.Count,
            "Remaining candidate count");
        E2EAssert.SetEqual(
            ExpectedFailedSources,
            remaining.Select(candidate => candidate.OriginalText),
            "Remaining failed candidates");

        IReadOnlyList<WordFormulaEntry> formulas = await LoadAllFormulaEntriesAsync(document, adapter)
            .ConfigureAwait(true);
        FormulaMetadata[] managed = formulas
            .Where(entry => !entry.IsNativeWordFormula && entry.Metadata != null)
            .Select(entry => entry.Metadata!)
            .ToArray();
        E2EAssert.Equal(
            WordParsingFixtureBuilder.ExpectedManagedFormulaCount,
            managed.Length,
            "Managed formula count");
        E2EAssert.Equal(1, formulas.Count(entry => entry.IsNativeWordFormula), "Native Word formula count");

        RenderEngineKind expectedEngine = _options.Backend == FormulaInsertionBackend.Ole
            ? RenderEngineKind.MathJaxSvg
            : RenderEngineKind.Omml;
        E2EAssert.True(
            managed.All(metadata => metadata.RenderEngine == expectedEngine),
            "A formula used the wrong render engine");
        E2EAssert.True(
            managed.Where(metadata => metadata.NumberingMode == NumberingMode.Manual)
                .All(metadata => metadata.Latex.IndexOf(@"\tag", StringComparison.Ordinal) < 0),
            "A manually numbered formula retained its top-level tag command");
        FormulaMetadata commentedTag = managed.Single(metadata =>
            metadata.Latex.IndexOf(@"\tag{ignored}", StringComparison.Ordinal) >= 0);
        E2EAssert.Equal(
            NumberingMode.None,
            commentedTag.NumberingMode,
            "A tag inside a comment affected numbering");
        E2EAssert.True(
            managed.Where(metadata => metadata.DisplayMode == FormulaDisplayMode.Inline)
                .All(metadata => metadata.NumberingMode == NumberingMode.None),
            "An inline formula inherited numbering");

        E2EAssert.SetEqual(
            new[] { "5", "7", "8", "EL-field", "T-3" },
            managed.Where(metadata => metadata.NumberingMode == NumberingMode.Manual)
                .Select(metadata => metadata.NumberText),
            "Manual tag numbers");

        string text = Convert.ToString(document.Content.Text) ?? string.Empty;
        E2EAssert.True(text.IndexOf(@"$q$", StringComparison.Ordinal) < 0, "Adjacent q formula was not converted");
        E2EAssert.True(
            text.IndexOf(@"$\ddot q$", StringComparison.Ordinal) < 0,
            "Adjacent ddot q formula was not converted");
        E2EAssert.True(text.Contains(@"$unsafe$"), "Content-control source text changed");
        E2EAssert.True(text.Contains(@"$field$"), "Field source text changed");
        E2EAssert.True(text.Contains(@"$link$"), "Hyperlink source text changed");
        E2EAssert.True(text.Contains(@"\\(a+b\)"), "Escaped parenthesis delimiter changed");
        E2EAssert.True(text.Contains(@"\\[a+b\]"), "Escaped bracket delimiter changed");
        E2EAssert.True(
            text.Contains(@"未闭合 $$\frac{\partial L}{\partial q}"),
            "Unclosed table display source changed");
        E2EAssert.True(
            text.Contains(@"未闭合 \[\delta S=0"),
            "Unclosed table bracket source changed");
        E2EAssert.True(
            text.Contains(@"未闭合行间公式：$$a+b"),
            "Unclosed body display source changed");
        E2EAssert.True(
            text.Contains(@"$$\mathcal E_i(L)="),
            "Final unclosed display source changed");
        string headerText = Convert.ToString(document.Sections.Item(1).Headers.Item(1).Range.Text)
            ?? string.Empty;
        E2EAssert.True(headerText.Contains(@"$header$"), "Header source text changed");
    }

    private static async Task VerifySelectionBoundariesAsync(
        dynamic document,
        DynamicWordApplicationAdapter adapter,
        IReadOnlyList<WordLatexParseCandidate> candidates)
    {
        WordLatexParseCandidate target = candidates.First(candidate =>
            string.Equals(candidate.OriginalText, @"$E_{\mathrm{start}}=0$", StringComparison.Ordinal));

        document.Application.Selection.SetRange(target.Start, target.End);
        IReadOnlyList<WordLatexParseCandidate> fullSelection =
            await adapter.FindLatexParseCandidatesAsync(all: false, CancellationToken.None)
                .ConfigureAwait(true);
        E2EAssert.Equal(1, fullSelection.Count, "Full formula selection candidate count");

        document.Application.Selection.SetRange(target.Start + 1, target.End - 1);
        IReadOnlyList<WordLatexParseCandidate> partialSelection =
            await adapter.FindLatexParseCandidatesAsync(all: false, CancellationToken.None)
                .ConfigureAwait(true);
        E2EAssert.Equal(0, partialSelection.Count, "Partial formula selection candidate count");

        document.Application.Selection.SetRange(target.Start, target.Start + 1);
        IReadOnlyList<WordLatexParseCandidate> openingOnlySelection =
            await adapter.FindLatexParseCandidatesAsync(all: false, CancellationToken.None)
                .ConfigureAwait(true);
        E2EAssert.Equal(0, openingOnlySelection.Count, "Opening-only selection candidate count");

        document.Application.Selection.SetRange(target.End - 1, target.End);
        IReadOnlyList<WordLatexParseCandidate> closingOnlySelection =
            await adapter.FindLatexParseCandidatesAsync(all: false, CancellationToken.None)
                .ConfigureAwait(true);
        E2EAssert.Equal(0, closingOnlySelection.Count, "Closing-only selection candidate count");

        document.Application.Selection.SetRange(target.Start, target.Start);
        IReadOnlyList<WordLatexParseCandidate> collapsedSelection =
            await adapter.FindLatexParseCandidatesAsync(all: false, CancellationToken.None)
                .ConfigureAwait(true);
        E2EAssert.Equal(0, collapsedSelection.Count, "Collapsed selection candidate count");
    }

    private static async Task<int> CountManagedFormulasAsync(
        dynamic document,
        DynamicWordApplicationAdapter adapter)
    {
        IReadOnlyList<WordFormulaEntry> formulas = await LoadAllFormulaEntriesAsync(document, adapter)
            .ConfigureAwait(true);
        return formulas.Count(entry => !entry.IsNativeWordFormula && entry.Metadata != null);
    }

    private static async Task<IReadOnlyList<WordFormulaEntry>> LoadAllFormulaEntriesAsync(
        dynamic document,
        DynamicWordApplicationAdapter adapter)
    {
        dynamic application = document.Application;
        application.Selection.SetRange(document.Content.Start, document.Content.End);
        return await adapter.LoadSelectedFormulaEntriesAsync(CancellationToken.None).ConfigureAwait(true);
    }
}
