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
            var numberControls = new Dictionary<string, object>(StringComparer.Ordinal);
            var equationControls = new List<object>();
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
            int controlCount = Convert.ToInt32(controls.Count);
            for (int index = 1; index <= controlCount; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic control = controls.Item(index);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                string numberEquationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
                if (!string.IsNullOrWhiteSpace(numberEquationId))
                {
                    numberControls[numberEquationId] = control;
                }
                else if (IsEquationControl(control))
                {
                    equationControls.Add(control);
                }
            }

            foreach (object candidate in equationControls)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic control = candidate;
                string equationId = GetEquationId(control);
                if (!WordFormulaMetadataStore.TryLoadOmmlNaturalFontSize(
                    _wordApplication.ActiveDocument,
                    equationId,
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
                if (numberControls.TryGetValue(equationId, out object numberControl))
                {
                    FormulaMetadata metadata = WordFormulaMetadataStore.Load(
                        _wordApplication.ActiveDocument,
                        equationId);
                    ApplyNumberControlVerticalAlignment(numberControl, metadata);
                }

                resetCount++;
            }

            dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
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
                        _wordApplication.ActiveDocument,
                        equationId,
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
                if (numberControls.TryGetValue(equationId, out object numberControl))
                {
                    FormulaMetadata metadata = WordFormulaMetadataStore.Load(
                        _wordApplication.ActiveDocument,
                        equationId);
                    ApplyNumberControlVerticalAlignment(numberControl, metadata, naturalHeight);
                }

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
            double fontSize = ReadSurroundingTextFontSize(control);
            ApplyManagedEquationFontSizeById(metadata.Identity.EquationId, fontSize);
            WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                _wordApplication.ActiveDocument,
                metadata.Identity.EquationId,
                fontSize);
            ApplyManagedEquationStyleById(metadata);
            ApplyNumberControlVerticalAlignmentById(metadata);
            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
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
            ApplyManagedEquationStyle(FindFormulaControlById(metadata.Identity.EquationId), metadata);
        }
        catch
        {
        }
    }

    private static void ApplyManagedEquationStyle(object contentControl, FormulaMetadata metadata)
    {
        dynamic control = contentControl;
        TryCom(() => control.Range.Font.Bold = metadata.FontStyle == FormulaFontStyle.Bold ? -1 : 0);
        TryCom(() => control.Range.Font.Italic = metadata.FontStyle == FormulaFontStyle.Italic ? -1 : 0);
        int color = ParseWordColor(metadata.FontColor);
        TryCom(() => control.Range.Font.Color = color);
        dynamic equations = control.Range.OMaths;
        int equationCount = Convert.ToInt32(equations.Count);
        for (int index = 1; index <= equationCount; index++)
        {
            dynamic equation = equations.Item(index);
            TryCom(() => equation.Range.Font.Color = color);
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
