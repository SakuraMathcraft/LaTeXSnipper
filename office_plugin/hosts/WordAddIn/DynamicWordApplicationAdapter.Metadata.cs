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
        WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
        UpsertMetadataControl(metadata, metadataControls: null);
    }

    private void SaveNewFormulaMetadata(
        FormulaMetadata metadata,
        object formulaObject,
        bool hasContentControlBoundary)
    {
        WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
        CreateMetadataControl(metadata, formulaObject, hasContentControlBoundary);
    }

    private void SaveFormulaMetadata(
        FormulaMetadata metadata,
        IDictionary<string, object> metadataControls)
    {
        WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
        UpsertMetadataControl(metadata, metadataControls);
    }

    private void UpsertMetadataControl(
        FormulaMetadata metadata,
        IDictionary<string, object>? metadataControls)
    {
        string equationId = metadata.Identity.EquationId;
        object? existing = null;
        if (metadataControls != null)
        {
            metadataControls.TryGetValue(equationId, out existing);
        }
        else
        {
            existing = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        }

        dynamic control;
        if (existing != null)
        {
            control = existing;
            TryCom(() => control.LockContents = false);
        }
        else
        {
            object? equationControl = TryGetEquationControlById(equationId);
            if (equationControl != null)
            {
                control = CreateMetadataControl(metadata, equationControl, hasContentControlBoundary: true);
            }
            else
            {
                object? inlineShape = TryFindOleInlineShapeById(equationId);
                if (inlineShape == null)
                {
                    throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                }

                control = CreateMetadataControl(metadata, inlineShape, hasContentControlBoundary: false);
            }

            if (metadataControls != null)
            {
                metadataControls[equationId] = control;
            }

            return;
        }

        WriteMetadataControl(control, metadata);
    }

    private dynamic CreateMetadataControl(
        FormulaMetadata metadata,
        object formulaObject,
        bool hasContentControlBoundary)
    {
        string json = WordFormulaMetadataStore.Serialize(metadata);
        int position = GetRangeEnd(((dynamic)formulaObject).Range) +
            (hasContentControlBoundary ? 1 : 0);
        position = ClampDocumentPosition(position);
        dynamic insertionRange = CreateDocumentRange(position, position);
        insertionRange.InsertAfter(json);
        dynamic controlRange = CreateDocumentRange(position, position + json.Length);
        dynamic control = controlRange.ContentControls.Add(WdContentControlRichText);
        control.Tag = WordFormulaMetadataStore.BuildMetadataTag(metadata.Identity.EquationId);
        control.Title = WordFormulaMetadataStore.BuildMetadataAlias(metadata.Identity.EquationId);
        ApplyMetadataControlFormatting(control);
        return control;
    }

    private static void WriteMetadataControl(dynamic control, FormulaMetadata metadata)
    {
        TryCom(() => control.Range.Font.Hidden = 0);
        control.Range.Text = WordFormulaMetadataStore.Serialize(metadata);
        ApplyMetadataControlFormatting(control);
    }

    private static void ApplyMetadataControlFormatting(dynamic control)
    {
        HideContentControlChrome(control);
        TryCom(() => control.Range.Font.Hidden = -1);
        TryCom(() => control.Range.Font.Size = 1);
        TryCom(() => control.Range.Font.Position = 0);
        TryCom(() => control.LockContents = true);
    }

    private Dictionary<string, object> LoadMetadataControlIndex()
    {
        var result = new Dictionary<string, object>(StringComparer.Ordinal);
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            string equationId = WordFormulaMetadataStore.EquationIdFromMetadataTag(
                Convert.ToString(control.Tag) ?? string.Empty);
            if (!string.IsNullOrWhiteSpace(equationId))
            {
                result[equationId] = control;
            }
        }

        return result;
    }

    private FormulaMetadata LoadFormulaMetadata(
        string equationId,
        IReadOnlyDictionary<string, object> metadataControls)
    {
        if (metadataControls.TryGetValue(equationId, out object control))
        {
            return WordFormulaMetadataStore.Deserialize(
                CleanRangeText(ReadHiddenControlText(control)));
        }

        return WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
    }

    private static string ReadHiddenControlText(object contentControl)
    {
        dynamic range = ((dynamic)contentControl).Range.Duplicate;
        TryCom(() => range.TextRetrievalMode.IncludeHiddenText = true);
        return Convert.ToString(range.Text) ?? string.Empty;
    }

    private FormulaMetadata LoadFormulaMetadata(
        dynamic control,
        string equationId,
        RenderEngineKind actualRenderEngine)
    {
        FormulaMetadata metadata;
        try
        {
            metadata = WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
        }
        catch
        {
            metadata = CreateRecoveredFormulaMetadata(control, equationId);
        }

        if (metadata.RenderEngine == actualRenderEngine)
        {
            return metadata;
        }

        FormulaMetadata corrected = WithRenderEngine(metadata, actualRenderEngine);
        SaveFormulaMetadata(corrected);
        return corrected;
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
            metadata.FontColor,
            metadata.FontStyle,
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

    private FormulaMetadata CreateRecoveredFormulaMetadata(dynamic control, string equationId)
    {
        string numberText = ReadNumberText(equationId);
        NumberingMode numberingMode = string.IsNullOrWhiteSpace(numberText) ? NumberingMode.None : NumberingMode.Manual;
        FormulaDisplayMode displayMode = numberingMode != NumberingMode.None || IsCenteredParagraph(control)
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        return new FormulaMetadata(
            new FormulaIdentity("active-document", equationId),
            ReadFormulaText(control),
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: 1);
    }

    private string ReadNumberText(string equationId)
    {
        object? control = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        return control == null ? string.Empty : CleanRangeText(((dynamic)control).Range.Text);
    }

    private void ReplaceNumberControlTextById(string equationId, string numberText)
    {
        object? control = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        if (control != null)
        {
            ReplaceNumberControlText(control, numberText);
        }
    }

    private static void ReplaceNumberControlText(object numberControl, string numberText)
    {
        dynamic control = numberControl;
        HideContentControlChrome(control);
        TryCom(() => control.Range.Text = numberText);
    }

    private static string ReadFormulaText(dynamic control)
    {
        try
        {
            return CleanRangeText(Convert.ToString(control.Range.Text) ?? string.Empty);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool IsCenteredParagraph(dynamic control)
    {
        try
        {
            int alignment = Convert.ToInt32(control.Range.ParagraphFormat.Alignment);
            return alignment == WdAlignParagraphCenter;
        }
        catch
        {
            return false;
        }
    }

    private static string CleanRangeText(string value)
    {
        return value
            .Replace("\a", string.Empty)
            .Replace("\r", string.Empty)
            .Replace("\n", string.Empty)
            .Trim();
    }

    private static object? TryGetNumberControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildNumberTag(equationId));
    }

    private object? TryGetEquationControlById(string equationId)
    {
        try
        {
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
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

    private static object? TryGetMetadataControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildMetadataTag(equationId));
    }

    private static object? TryGetControlByTag(dynamic document, string expectedTag)
    {
        try
        {
            dynamic controls = document.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (string.Equals(tag, expectedTag, StringComparison.Ordinal))
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
            return _wordApplication.ActiveDocument.Range(start, end);
        }
        catch
        {
            return _wordApplication.ActiveDocument.Range(Math.Max(0, start - 1), Math.Max(0, end - 1));
        }
    }

    private int ClampDocumentPosition(int position)
    {
        try
        {
            int documentStart = Convert.ToInt32(_wordApplication.ActiveDocument.Content.Start);
            int documentEnd = Convert.ToInt32(_wordApplication.ActiveDocument.Content.End);
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
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
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
            dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
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
        int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
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
