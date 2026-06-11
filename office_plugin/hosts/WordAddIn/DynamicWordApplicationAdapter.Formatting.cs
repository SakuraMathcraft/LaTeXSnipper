using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
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

    private void NormalizePlainTextBaselineByFormulaId(string equationId)
    {
        try
        {
            NormalizePlainTextBaselineAroundRange(((dynamic)FindFormulaControlById(equationId)).Range);
        }
        catch
        {
        }
    }

    private void NormalizePlainTextBaselineInParagraph(dynamic paragraphRange)
    {
        int paragraphStart = GetRangeStart(paragraphRange);
        int paragraphEnd = Math.Max(paragraphStart, GetRangeEnd(paragraphRange) - 1);
        if (paragraphEnd <= paragraphStart)
        {
            return;
        }

        List<ManagedRangeSpan> managedSpans = LoadManagedFormulaSpans(paragraphStart, paragraphEnd);
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

    private List<ManagedRangeSpan> LoadManagedFormulaSpans(int paragraphStart, int paragraphEnd)
    {
        var spans = new List<ManagedRangeSpan>();
        try
        {
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
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
            dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
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
            dynamic control = FindFormulaControlById(metadata.Identity.EquationId);
            TryCom(() => control.Range.Font.Bold =
                metadata.FontStyle == LaTeXSnipper.OfficePlugin.Abstractions.FormulaFontStyle.Bold
                || metadata.FontWeightPercent > 0
                    ? -1
                    : 0);
            TryCom(() => control.Range.Font.Italic =
                metadata.FontStyle == LaTeXSnipper.OfficePlugin.Abstractions.FormulaFontStyle.Italic
                    ? -1
                    : 0);
            TryCom(() => control.Range.Font.Color = ParseWordColor(metadata.FontColor));
        }
        catch
        {
        }
    }

    private static int ParseWordColor(string color)
    {
        string value = (color ?? string.Empty).Trim().TrimStart('#');
        if (value.Length != 6 || !int.TryParse(value, System.Globalization.NumberStyles.HexNumber, null, out int rgb))
        {
            return 0;
        }

        int red = (rgb >> 16) & 0xff;
        int green = (rgb >> 8) & 0xff;
        int blue = rgb & 0xff;
        return red | (green << 8) | (blue << 16);
    }
}
