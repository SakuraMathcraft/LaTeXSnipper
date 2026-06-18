using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class WordPluginController
{
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

    public Task InsertReferenceAsync(CancellationToken cancellationToken)
    {
        return _wordAdapter.InsertReferencePlaceholderAsync(cancellationToken);
    }

    public Task HandleSelectionChangedAsync(CancellationToken cancellationToken)
    {
        return _wordAdapter.CompletePendingReferenceAsync(cancellationToken);
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
        IReadOnlyList<WordFormulaEntry> formulas = await _wordAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken);
        RenderEngineKind targetEngine = target == FormulaInsertionBackend.Ole
            ? RenderEngineKind.MathJaxSvg
            : RenderEngineKind.Omml;
        int convertedCount = 0;
        using (_wordAdapter.BeginUndoRecord())
        {
            foreach (WordFormulaEntry entry in formulas)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.IsNativeWordFormula)
                {
                    if (target != FormulaInsertionBackend.Ole)
                    {
                        continue;
                    }

                    FormulaMetadata native = CreateMetadataFromNativeWordFormula(entry);
                    PreparedWordFormula nativePrepared = await PrepareRenderedFormulaAsync(
                        native,
                        includeEquationOoxml: false,
                        cancellationToken,
                        FormulaInsertionBackend.Ole);
                    await _wordAdapter.ReplaceNativeWordFormulaWithOleAsync(
                        entry.Start,
                        nativePrepared.Metadata,
                        nativePrepared.OlePresentation!,
                        nativePrepared.Display,
                        cancellationToken);
                    convertedCount++;
                    continue;
                }

                FormulaMetadata formula = entry.Metadata
                    ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
                if (formula.RenderEngine == targetEngine)
                {
                    continue;
                }

                FormulaMetadata converted = WithRenderEngine(formula, targetEngine);
                PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                    converted,
                    includeEquationOoxml: true,
                    cancellationToken,
                    target);
                await UpdatePreparedFormulaAsync(prepared, cancellationToken);
                convertedCount++;
            }
        }

        if (convertedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoConversionNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("ConvertedStatus")
            .Replace("{count}", convertedCount.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("WorkingStatus"));
        if (all)
        {
            await ResetAllNaturalSizesAsync(cancellationToken);
            return;
        }

        WordPluginSettings settings = WordPluginSettings.Load();
        IReadOnlyList<WordFormulaEntry> formulas = await _wordAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken);
        int formattedCount = 0;
        using (_wordAdapter.BeginUndoRecord())
        {
            foreach (WordFormulaEntry entry in formulas)
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

                FormulaMetadata formatted = WithDefaultStyle(formula, settings);
                if (formula.RenderEngine == RenderEngineKind.MathJaxSvg)
                {
                    PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                        formatted,
                        includeEquationOoxml: false,
                        cancellationToken,
                        FormulaInsertionBackend.Ole,
                        reportProgress: false);
                    await _wordAdapter.ResetOleFormulaObjectAsync(
                        formatted.Identity.EquationId,
                        formatted,
                        prepared.OlePresentation!,
                        prepared.Display,
                        cancellationToken);
                }
                else
                {
                    if (formula.FontStyle != settings.FormulaFontStyle)
                    {
                        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                            formatted,
                            includeEquationOoxml: true,
                            cancellationToken,
                            FormulaInsertionBackend.WordOmml,
                            reportProgress: false);
                        await _wordAdapter.UpdateFormulaAsync(
                            formatted.Identity.EquationId,
                            prepared.Ooxml!,
                            prepared.EquationOoxml!,
                            formatted,
                            prepared.Display,
                            cancellationToken);
                    }
                    else
                    {
                        await _wordAdapter.ResetManagedEquationFormattingAsync(formatted, cancellationToken);
                    }
                }

                _currentFormula = formatted;
                formattedCount++;
            }
        }

        if (formattedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("FormattedStatus")
            .Replace("{count}", formattedCount.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    private async Task ResetAllNaturalSizesAsync(CancellationToken cancellationToken)
    {
        int formattedCount;
        using (_wordAdapter.BeginUndoRecord())
        {
            formattedCount = await _wordAdapter.ResetCustomFormulaSizesAsync(cancellationToken);
        }

        if (formattedCount == 0)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("NoFormattingNeededStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("FormattedStatus")
            .Replace("{count}", formattedCount.ToString(System.Globalization.CultureInfo.InvariantCulture)));
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
        return new FormulaMetadata(
            metadata.Identity,
            MathLiveLatexStyleNormalizer.RemoveColorFormatting(metadata.Latex),
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            settings.FormulaColor,
            settings.FormulaFontStyle,
            settings.FormulaFontScale);
    }

    private bool NeedsFormatting(FormulaMetadata metadata, WordPluginSettings settings)
    {
        return !string.Equals(metadata.FontColor, settings.FormulaColor, StringComparison.OrdinalIgnoreCase)
            || metadata.FontStyle != settings.FormulaFontStyle
            || Math.Abs(metadata.FontScale - settings.FormulaFontScale) > 0.001
            || MathLiveLatexStyleNormalizer.HasColorFormatting(metadata.Latex)
            || _wordAdapter.HasCustomFormulaScale(metadata);
    }

    private static FormulaMetadata CreateMetadataFromNativeWordFormula(WordFormulaEntry entry)
    {
        return new FormulaMetadata(
            new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            entry.NativeMathMl,
            entry.NativeDisplayMode,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.MathJaxSvg,
            schemaVersion: 1,
            "#000000",
            FormulaFontStyle.TeX,
            WordPluginSettings.Load().FormulaFontScale);
    }
}
