using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class WordPluginController
{
    private const int BatchFormulaOperationSize = 5;

    public async Task ConvertSelectedToMathTypeAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        // Capture every target before conversion changes the host selection.
        IReadOnlyList<WordFormulaEditTarget> targets = await _wordAdapter.LoadSelectedFormulaTargetsAsync(cancellationToken);
        if (targets.Count == 0) throw new InvalidOperationException(MathTypeText.Get("MathTypeOleRequired"));
        int converted = 0, skipped = 0, failed = 0;
        string? firstFailure = null;
        for (int index = 0; index < targets.Count; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            WordFormulaEditTarget target = targets[index];
            try
            {
                if (!target.IsOle || target.Metadata.NumberingMode != NumberingMode.None)
                {
                    skipped++;
                    continue;
                }
                string mathMl = await _mathJaxRenderer.ConvertTypographyToMathMlAsync(target.Metadata.Latex,
                    target.Metadata.DisplayMode, target.Metadata.Typography, cancellationToken);
                await _wordAdapter.ReplaceWithMathTypeAsync(target, mathMl, cancellationToken);
                converted++;
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception exception)
            {
                failed++;
                firstFailure ??= WordAddInText.GetExceptionMessage(exception);
                Trace.TraceWarning("MathType conversion failed for {0}: {1}", target.Metadata.Identity.EquationId, exception);
            }
            finally
            {
                if ((index + 1) % BatchFormulaOperationSize == 0 || index + 1 == targets.Count)
                    PostBatchProgress("BatchConvertingStatus", index + 1, targets.Count);
            }
        }
        if (failed > 0)
            PostBatchFailures("ConvertedWithFailuresStatus", targets.Count, converted, failed, skipped, firstFailure!);
        else
            _statusSink.Post(converted == 0 ? WordStatusKind.Info : WordStatusKind.Success,
                converted == 0 ? WordAddInText.Get("NoConversionNeededStatus")
                    : BuildChangedStatus("ConvertedStatus", "ConvertedWithSkippedStatus", converted, skipped));
    }

    public Task ConvertSelectedToOleAsync(CancellationToken cancellationToken)
    {
        return ConvertSelectedAsync(FormulaInsertionBackend.Ole, cancellationToken);
    }

    public Task ConvertSelectedToOmmlAsync(CancellationToken cancellationToken)
    {
        return ConvertSelectedAsync(FormulaInsertionBackend.WordOmml, cancellationToken);
    }

    public Task FormatSelectedAsync(CancellationToken cancellationToken)
    {
        return FormatAsync(all: false, cancellationToken);
    }

    public Task FormatAllAsync(CancellationToken cancellationToken)
    {
        return FormatAsync(all: true, cancellationToken);
    }

    public async Task InsertReferenceAsync(CancellationToken cancellationToken)
    {
        await _wordAdapter.InsertReferencePlaceholderAsync(cancellationToken);
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("ReferencePlaceholderStatus"));
    }

    public async Task HandleSelectionChangedAsync(CancellationToken cancellationToken)
    {
        bool completed = await _wordAdapter.CompletePendingReferenceAsync(cancellationToken);
        if (completed)
        {
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("ReferenceInsertedStatus"));
        }
    }

    public Task InsertChapterBoundaryAsync(CancellationToken cancellationToken)
    {
        return InsertBoundaryAsync(WordNumberingBoundary.Chapter, cancellationToken);
    }

    public Task InsertSectionBoundaryAsync(CancellationToken cancellationToken)
    {
        return InsertBoundaryAsync(WordNumberingBoundary.Section, cancellationToken);
    }

    private async Task ConvertSelectedAsync(FormulaInsertionBackend target, CancellationToken cancellationToken)
    {
        IReadOnlyList<WordFormulaEntry> formulas = (await _wordAdapter.LoadConversionEntriesAsync(target == FormulaInsertionBackend.Ole, cancellationToken))
            .OrderByDescending(item => item.Start)
            .ToArray();
        int targetCount = formulas.Count(entry => !entry.IsNativeWordFormula || target == FormulaInsertionBackend.Ole);
        if (targetCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoConversionTargetsStatus"));
            return;
        }

        RenderEngineKind targetEngine = target == FormulaInsertionBackend.Ole
            ? RenderEngineKind.MathJaxSvg
            : RenderEngineKind.Omml;
        int convertedCount = 0;
        int skippedCount = 0;
        int failedCount = 0;
        string? firstFailure = null;
        void RecordFailure(int start, string stage, Exception exception)
        {
            failedCount++;
            firstFailure ??= WordAddInText.GetExceptionMessage(exception);
            Trace.TraceWarning("Formula conversion {0} failed at {1}: {2}", stage, start, exception);
        }

        for (int batchStart = 0; batchStart < formulas.Count; batchStart += BatchFormulaOperationSize)
        {
            WordFormulaEntry[] batch = formulas
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            var preparedBatch = new List<(WordFormulaEntry Entry, PreparedWordFormula Prepared)>();
            foreach (WordFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                try
                {
                    if (entry.MathTypeTarget is MathTypeFormulaTarget mathType)
                    {
                        string mathMl = await _wordAdapter.ReadMathTypeMathMlAsync(mathType, cancellationToken);
                        var imported = new FormulaMetadata(
                            new FormulaIdentity(mathType.DocumentId, Guid.NewGuid().ToString("N")),
                            mathMl, FormulaDisplayMode.Inline, NumberingMode.None, string.Empty,
                            RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, _settingsLoader().Typography);
                        PreparedWordFormula importedPrepared = await PrepareRenderedFormulaAsync(imported,
                            includeEquationOoxml: false, cancellationToken, FormulaInsertionBackend.Ole, reportProgress: false);
                        preparedBatch.Add((entry, importedPrepared));
                        continue;
                    }
                    if (entry.IsNativeWordFormula)
                    {
                        if (target != FormulaInsertionBackend.Ole)
                        {
                            continue;
                        }

                        if (!_wordAdapter.ContainsNativeWordFormula(entry.Start))
                        {
                            skippedCount++;
                            continue;
                        }

                        FormulaMetadata native = CreateMetadataFromNativeWordFormula(entry);
                        PreparedWordFormula nativePrepared = await PrepareRenderedFormulaAsync(
                            native,
                            includeEquationOoxml: false,
                            cancellationToken,
                            FormulaInsertionBackend.Ole,
                            reportProgress: false);
                        preparedBatch.Add((entry, nativePrepared));
                        continue;
                    }

                    FormulaMetadata formula = entry.Metadata
                        ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
                    if (formula.RenderEngine == targetEngine)
                    {
                        continue;
                    }

                    if (!_wordAdapter.ContainsFormula(formula.Identity.EquationId))
                    {
                        skippedCount++;
                        continue;
                    }

                    FormulaMetadata converted = WithRenderEngine(formula, targetEngine);
                    PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                        converted,
                        includeEquationOoxml: true,
                        cancellationToken,
                        target,
                        reportProgress: false);
                    preparedBatch.Add((entry, prepared));
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    RecordFailure(entry.Start, "preparation", exception);
                }
            }

            using (_wordAdapter.BeginUndoRecord())
            {
                foreach ((WordFormulaEntry entry, PreparedWordFormula prepared) in preparedBatch)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    try
                    {
                        if (entry.MathTypeTarget is MathTypeFormulaTarget mathType)
                        {
                            await _wordAdapter.ReplaceMathTypeWithOleAsync(mathType, prepared.Metadata, prepared.OlePresentation!, cancellationToken);
                            convertedCount++;
                            continue;
                        }
                        if (entry.IsNativeWordFormula)
                        {
                            if (!_wordAdapter.ContainsNativeWordFormula(entry.Start))
                            {
                                skippedCount++;
                                continue;
                            }

                            await _wordAdapter.ReplaceNativeWordFormulaWithOleAsync(
                                entry.Start,
                                prepared.Metadata,
                                prepared.OlePresentation!,
                                prepared.Display,
                                cancellationToken);
                            convertedCount++;
                            continue;
                        }

                        string equationId = prepared.Metadata.Identity.EquationId;
                        if (!_wordAdapter.ContainsFormula(equationId))
                        {
                            skippedCount++;
                            continue;
                        }

                        await UpdatePreparedFormulaAsync(prepared, cancellationToken, reportStatus: false);
                        convertedCount++;
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception exception)
                    {
                        RecordFailure(entry.Start, "replacement", exception);
                    }
                }
            }

            PostBatchProgress("BatchConvertingStatus", Math.Min(batchStart + batch.Length, formulas.Count), formulas.Count);
        }

        if (failedCount > 0)
        {
            PostBatchFailures("ConvertedWithFailuresStatus", targetCount, convertedCount, failedCount, skippedCount, firstFailure!);
            return;
        }
        else if (convertedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoConversionNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, BuildChangedStatus("ConvertedStatus", "ConvertedWithSkippedStatus", convertedCount, skippedCount));
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        WordPluginSettings settings = _settingsLoader();
        IReadOnlyList<WordFormulaEntry> formulas = (await _wordAdapter.LoadFormulaEntriesAsync(all, cancellationToken))
            .OrderByDescending(item => item.Start)
            .ToArray();
        if (!formulas.Any(entry => !entry.IsNativeWordFormula))
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingTargetsStatus"));
            return;
        }

        int formattedCount = 0;
        int skippedCount = 0;
        int failedCount = 0;
        string? firstFailure = null;
        void RecordFailure(int start, string stage, Exception exception)
        {
            failedCount++;
            firstFailure ??= WordAddInText.GetExceptionMessage(exception);
            Trace.TraceWarning("Formula formatting {0} failed at {1}: {2}", stage, start, exception);
        }

        for (int batchStart = 0; batchStart < formulas.Count; batchStart += BatchFormulaOperationSize)
        {
            WordFormulaEntry[] batch = formulas
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            var preparedBatch = new List<(WordFormulaEntry Entry, PreparedWordFormula Prepared)>();
            foreach (WordFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.IsNativeWordFormula)
                {
                    continue;
                }

                try
                {
                    FormulaMetadata formula = entry.Metadata
                        ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
                    if (!NeedsFormatting(formula, settings))
                    {
                        continue;
                    }

                    if (!_wordAdapter.ContainsFormula(formula.Identity.EquationId))
                    {
                        skippedCount++;
                        continue;
                    }

                    FormulaMetadata formatted = WithDefaultStyle(formula, settings);
                    if (formula.RenderEngine == RenderEngineKind.MathJaxSvg)
                    {
                        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                            formatted,
                            includeEquationOoxml: false,
                            cancellationToken,
                            FormulaInsertionBackend.Ole,
                            reportProgress: false);
                        preparedBatch.Add((entry, prepared));
                    }
                    else
                    {
                        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                            formatted,
                            includeEquationOoxml: true,
                            cancellationToken,
                            FormulaInsertionBackend.WordOmml,
                            reportProgress: false);
                        preparedBatch.Add((entry, prepared));
                    }
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    RecordFailure(entry.Start, "preparation", exception);
                }
            }

            using (_wordAdapter.BeginUndoRecord())
            {
                foreach ((WordFormulaEntry entry, PreparedWordFormula prepared) in preparedBatch)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    try
                    {
                        FormulaMetadata formatted = prepared.Metadata;
                        if (!_wordAdapter.ContainsFormula(formatted.Identity.EquationId))
                        {
                            skippedCount++;
                            continue;
                        }

                        if (formatted.RenderEngine == RenderEngineKind.MathJaxSvg)
                        {
                            await _wordAdapter.ResetOleFormulaObjectAsync(
                                formatted.Identity.EquationId,
                                formatted,
                                prepared.OlePresentation!,
                                prepared.Display,
                                cancellationToken);
                        }
                        else
                        {
                            await _wordAdapter.UpdateFormulaAsync(
                                formatted.Identity.EquationId,
                                prepared.Ooxml!,
                                prepared.EquationOoxml!,
                                prepared.EquationContentOoxml!,
                                formatted,
                                prepared.Display,
                                cancellationToken, preserveUserScale: false);
                        }

                        formattedCount++;
                    }
                    catch (OperationCanceledException)
                    {
                        throw;
                    }
                    catch (Exception exception)
                    {
                        RecordFailure(entry.Start, "replacement", exception);
                    }
                }
            }

            PostBatchProgress("BatchFormattingStatus", Math.Min(batchStart + batch.Length, formulas.Count), formulas.Count);
        }

        if (failedCount > 0)
        {
            PostBatchFailures("FormattedWithFailuresStatus", formulas.Count, formattedCount, failedCount, skippedCount, firstFailure!);
            return;
        }
        else if (formattedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, BuildChangedStatus("FormattedStatus", "FormattedWithSkippedStatus", formattedCount, skippedCount));
    }

    private async Task InsertBoundaryAsync(WordNumberingBoundary boundary, CancellationToken cancellationToken)
    {
        using (_wordAdapter.BeginUndoRecord())
        {
            await _wordAdapter.InsertNumberingBoundaryAsync(boundary, cancellationToken);
            await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("BoundaryInsertedStatus"));
    }

    private static FormulaMetadata WithDefaultStyle(FormulaMetadata metadata, WordPluginSettings settings)
    {
        string latex = metadata.Latex;
        return new FormulaMetadata(
            metadata.Identity,
            latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            settings.Typography);
    }

    private bool NeedsFormatting(FormulaMetadata metadata, WordPluginSettings settings)
    {
        return !metadata.Typography.Equals(settings.Typography)
            || _wordAdapter.HasCustomFormulaScale(metadata);
    }

    private FormulaMetadata CreateMetadataFromNativeWordFormula(WordFormulaEntry entry)
    {
        return new FormulaMetadata(
            new FormulaIdentity(_wordAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            entry.NativeMathMl,
            entry.NativeDisplayMode,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.MathJaxSvg,
            schemaVersion: FormulaMetadata.CurrentSchemaVersion,
            _settingsLoader().Typography);
    }

    private void PostBatchProgress(string key, int processed, int total)
    {
        _statusSink.Post(
            WordStatusKind.Info,
            WordAddInText.Get(key)
                .Replace("{processed}", processed.ToString(System.Globalization.CultureInfo.InvariantCulture))
                .Replace("{total}", total.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    private static string BuildChangedStatus(string changedKey, string skippedKey, int changed, int skipped)
    {
        string message = WordAddInText.Get(skipped > 0 ? skippedKey : changedKey)
            .Replace("{count}", changed.ToString(System.Globalization.CultureInfo.InvariantCulture));
        return message.Replace("{skipped}", skipped.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private void PostBatchFailures(string key, int total, int succeeded, int failed, int skipped, string reason)
    {
        string message = WordAddInText.Get(key)
            .Replace("{total}", total.ToString(System.Globalization.CultureInfo.InvariantCulture))
            .Replace("{succeeded}", succeeded.ToString(System.Globalization.CultureInfo.InvariantCulture))
            .Replace("{failed}", failed.ToString(System.Globalization.CultureInfo.InvariantCulture))
            .Replace("{skipped}", skipped.ToString(System.Globalization.CultureInfo.InvariantCulture))
            .Replace("{reason}", reason);
        _statusSink.Post(succeeded == 0 ? WordStatusKind.Error : WordStatusKind.Info, message);
    }
}
