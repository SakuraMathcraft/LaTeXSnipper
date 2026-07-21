using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class WordPluginController
{
    private const int BatchFormulaOperationSize = 5;

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
        IReadOnlyList<WordFormulaEntry> formulas = (await _wordAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken))
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

            using (_wordAdapter.BeginUndoRecord())
            {
                foreach ((WordFormulaEntry entry, PreparedWordFormula prepared) in preparedBatch)
                {
                    cancellationToken.ThrowIfCancellationRequested();
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
            }

            PostBatchProgress("BatchConvertingStatus", Math.Min(batchStart + batch.Length, formulas.Count), formulas.Count);
        }

        if (convertedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoConversionNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, BuildChangedStatus("ConvertedStatus", "ConvertedWithSkippedStatus", convertedCount, skippedCount));
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        if (all)
        {
            await ResetAllNaturalSizesAsync(cancellationToken);
            return;
        }

        WordPluginSettings settings = _settingsLoader();
        IReadOnlyList<WordFormulaEntry> formulas = (await _wordAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken))
            .OrderByDescending(item => item.Start)
            .ToArray();
        if (!formulas.Any(entry => !entry.IsNativeWordFormula))
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingTargetsStatus"));
            return;
        }

        int formattedCount = 0;
        int skippedCount = 0;
        for (int batchStart = 0; batchStart < formulas.Count; batchStart += BatchFormulaOperationSize)
        {
            WordFormulaEntry[] batch = formulas
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            var preparedBatch = new List<PreparedWordFormula>();
            foreach (WordFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.IsNativeWordFormula)
                {
                    continue;
                }

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
                    preparedBatch.Add(prepared);
                }
                else
                {
                    PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                        formatted,
                        includeEquationOoxml: true,
                        cancellationToken,
                        FormulaInsertionBackend.WordOmml,
                        reportProgress: false);
                    preparedBatch.Add(prepared);
                }
            }

            using (_wordAdapter.BeginUndoRecord())
            {
                foreach (PreparedWordFormula prepared in preparedBatch)
                {
                    cancellationToken.ThrowIfCancellationRequested();
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
                            cancellationToken);
                    }

                    formattedCount++;
                }
            }

            PostBatchProgress("BatchFormattingStatus", Math.Min(batchStart + batch.Length, formulas.Count), formulas.Count);
        }

        if (formattedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, BuildChangedStatus("FormattedStatus", "FormattedWithSkippedStatus", formattedCount, skippedCount));
    }

    private async Task ResetAllNaturalSizesAsync(CancellationToken cancellationToken)
    {
        WordFormattingResetResult result;
        using (_wordAdapter.BeginUndoRecord())
        {
            result = await _wordAdapter.ResetCustomFormulaSizesAsync(cancellationToken);
        }

        if (result.FormulaCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingTargetsStatus"));
            return;
        }

        if (result.ResetCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingNeededAllStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("FormattedStatus")
            .Replace("{count}", result.ResetCount.ToString(System.Globalization.CultureInfo.InvariantCulture)));
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
        string latex = MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle(
            MathLiveLatexStyleNormalizer.RemoveColorFormatting(metadata.Latex),
            settings.FormulaFontStyle);
        latex = ApplyFormulaColor(latex, settings.FormulaColor);
        return new FormulaMetadata(
            metadata.Identity,
            latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            settings.FormulaFontScale);
    }

    private bool NeedsFormatting(FormulaMetadata metadata, WordPluginSettings settings)
    {
        string colorlessLatex = MathLiveLatexStyleNormalizer.RemoveColorFormatting(metadata.Latex);
        string formattedLatex = MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle(
            colorlessLatex,
            settings.FormulaFontStyle);
        formattedLatex = ApplyFormulaColor(formattedLatex, settings.FormulaColor);
        return !string.Equals(MathLiveLatexStyleNormalizer.NormalizeLatex(metadata.Latex), formattedLatex, StringComparison.Ordinal)
            || Math.Abs(metadata.FontScale - settings.FormulaFontScale) > 0.001
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
            _settingsLoader().FormulaFontScale);
    }

    private static string ApplyFormulaColor(string latex, string fontColor)
    {
        if (MathLiveLatexStyleNormalizer.HasColorFormatting(latex)
            || string.Equals(fontColor, "#000000", StringComparison.OrdinalIgnoreCase))
        {
            return latex;
        }

        return "\\color{" + fontColor + "}{" + latex + "}";
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
}
