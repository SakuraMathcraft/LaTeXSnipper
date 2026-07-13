using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void SaveFormulaMetadata(FormulaMetadata metadata)
    {
        object? equationControl = TryGetEquationControlById(metadata.Identity.EquationId);
        if (equationControl != null)
        {
            SaveFormulaMetadata(equationControl, metadata);
            return;
        }

        object? inlineShape = TryFindOleInlineShapeById(metadata.Identity.EquationId);
        if (inlineShape == null)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        SaveFormulaMetadata(inlineShape, metadata);
    }

    private void SaveFormulaMetadata(object formulaObject, FormulaMetadata metadata)
    {
        dynamic shape = formulaObject;
        if (metadata.RenderEngine == RenderEngineKind.Omml)
        {
            double naturalFontSize = ReadManagedEquationFontSize(formulaObject);
            WordFormulaMetadataStore.SaveOmml(shape, metadata, naturalFontSize);
            FormulaMetadata stored = WordFormulaMetadataStore.LoadOmml(shape);
            if (!string.Equals(
                    stored.Identity.EquationId,
                    metadata.Identity.EquationId,
                    StringComparison.Ordinal))
            {
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
            }

            return;
        }

        if (!WordFormulaMetadataStore.TryLoadOleNaturalSize(
                shape,
                out double naturalWidth,
                out double naturalHeight))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        WordFormulaMetadataStore.SaveOle(
            shape,
            metadata,
            naturalWidth,
            naturalHeight);
    }

    private FormulaMetadata LoadFormulaMetadata(
        dynamic control,
        string equationId,
        RenderEngineKind actualRenderEngine)
    {
        FormulaMetadata metadata = actualRenderEngine == RenderEngineKind.Omml
            ? WordFormulaMetadataStore.LoadOmml(control)
            : WordFormulaMetadataStore.LoadOle(control);
        if (!string.Equals(metadata.Identity.EquationId, equationId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        if (metadata.RenderEngine != actualRenderEngine)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return metadata;
    }

    private static FormulaMetadata WithRenderEngine(FormulaMetadata metadata, RenderEngineKind renderEngine)
    {
        return new FormulaMetadata(
            metadata.Identity,
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            renderEngine,
            metadata.SchemaVersion,
            metadata.FontScale);
    }

    private static FormulaMetadata WithNewIdentity(FormulaMetadata metadata, string documentId)
    {
        return new FormulaMetadata(
            new FormulaIdentity(documentId, Guid.NewGuid().ToString("N")),
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            metadata.FontScale);
    }

    private static string ReadControlTag(dynamic control)
    {
        try
        {
            return Convert.ToString(control.Tag) ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private object? TryGetEquationControlById(string equationId)
    {
        try
        {
            dynamic controls = CurrentDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (GetEquationControlId(control) == equationId)
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private dynamic CreateDocumentRange(int start, int end)
    {
        try
        {
            return CurrentDocument.Range(start, end);
        }
        catch
        {
            return CurrentDocument.Range(Math.Max(0, start - 1), Math.Max(0, end - 1));
        }
    }

    private int ClampDocumentPosition(int position)
    {
        try
        {
            int documentStart = Convert.ToInt32(CurrentDocument.Content.Start);
            int documentEnd = Convert.ToInt32(CurrentDocument.Content.End);
            return Math.Min(Math.Max(position, documentStart), documentEnd);
        }
        catch
        {
            return Math.Max(0, position);
        }
    }

    private static int GetRangeEnd(dynamic range)
    {
        return Convert.ToInt32(range.End);
    }

    private static int GetRangeStart(dynamic range)
    {
        return Convert.ToInt32(range.Start);
    }

    private static bool RangesOverlap(int leftStart, int leftEnd, int rightStart, int rightEnd)
    {
        return leftStart < rightEnd && leftEnd > rightStart;
    }

    private static bool IsCollapsedRange(dynamic range)
    {
        try
        {
            return Convert.ToInt32(range.Start) == Convert.ToInt32(range.End);
        }
        catch
        {
            return false;
        }
    }

    private static bool RangeTouchesManagedFormula(dynamic range)
    {
        return TryGetParentContentControl(range) != null
            || TryGetFirstManagedContentControl(range) != null;
    }

    private bool RangeIntersectsManagedFormula(dynamic range)
    {
        if (IsCollapsedRange(range))
        {
            return CollapsedRangeIntersectsManagedFormula(range);
        }

        int rangeStart = GetRangeStart(range);
        int rangeEnd = GetRangeEnd(range);
        try
        {
            dynamic controls = CurrentDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (!IsManagedControl(control))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(control.Range), GetRangeEnd(control.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        try
        {
            dynamic inlineShapes = CurrentDocument.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic inlineShape = inlineShapes.Item(i);
                if (string.IsNullOrWhiteSpace(GetOleInlineShapeEquationId(inlineShape)))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(inlineShape.Range), GetRangeEnd(inlineShape.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private bool CollapsedRangeIntersectsManagedFormula(dynamic range)
    {
        int position = GetRangeStart(range);
        int documentEnd = GetRangeEnd(CurrentDocument.Content);
        dynamic nearby = CreateDocumentRange(
            Math.Max(0, position - 1),
            Math.Min(documentEnd, position + 1));
        object? parent = TryGetParentContentControl(range);
        if (parent != null)
        {
            return true;
        }

        object? nearbyControl = TryGetFirstManagedContentControl(nearby);
        if (nearbyControl != null)
        {
            dynamic control = nearbyControl;
            if (RangesIntersectOrContainPoint(
                position,
                position,
                GetRangeStart(control.Range),
                GetRangeEnd(control.Range)))
            {
                return true;
            }
        }

        try
        {
            dynamic inlineShapes = nearby.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int index = 1; index <= count; index++)
            {
                dynamic inlineShape = inlineShapes.Item(index);
                if (!string.IsNullOrWhiteSpace(GetOleInlineShapeEquationId(inlineShape)) &&
                    RangesIntersectOrContainPoint(
                        position,
                        position,
                        GetRangeStart(inlineShape.Range),
                        GetRangeEnd(inlineShape.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private static bool RangesIntersectOrContainPoint(int rangeStart, int rangeEnd, int targetStart, int targetEnd)
    {
        if (rangeStart == rangeEnd)
        {
            return rangeStart >= targetStart && rangeStart < targetEnd;
        }

        return RangesOverlap(rangeStart, rangeEnd, targetStart, targetEnd);
    }
}
