using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class PowerPointPluginController
{
    private const int BatchFormulaOperationSize = 5;

    public async Task ConvertSelectedToMathTypeAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        // Capture every target before conversion changes the host selection.
        IReadOnlyList<PowerPointFormulaEditTarget> targets = await _powerPointAdapter.LoadSelectedFormulaTargetsAsync(cancellationToken);
        if (targets.Count == 0) throw new InvalidOperationException(MathTypeText.Get("MathTypeOleRequired"));
        int converted = 0, skipped = 0, failed = 0;
        string? firstFailure = null;
        for (int index = 0; index < targets.Count; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            PowerPointFormulaEditTarget target = targets[index];
            try
            {
                if (target.Metadata.RenderEngine != RenderEngineKind.MathJaxSvg)
                {
                    skipped++;
                    continue;
                }
                string mathMl = await _mathJaxRenderer.ConvertTypographyToMathMlAsync(target.Metadata.Latex,
                    target.Metadata.DisplayMode, target.Metadata.Typography, cancellationToken);
                byte[] native = MathTypeNativeEquation.Create(mathMl, target.Metadata.Typography.FontSizePoints);
                byte[] compoundFile = MathTypeCompoundFile.Create(native);
                OlePresentationResult presentation = await RenderOlePresentationAsync(target.Metadata, cancellationToken);
                await _powerPointAdapter.ReplaceWithMathTypeAsync(target, compoundFile, presentation, cancellationToken);
                converted++;
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception exception)
            {
                failed++;
                firstFailure ??= PowerPointAddInText.GetExceptionMessage(exception);
                Trace.TraceWarning("MathType conversion failed for {0}: {1}", target.Metadata.Identity.EquationId, exception);
            }
            finally
            {
                if ((index + 1) % BatchFormulaOperationSize == 0 || index + 1 == targets.Count)
                    PostBatchProgress("BatchConvertingStatus", index + 1, targets.Count);
            }
        }
        PostBatchResult(targets.Count, converted, skipped, failed, firstFailure,
            "ConvertedStatus", "ConvertedWithSkippedStatus", "ConvertedWithFailuresStatus", "NoConversionNeededStatus");
    }

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
            await _powerPointAdapter.LoadConversionEntriesAsync(target == RenderEngineKind.MathJaxSvg, cancellationToken);
        int converted = 0;
        int skipped = 0;
        int failed = 0;
        string? firstFailure = null;
        for (int batchStart = 0; batchStart < entries.Count; batchStart += BatchFormulaOperationSize)
        {
            PowerPointFormulaEntry[] batch = entries
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            foreach (PowerPointFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                try
                {
                    if (entry.MathTypeTarget is MathTypeFormulaTarget mathType)
                    {
                        MathTypeFormulaContent content = await _powerPointAdapter.ReadMathTypeAsync(mathType, cancellationToken);
                        var imported = new FormulaMetadata(
                            new FormulaIdentity(mathType.DocumentId, Guid.NewGuid().ToString("N")),
                            content.MathMl, FormulaDisplayMode.Display, NumberingMode.None, string.Empty,
                            RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion,
                            PowerPointPluginSettings.Load().Typography.WithFontSize(content.FontSizePoints));
                        OlePresentationResult presentation = await RenderOlePresentationAsync(imported, cancellationToken);
                        await _powerPointAdapter.ReplaceMathTypeWithOleAsync(mathType, imported, presentation, cancellationToken);
                        converted++;
                        continue;
                    }
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
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    failed++;
                    firstFailure ??= PowerPointAddInText.GetExceptionMessage(exception);
                    Trace.TraceWarning("Formula conversion failed on slide {0}, formula {1}: {2}",
                        entry.SlideIndex, entry.MathTypeTarget?.Location.ToString() ?? entry.Metadata.Identity.EquationId, exception);
                }
            }

            PostBatchProgress("BatchConvertingStatus", Math.Min(batchStart + batch.Length, entries.Count), entries.Count);
        }

        PostBatchResult(entries.Count, converted, skipped, failed, firstFailure,
            "ConvertedStatus", "ConvertedWithSkippedStatus", "ConvertedWithFailuresStatus", "NoConversionNeededStatus");
    }

    private async Task FormatAsync(bool all, CancellationToken cancellationToken)
    {
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        IReadOnlyList<PowerPointFormulaEntry> entries =
            await _powerPointAdapter.LoadFormulaEntriesAsync(all, cancellationToken);
        int formatted = 0;
        int skipped = 0;
        int failed = 0;
        string? firstFailure = null;
        for (int batchStart = 0; batchStart < entries.Count; batchStart += BatchFormulaOperationSize)
        {
            PowerPointFormulaEntry[] batch = entries
                .Skip(batchStart)
                .Take(BatchFormulaOperationSize)
                .ToArray();
            foreach (PowerPointFormulaEntry entry in batch)
            {
                cancellationToken.ThrowIfCancellationRequested();
                try
                {
                    if (!NeedsFormatting(entry, settings))
                    {
                        continue;
                    }

                    if (!_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId))
                    {
                        skipped++;
                        continue;
                    }

                    string latex = entry.Metadata.Latex;
                    FormulaMetadata metadata = new FormulaMetadata(
                        entry.Metadata.Identity,
                        latex,
                        entry.Metadata.DisplayMode,
                        entry.Metadata.NumberingMode,
                        entry.Metadata.NumberText,
                        entry.Metadata.RenderEngine,
                        entry.Metadata.SchemaVersion,
                        settings.Typography);
                    if (await ReplaceEntryAsync(entry, metadata, scale: 1, cancellationToken))
                    {
                        formatted++;
                    }
                    else
                    {
                        skipped++;
                    }
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception)
                {
                    failed++;
                    firstFailure ??= PowerPointAddInText.GetExceptionMessage(exception);
                    Trace.TraceWarning("Formula formatting failed on slide {0}, formula {1}: {2}",
                        entry.SlideIndex, entry.Metadata.Identity.EquationId, exception);
                }
            }

            PostBatchProgress("BatchFormattingStatus", Math.Min(batchStart + batch.Length, entries.Count), entries.Count);
        }

        PostBatchResult(entries.Count, formatted, skipped, failed, firstFailure,
            "FormattedStatus", "FormattedWithSkippedStatus", "FormattedWithFailuresStatus", "NoFormattingNeededStatus");
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

    private void PostBatchResult(int total, int count, int skipped, int failed, string? firstFailure,
        string changedKey, string skippedKey, string failedKey, string unchangedKey)
    {
        if (failed > 0)
        {
            string summary = PowerPointAddInText.Get(failedKey)
                .Replace("{total}", total.ToString(CultureInfo.InvariantCulture))
                .Replace("{succeeded}", count.ToString(CultureInfo.InvariantCulture))
                .Replace("{failed}", failed.ToString(CultureInfo.InvariantCulture))
                .Replace("{skipped}", skipped.ToString(CultureInfo.InvariantCulture))
                .Replace("{reason}", firstFailure ?? string.Empty);
            _statusSink.Post(count == 0 ? PowerPointStatusKind.Error : PowerPointStatusKind.Info, summary);
            return;
        }

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
        return !entry.Metadata.Typography.Equals(settings.Typography)
            || Math.Abs(entry.Scale - 1) > 0.01;
    }

}
