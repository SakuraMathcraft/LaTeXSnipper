using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class PowerPointPluginController
{
    private const int BatchFormulaOperationSize = 5;

    public Task ConvertSelectedToOleAsync(CancellationToken cancellationToken)
    {
        return ConvertSelectedAsync(RenderEngineKind.MathJaxSvg, cancellationToken);
    }

    public Task ConvertSelectedToPngAsync(CancellationToken cancellationToken)
    {
        return ConvertSelectedAsync(RenderEngineKind.Image, cancellationToken);
    }

    public Task FormatSelectedAsync(CancellationToken cancellationToken)
    {
        return FormatAsync(all: false, cancellationToken);
    }

    public Task FormatAllAsync(CancellationToken cancellationToken)
    {
        return FormatAsync(all: true, cancellationToken);
    }

    private async Task ConvertSelectedAsync(RenderEngineKind target, CancellationToken cancellationToken)
    {
        IReadOnlyList<PowerPointFormulaEntry> entries =
            await _powerPointAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken);
        int converted = 0;
        int skipped = 0;
        for (int batchStart = 0; batchStart < entries.Count; batchStart += BatchFormulaOperationSize)
        {
            PowerPointFormulaEntry[] batch = entries
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            foreach (PowerPointFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.Metadata.RenderEngine == target)
                {
                    continue;
                }

                if (!_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId))
                {
                    skipped++;
                    continue;
                }

                if (await ReplaceEntryAsync(entry, WithRenderEngine(entry.Metadata, target), entry.Scale, cancellationToken))
                {
                    converted++;
                }
                else
                {
                    skipped++;
                }
            }

            PostBatchProgress("BatchConvertingStatus", Math.Min(batchStart + batch.Length, entries.Count), entries.Count);
        }

        PostChangedCount(converted, skipped, "ConvertedStatus", "ConvertedWithSkippedStatus", "NoConversionNeededStatus");
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        if (all)
        {
            int resetCount = await _powerPointAdapter.ResetCustomFormulaSizesAsync(cancellationToken);
            PostChangedCount(resetCount, "FormattedStatus", "NoFormattingNeededStatus");
            return;
        }

        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        IReadOnlyList<PowerPointFormulaEntry> entries =
            await _powerPointAdapter.LoadSelectedFormulaEntriesAsync(cancellationToken);
        int formatted = 0;
        int skipped = 0;
        for (int batchStart = 0; batchStart < entries.Count; batchStart += BatchFormulaOperationSize)
        {
            PowerPointFormulaEntry[] batch = entries
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            foreach (PowerPointFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (!NeedsFormatting(entry, settings))
                {
                    continue;
                }

                if (!_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId))
                {
                    skipped++;
                    continue;
                }

                string latex = MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle(
                    MathLiveLatexStyleNormalizer.RemoveColorFormatting(entry.Metadata.Latex),
                    settings.FormulaFontStyle);
                latex = ApplyFormulaColor(latex, settings.FormulaColor);
                FormulaMetadata metadata = new FormulaMetadata(
                    entry.Metadata.Identity,
                    latex,
                    entry.Metadata.DisplayMode,
                    entry.Metadata.NumberingMode,
                    entry.Metadata.NumberText,
                    entry.Metadata.RenderEngine,
                    entry.Metadata.SchemaVersion,
                    settings.FormulaFontScale);
                if (await ReplaceEntryAsync(entry, metadata, scale: 1, cancellationToken))
                {
                    formatted++;
                }
                else
                {
                    skipped++;
                }
            }

            PostBatchProgress("BatchFormattingStatus", Math.Min(batchStart + batch.Length, entries.Count), entries.Count);
        }

        PostChangedCount(formatted, skipped, "FormattedStatus", "FormattedWithSkippedStatus", "NoFormattingNeededStatus");
    }

    private async Task<bool> ReplaceEntryAsync(
        PowerPointFormulaEntry entry,
        FormulaMetadata metadata,
        float scale,
        CancellationToken cancellationToken)
    {
        if (metadata.RenderEngine == RenderEngineKind.MathJaxSvg)
        {
            OlePresentationResult presentation = await RenderOlePresentationAsync(metadata, cancellationToken);
            if (!_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId))
            {
                return false;
            }

            await _powerPointAdapter.DeleteFormulaByIdAsync(entry.Metadata.Identity.EquationId, cancellationToken);
            await _powerPointAdapter.InsertOleFormulaObjectOnSlideAsync(
                entry.SlideIndex,
                metadata,
                presentation,
                entry.Left,
                entry.Top,
                scale,
                cancellationToken);
            return true;
        }

        PowerPointRenderedImage image = await RenderImageAsync(metadata, cancellationToken);
        if (!_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId))
        {
            return false;
        }

        await _powerPointAdapter.DeleteFormulaByIdAsync(entry.Metadata.Identity.EquationId, cancellationToken);
        await _powerPointAdapter.InsertFormulaImageOnSlideAsync(
            entry.SlideIndex,
            image,
            metadata,
            entry.Left,
            entry.Top,
            scale,
            cancellationToken);
        return true;
    }

    private void PostChangedCount(int count, string changedKey, string unchangedKey)
    {
        PostChangedCount(count, skipped: 0, changedKey, skippedKey: changedKey, unchangedKey);
    }

    private void PostChangedCount(int count, int skipped, string changedKey, string skippedKey, string unchangedKey)
    {
        if (count == 0)
        {
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get(unchangedKey));
            return;
        }

        string message = PowerPointAddInText.Get(skipped > 0 ? skippedKey : changedKey)
            .Replace(
                "{count}",
                count.ToString(CultureInfo.InvariantCulture))
            .Replace(
                "{skipped}",
                skipped.ToString(CultureInfo.InvariantCulture));
        _statusSink.Post(
            PowerPointStatusKind.Success,
            message);
    }

    private void PostBatchProgress(string key, int processed, int total)
    {
        _statusSink.Post(
            PowerPointStatusKind.Info,
            PowerPointAddInText.Get(key)
                .Replace("{processed}", processed.ToString(CultureInfo.InvariantCulture))
                .Replace("{total}", total.ToString(CultureInfo.InvariantCulture)));
    }

    private static bool NeedsFormatting(PowerPointFormulaEntry entry, PowerPointPluginSettings settings)
    {
        string colorlessLatex = MathLiveLatexStyleNormalizer.RemoveColorFormatting(entry.Metadata.Latex);
        string formattedLatex = MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle(
            colorlessLatex,
            settings.FormulaFontStyle);
        formattedLatex = ApplyFormulaColor(formattedLatex, settings.FormulaColor);
        return !string.Equals(MathLiveLatexStyleNormalizer.NormalizeLatex(entry.Metadata.Latex), formattedLatex, StringComparison.Ordinal)
            || Math.Abs(entry.Metadata.FontScale - settings.FormulaFontScale) > 0.001
            || Math.Abs(entry.Scale - 1) > 0.01;
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
}
