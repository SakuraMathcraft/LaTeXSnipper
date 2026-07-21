using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class WordPluginController
{
    public Task ParseSelectedAsync(CancellationToken cancellationToken)
    {
        return ParseLatexAsync(all: false, cancellationToken);
    }

    public Task ParseAllAsync(CancellationToken cancellationToken)
    {
        return ParseLatexAsync(all: true, cancellationToken);
    }

    private async Task ParseLatexAsync(bool all, CancellationToken cancellationToken)
    {
        WordPluginSettings settings = _settingsLoader();
        WordFormulaOptions paneOptions = _optionsProvider.GetFormulaOptions();
        IReadOnlyList<WordLatexParseCandidate> candidates = (await _wordAdapter
                .FindLatexParseCandidatesAsync(all, cancellationToken)
                .ConfigureAwait(true))
            .OrderByDescending(candidate => candidate.Start)
            .ToArray();
        if (candidates.Count == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoParsingTargetsStatus"));
            return;
        }

        int succeeded = 0;
        int failed = 0;

        for (int batchStart = 0; batchStart < candidates.Count; batchStart += BatchFormulaOperationSize)
        {
            WordLatexParseCandidate[] batch = candidates
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            var preparedBatch = new List<(WordLatexParseCandidate Candidate, PreparedWordFormula Prepared)>();
            foreach (WordLatexParseCandidate candidate in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                try
                {
                    LatexTagPreprocessResult preprocessed = LatexTagPreprocessor.Process(
                        candidate.Latex,
                        candidate.DisplayMode == FormulaDisplayMode.Display);
                    if (!preprocessed.Success)
                    {
                        failed++;
                        continue;
                    }

                    FormulaMetadata metadata = CreateParsedFormulaMetadata(
                        candidate,
                        preprocessed,
                        paneOptions,
                        settings);
                    PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                        metadata,
                        includeEquationOoxml: false,
                        cancellationToken,
                        settings.InsertionBackend,
                        reportProgress: false).ConfigureAwait(true);
                    preparedBatch.Add((candidate, prepared));
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    Trace.TraceWarning(
                        "Formula parsing preparation failed: {0}: {1}",
                        exception.GetType().Name,
                        exception.Message);
                    failed++;
                }
            }

            using (_wordAdapter.BeginUndoRecord())
            {
                foreach ((WordLatexParseCandidate candidate, PreparedWordFormula prepared) in preparedBatch)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    try
                    {
                        if (prepared.OlePresentation != null)
                        {
                            await _wordAdapter.ReplaceParsedOleFormulaAsync(
                                candidate,
                                prepared.Metadata,
                                prepared.OlePresentation,
                                cancellationToken).ConfigureAwait(true);
                        }
                        else
                        {
                            await _wordAdapter.ReplaceParsedOmmlFormulaAsync(
                                candidate,
                                prepared.Ooxml!,
                                prepared.Metadata,
                                cancellationToken).ConfigureAwait(true);
                        }

                        succeeded++;
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception exception)
                    {
                        Trace.TraceWarning(
                            "Formula parsing replacement failed at {0}-{1}: {2}: {3}",
                            candidate.Start,
                            candidate.End,
                            exception.GetType().Name,
                            exception.Message);
                        failed++;
                    }
                }
            }

            PostBatchProgress(
                "BatchParsingStatus",
                Math.Min(batchStart + batch.Length, candidates.Count),
                candidates.Count);
        }

        string status = failed == 0
            ? WordAddInText.Get("ParsedStatus")
                .Replace("{count}", succeeded.ToString(CultureInfo.InvariantCulture))
            : WordAddInText.Get("ParsedWithFailuresStatus")
                .Replace("{total}", candidates.Count.ToString(CultureInfo.InvariantCulture))
                .Replace("{succeeded}", succeeded.ToString(CultureInfo.InvariantCulture))
                .Replace("{failed}", failed.ToString(CultureInfo.InvariantCulture));
        _statusSink.Post(failed == 0 ? WordStatusKind.Success : WordStatusKind.Info, status);
    }

    private FormulaMetadata CreateParsedFormulaMetadata(
        WordLatexParseCandidate candidate,
        LatexTagPreprocessResult preprocessed,
        WordFormulaOptions paneOptions,
        WordPluginSettings settings)
    {
        NumberingMode numberingMode = NumberingMode.None;
        string numberText = string.Empty;
        if (candidate.DisplayMode == FormulaDisplayMode.Display)
        {
            if (preprocessed.HasTag)
            {
                numberingMode = NumberingMode.Manual;
                numberText = preprocessed.NumberText!;
            }
            else
            {
                numberingMode = paneOptions.NumberingMode;
                numberText = numberingMode == NumberingMode.Manual
                    ? paneOptions.ManualNumber.Trim()
                    : string.Empty;
                if (numberingMode == NumberingMode.Manual && numberText.Length == 0)
                {
                    numberingMode = NumberingMode.None;
                }
            }
        }

        string latex = MathLiveLatexStyleNormalizer.NormalizeLatex(preprocessed.Latex.Trim());
        latex = ApplyDefaultSourceFormatting(latex, settings.FormulaFontStyle, settings.FormulaColor);
        return new FormulaMetadata(
            new FormulaIdentity(_wordAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            latex,
            candidate.DisplayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            FormulaMetadata.CurrentSchemaVersion,
            settings.FormulaFontScale);
    }
}
