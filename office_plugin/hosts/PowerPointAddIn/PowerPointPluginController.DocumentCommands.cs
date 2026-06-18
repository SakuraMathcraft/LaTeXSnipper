using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class PowerPointPluginController
{
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
        foreach (PowerPointFormulaEntry entry in entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (entry.Metadata.RenderEngine == target)
            {
                continue;
            }

            await ReplaceEntryAsync(entry, WithRenderEngine(entry.Metadata, target), entry.Scale, cancellationToken);
            converted++;
        }

        PostChangedCount(converted, "ConvertedStatus", "NoConversionNeededStatus");
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
        foreach (PowerPointFormulaEntry entry in entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!NeedsFormatting(entry, settings))
            {
                continue;
            }

            FormulaMetadata metadata = new FormulaMetadata(
                entry.Metadata.Identity,
                MathLiveLatexStyleNormalizer.RemoveColorFormatting(entry.Metadata.Latex),
                entry.Metadata.DisplayMode,
                entry.Metadata.NumberingMode,
                entry.Metadata.NumberText,
                entry.Metadata.RenderEngine,
                entry.Metadata.SchemaVersion,
                settings.FormulaColor,
                settings.FormulaFontStyle,
                settings.FormulaFontScale);
            await ReplaceEntryAsync(entry, metadata, scale: 1, cancellationToken);
            formatted++;
        }

        PostChangedCount(formatted, "FormattedStatus", "NoFormattingNeededStatus");
    }

    private async Task ReplaceEntryAsync(
        PowerPointFormulaEntry entry,
        FormulaMetadata metadata,
        float scale,
        CancellationToken cancellationToken)
    {
        if (metadata.RenderEngine == RenderEngineKind.MathJaxSvg)
        {
            OlePresentationResult presentation = await RenderOlePresentationAsync(metadata, cancellationToken);
            await _powerPointAdapter.DeleteFormulaByIdAsync(entry.Metadata.Identity.EquationId, cancellationToken);
            await _powerPointAdapter.InsertOleFormulaObjectOnSlideAsync(
                entry.SlideIndex,
                metadata,
                presentation,
                entry.Left,
                entry.Top,
                scale,
                cancellationToken);
            return;
        }

        PowerPointRenderedImage image = await RenderImageAsync(metadata, cancellationToken);
        await _powerPointAdapter.DeleteFormulaByIdAsync(entry.Metadata.Identity.EquationId, cancellationToken);
        await _powerPointAdapter.InsertFormulaImageOnSlideAsync(
            entry.SlideIndex,
            image,
            metadata,
            entry.Left,
            entry.Top,
            scale,
            cancellationToken);
    }

    private void PostChangedCount(int count, string changedKey, string unchangedKey)
    {
        if (count == 0)
        {
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get(unchangedKey));
            return;
        }

        _statusSink.Post(
            PowerPointStatusKind.Success,
            PowerPointAddInText.Get(changedKey).Replace(
                "{count}",
                count.ToString(CultureInfo.InvariantCulture)));
    }

    private static bool NeedsFormatting(PowerPointFormulaEntry entry, PowerPointPluginSettings settings)
    {
        return !string.Equals(entry.Metadata.FontColor, settings.FormulaColor, StringComparison.OrdinalIgnoreCase)
            || entry.Metadata.FontStyle != settings.FormulaFontStyle
            || Math.Abs(entry.Metadata.FontScale - settings.FormulaFontScale) > 0.001
            || MathLiveLatexStyleNormalizer.HasColorFormatting(entry.Metadata.Latex)
            || Math.Abs(entry.Scale - 1) > 0.01;
    }
}
