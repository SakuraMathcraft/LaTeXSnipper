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
        return ConvertAsync(all: false, FormulaInsertionBackend.Ole, cancellationToken);
    }

    public Task ConvertAllToOleAsync(CancellationToken cancellationToken)
    {
        return ConvertAsync(all: true, FormulaInsertionBackend.Ole, cancellationToken);
    }

    public Task ConvertSelectedToOmmlAsync(CancellationToken cancellationToken)
    {
        return ConvertAsync(all: false, FormulaInsertionBackend.WordOmml, cancellationToken);
    }

    public Task ConvertAllToOmmlAsync(CancellationToken cancellationToken)
    {
        return ConvertAsync(all: true, FormulaInsertionBackend.WordOmml, cancellationToken);
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

    private async Task ConvertAsync(bool all, FormulaInsertionBackend target, CancellationToken cancellationToken)
    {
        IReadOnlyList<FormulaMetadata> formulas = all
            ? await _wordAdapter.LoadAllFormulasAsync(cancellationToken)
            : await _wordAdapter.LoadSelectedFormulasAsync(cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            foreach (FormulaMetadata formula in formulas)
            {
                cancellationToken.ThrowIfCancellationRequested();
                FormulaMetadata converted = WithRenderEngine(
                    formula,
                    target == FormulaInsertionBackend.Ole ? RenderEngineKind.MathJaxSvg : RenderEngineKind.Omml);
                PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                    converted,
                    includeEquationOoxml: true,
                    cancellationToken,
                    target);
                await UpdatePreparedFormulaAsync(prepared, cancellationToken);
            }
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("ConvertedStatus")
            .Replace("{count}", formulas.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        IReadOnlyList<FormulaMetadata> formulas = all
            ? await _wordAdapter.LoadAllFormulasAsync(cancellationToken)
            : await _wordAdapter.LoadSelectedFormulasAsync(cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            foreach (FormulaMetadata formula in formulas)
            {
                cancellationToken.ThrowIfCancellationRequested();
                FormulaMetadata formatted = WithFormat(
                    formula,
                    new WordFormulaFormat(
                        settings.FormulaColor,
                        settings.FormulaFontStyle,
                        settings.FormulaScale,
                        settings.FormulaWeightPercent));
                FormulaInsertionBackend backend = formula.RenderEngine == RenderEngineKind.MathJaxSvg
                    ? FormulaInsertionBackend.Ole
                    : FormulaInsertionBackend.WordOmml;
                PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
                    formatted,
                    includeEquationOoxml: true,
                    cancellationToken,
                    backend);
                await UpdatePreparedFormulaAsync(prepared, cancellationToken);
            }
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("FormattedStatus")
            .Replace("{count}", formulas.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    }

    private async Task InsertBoundaryAsync(WordNumberingBoundary boundary, CancellationToken cancellationToken)
    {
        using (_wordAdapter.BeginUndoRecord())
        {
            await _wordAdapter.InsertNumberingBoundaryAsync(boundary, cancellationToken);
            await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }
    }

    private static FormulaMetadata WithFormat(FormulaMetadata metadata, WordFormulaFormat format)
    {
        return new FormulaMetadata(
            metadata.Identity,
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            format.Color,
            format.FontStyle,
            format.Scale,
            format.WeightPercent);
    }
}
