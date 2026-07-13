using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task<int> ResetCustomFormulaSizesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        int resetCount = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            var equationControls = new List<object>();
            dynamic controls = CurrentDocument.ContentControls;
            int controlCount = Convert.ToInt32(controls.Count);
            for (int index = 1; index <= controlCount; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic control = controls.Item(index);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (IsEquationControl(control))
                {
                    equationControls.Add(control);
                }
            }

            foreach (object candidate in equationControls)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic control = candidate;
                if (!WordFormulaMetadataStore.TryLoadOmmlNaturalFontSize(
                    control,
                    out double expectedSize))
                {
                    continue;
                }

                double actualSize = ReadManagedEquationFontSize(control);
                if (Math.Abs(actualSize - expectedSize) <= 0.1)
                {
                    continue;
                }

                TryCom(() => control.Range.Font.Size = expectedSize);

                resetCount++;
            }

            dynamic inlineShapes = CurrentDocument.InlineShapes;
            int shapeCount = Convert.ToInt32(inlineShapes.Count);
            for (int index = 1; index <= shapeCount; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic inlineShape = inlineShapes.Item(index);
                string equationId = GetOleInlineShapeEquationId(inlineShape);
                if (string.IsNullOrWhiteSpace(equationId))
                {
                    continue;
                }

                if (!WordFormulaMetadataStore.TryLoadOleNaturalSize(
                        inlineShape,
                        out double naturalWidth,
                        out double naturalHeight))
                {
                    continue;
                }

                double width = Convert.ToDouble(inlineShape.Width);
                double height = Convert.ToDouble(inlineShape.Height);
                if (Math.Abs(width / naturalWidth - 1) <= 0.01 &&
                    Math.Abs(height / naturalHeight - 1) <= 0.01)
                {
                    continue;
                }

                SetOleInlineShapeSize(inlineShape, (float)naturalWidth, (float)naturalHeight);

                resetCount++;
            }
        });

        return Task.FromResult(resetCount);
    }

    public System.Threading.Tasks.Task ResetManagedEquationFormattingAsync(
        LaTeXSnipper.OfficePlugin.Abstractions.FormulaMetadata metadata,
        System.Threading.CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic control = FindFormulaControlById(metadata.Identity.EquationId);
            double fontSize = ScaleFontSize(ReadSurroundingTextFontSize(control), metadata.FontScale);
            ApplyManagedEquationFontSizeById(metadata.Identity.EquationId, fontSize);
            ApplyManagedEquationStyleById(metadata);
            NormalizeManagedInlineEquationBaseline(metadata, control);
            SaveFormulaMetadata(metadata);
        });
        return System.Threading.Tasks.Task.CompletedTask;
    }

    private double ReadSurroundingTextFontSize(dynamic control)
    {
        dynamic paragraph = control.Range.Paragraphs.Item(1).Range;
        int paragraphStart = GetRangeStart(paragraph);
        int paragraphEnd = Math.Max(paragraphStart, GetRangeEnd(paragraph) - 1);
        int formulaStart = GetRangeStart(control.Range);
        int formulaEnd = GetRangeEnd(control.Range);
        if (formulaStart > paragraphStart)
        {
            double before = ReadPointSize(CreateDocumentRange(formulaStart - 1, formulaStart).Font.Size);
            if (before > 0)
            {
                return before;
            }
        }

        if (formulaEnd < paragraphEnd)
        {
            double after = ReadPointSize(CreateDocumentRange(formulaEnd, formulaEnd + 1).Font.Size);
            if (after > 0)
            {
                return after;
            }
        }

        return GetCurrentFontSizePoints();
    }

    private void ResetSelectionFormulaTextFormatting()
    {
        TryCom(() => _wordApplication.Selection.Font.Position = 0);
        TryCom(() => _wordApplication.Selection.Font.Superscript = 0);
        TryCom(() => _wordApplication.Selection.Font.Subscript = 0);
    }

    private void NormalizePlainTextBaselineAroundRange(dynamic anchorRange)
    {
        try
        {
            NormalizePlainTextBaselineInParagraph(anchorRange.Paragraphs.Item(1).Range);
        }
        catch
        {
        }
    }

    private void NormalizeManagedInlineEquationBaseline(FormulaMetadata metadata, object contentControl)
    {
        if (metadata.DisplayMode != FormulaDisplayMode.Inline || metadata.NumberingMode != NumberingMode.None)
        {
            return;
        }

        ResetManagedEquationBaseline(contentControl);
        NormalizePlainTextBaselineAroundRange(((dynamic)contentControl).Range);
    }

    private void NormalizePlainTextBaselineInParagraph(dynamic paragraphRange)
    {
        int paragraphStart = GetRangeStart(paragraphRange);
        int paragraphEnd = Math.Max(paragraphStart, GetRangeEnd(paragraphRange) - 1);
        if (paragraphEnd <= paragraphStart)
        {
            return;
        }

        List<ManagedRangeSpan> managedSpans = LoadManagedFormulaSpans(paragraphRange, paragraphStart, paragraphEnd);
        managedSpans.Sort((left, right) => left.Start.CompareTo(right.Start));
        int plainStart = paragraphStart;
        foreach (ManagedRangeSpan span in managedSpans)
        {
            int spanStart = Math.Max(paragraphStart, span.Start);
            int spanEnd = Math.Min(paragraphEnd, span.End);
            if (spanStart > plainStart)
            {
                ResetPlainTextBaseline(CreateDocumentRange(plainStart, spanStart));
            }

            plainStart = Math.Max(plainStart, spanEnd);
        }

        if (plainStart < paragraphEnd)
        {
            ResetPlainTextBaseline(CreateDocumentRange(plainStart, paragraphEnd));
        }
    }

    private List<ManagedRangeSpan> LoadManagedFormulaSpans(dynamic paragraphRange, int paragraphStart, int paragraphEnd)
    {
        var spans = new List<ManagedRangeSpan>();
        try
        {
            dynamic controls = paragraphRange.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (!IsManagedControl(control))
                {
                    continue;
                }

                AddManagedSpanIfInParagraph(spans, control.Range, paragraphStart, paragraphEnd);
            }
        }
        catch
        {
        }

        try
        {
            dynamic inlineShapes = paragraphRange.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic inlineShape = inlineShapes.Item(i);
                if (string.IsNullOrWhiteSpace(GetOleInlineShapeEquationId(inlineShape)))
                {
                    continue;
                }

                AddManagedSpanIfInParagraph(spans, inlineShape.Range, paragraphStart, paragraphEnd);
            }
        }
        catch
        {
        }

        return spans;
    }

    private static void AddManagedSpanIfInParagraph(List<ManagedRangeSpan> spans, dynamic range, int paragraphStart, int paragraphEnd)
    {
        int start = GetRangeStart(range);
        int end = GetRangeEnd(range);
        if (RangesOverlap(paragraphStart, paragraphEnd, start, end))
        {
            spans.Add(new ManagedRangeSpan(start, end));
        }
    }

    private static void ResetPlainTextBaseline(dynamic range)
    {
        TryCom(() => range.Font.Position = 0);
        TryCom(() => range.Font.Superscript = 0);
        TryCom(() => range.Font.Subscript = 0);
    }

    private void ApplyManagedEquationStyleById(LaTeXSnipper.OfficePlugin.Abstractions.FormulaMetadata metadata)
    {
        try
        {
            ApplyManagedEquationStyle(FindFormulaControlById(metadata.Identity.EquationId), metadata);
        }
        catch
        {
        }
    }

    private static void ApplyManagedEquationStyle(object contentControl, FormulaMetadata metadata)
    {
        dynamic control = contentControl;
        string originalTag = ReadControlTag(control);
        RestoreManagedEquationControlIdentity(control, originalTag, metadata.Identity.EquationId);
    }

    private static void RestoreManagedEquationControlIdentity(dynamic control, string originalTag, string equationId)
    {
        string tag = string.Equals(
            WordFormulaMetadataStore.EquationIdFromTag(originalTag),
            equationId,
            StringComparison.Ordinal)
            ? originalTag
            : WordFormulaMetadataStore.BuildEquationTag(equationId);
        TryCom(() => control.Tag = tag);
        TryCom(() => control.Title = "LaTeXSnipper Equation");
    }

}
