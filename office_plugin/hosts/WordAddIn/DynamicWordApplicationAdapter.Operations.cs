using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private const string ChapterBoundaryTag = "latexsnipper-number-boundary-chapter";
    private const string SectionBoundaryTag = "latexsnipper-number-boundary-section";
    private object? _pendingReferenceRange;

    public Task InsertReferencePlaceholderAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic range = _wordApplication.Selection.Range;
        range.Text = WordAddInText.Get("ReferencePlaceholderText");
        _pendingReferenceRange = range.Duplicate;
        return Task.CompletedTask;
    }

    public Task<bool> CompletePendingReferenceAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_pendingReferenceRange == null)
        {
            return Task.FromResult(false);
        }

        string equationId = FindSelectedEquationIdFromReferenceTarget();
        FormulaMetadata metadata = LoadFormulaMetadataByEquationId(equationId);
        if (metadata.NumberingMode == NumberingMode.None)
        {
            return Task.FromResult(false);
        }

        AddOrReplaceEquationBookmark(equationId, FindEquationNumberRangeById(equationId));
        dynamic placeholderRange = _pendingReferenceRange;
        placeholderRange.Text = string.Empty;
        placeholderRange.Collapse(1);
        dynamic referenceField = _wordApplication.ActiveDocument.Fields.Add(
            placeholderRange,
            WdFieldEmpty,
            " REF " + WordEquationNumbering.BuildBookmarkName(equationId) + " \\h ",
            true);
        TryCom(() => referenceField.Update());
        ResetPlainTextBaseline(referenceField.Result);
        _pendingReferenceRange = null;
        return Task.FromResult(true);
    }

    private string FindSelectedEquationIdFromReferenceTarget()
    {
        try
        {
            SelectedWordFormula formula = FindSelectedFormula();
            return formula.Metadata.Identity.EquationId;
        }
        catch
        {
        }

        return FindSelectedFormulaFromReferenceTarget().Metadata.Identity.EquationId;
    }

    private FormulaMetadata LoadFormulaMetadataByEquationId(string equationId)
    {
        object? equationControl = TryGetEquationControlById(equationId);
        if (equationControl != null)
        {
            return LoadFormulaMetadata(equationControl, equationId, RenderEngineKind.Omml);
        }

        object? oleInlineShape = TryFindOleInlineShapeById(equationId);
        if (oleInlineShape != null)
        {
            return LoadFormulaMetadata(oleInlineShape, equationId, RenderEngineKind.MathJaxSvg);
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
    }

    private SelectedWordFormula FindSelectedFormulaFromReferenceTarget()
    {
        try
        {
            return FindSelectedFormula();
        }
        catch
        {
        }

        dynamic paragraphRange = _wordApplication.Selection.Range.Paragraphs.Item(1).Range;
        var formulas = new List<SelectedWordFormula>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        AddSelectedFormulasFromRange(formulas, seen, paragraphRange);
        AddSelectedOleInlineShapes(formulas, seen, paragraphRange);
        if (formulas.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return formulas[0];
    }

    public Task InsertNumberingBoundaryAsync(WordNumberingBoundary boundary, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic range = _wordApplication.Selection.Range;
        range.Collapse(WdCollapseEnd);
        dynamic control = range.ContentControls.Add(WdContentControlRichText);
        control.Tag = boundary == WordNumberingBoundary.Chapter ? ChapterBoundaryTag : SectionBoundaryTag;
        control.Title = "LaTeXSnipper Numbering Boundary";
        control.Range.Text = boundary == WordNumberingBoundary.Chapter
            ? WordAddInText.Get("ChapterBoundaryText")
            : WordAddInText.Get("SectionBoundaryText");
        HideContentControlChrome(control);
        ApplyBoundaryVisibility(control, boundary, WordPluginSettings.Load());
        return Task.CompletedTask;
    }

    public Task ApplyNumberingBoundaryVisibilityAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() => ApplyNumberingBoundaryVisibility(WordPluginSettings.Load()));
        return Task.CompletedTask;
    }

    private IReadOnlyList<object> FindSelectedCommandControls()
    {
        dynamic selectionRange = _wordApplication.Selection.Range;
        var controls = new List<object>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        try
        {
            object? parent = selectionRange.ParentContentControl;
            if (parent != null && IsCommandControlTag(ReadControlTag((dynamic)parent)))
            {
                AddSelectedCommandControl(controls, seen, parent!);
            }
        }
        catch
        {
        }

        try
        {
            dynamic rangeControls = selectionRange.ContentControls;
            int count = Convert.ToInt32(rangeControls.Count);
            for (int index = 1; index <= count; index++)
            {
                dynamic control = rangeControls.Item(index);
                if (IsCommandControlTag(ReadControlTag(control)))
                {
                    AddSelectedCommandControl(controls, seen, control);
                }
            }
        }
        catch
        {
        }

        int selectionStart = GetRangeStart(selectionRange);
        int selectionEnd = GetRangeEnd(selectionRange);
        dynamic documentControls = _wordApplication.ActiveDocument.ContentControls;
        int documentControlCount = Convert.ToInt32(documentControls.Count);
        for (int index = 1; index <= documentControlCount; index++)
        {
            dynamic control = documentControls.Item(index);
            if (!IsCommandControlTag(ReadControlTag(control)))
            {
                continue;
            }

            int controlStart = GetRangeStart(control.Range);
            int controlEnd = GetRangeEnd(control.Range);
            bool selected = selectionStart == selectionEnd
                ? selectionStart >= controlStart && selectionStart < controlEnd
                : RangesOverlap(selectionStart, selectionEnd, controlStart, controlEnd);
            if (selected)
            {
                AddSelectedCommandControl(controls, seen, control);
            }
        }

        return controls;
    }

    private static void AddSelectedCommandControl(
        ICollection<object> controls,
        ISet<string> seen,
        object candidate)
    {
        dynamic control = candidate;
        string key = GetRangeStart(control.Range).ToString(System.Globalization.CultureInfo.InvariantCulture)
            + ":"
            + GetRangeEnd(control.Range).ToString(System.Globalization.CultureInfo.InvariantCulture);
        if (seen.Add(key))
        {
            controls.Add(candidate);
        }
    }

    private static bool IsCommandControlTag(string tag)
    {
        return string.Equals(tag, ChapterBoundaryTag, StringComparison.Ordinal)
            || string.Equals(tag, SectionBoundaryTag, StringComparison.Ordinal);
    }

    private void DeleteCommandControl(object selected)
    {
        dynamic control = selected;
        control.Delete(true);
    }

    private IReadOnlyList<object> FindSelectedReferenceFields()
    {
        dynamic selectionRange = _wordApplication.Selection.Range;
        int selectionStart = GetRangeStart(selectionRange);
        int selectionEnd = GetRangeEnd(selectionRange);
        var fields = new List<object>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        dynamic documentFields = _wordApplication.ActiveDocument.Fields;
        int fieldCount = Convert.ToInt32(documentFields.Count);
        for (int index = 1; index <= fieldCount; index++)
        {
            dynamic field = documentFields.Item(index);
            if (!IsLaTeXSnipperReferenceField(field))
            {
                continue;
            }

            int fieldStart = GetRangeStart(field.Result);
            int fieldEnd = GetRangeEnd(field.Result);
            bool selected = selectionStart == selectionEnd
                ? selectionStart >= fieldStart && selectionStart <= fieldEnd
                : RangesOverlap(selectionStart, selectionEnd, fieldStart, fieldEnd);
            string key = fieldStart.ToString(System.Globalization.CultureInfo.InvariantCulture)
                + ":"
                + fieldEnd.ToString(System.Globalization.CultureInfo.InvariantCulture);
            if (selected && seen.Add(key))
            {
                fields.Add((object)field);
            }
        }

        return fields;
    }

    private object? FindSelectedPendingReferencePlaceholder()
    {
        if (_pendingReferenceRange == null)
        {
            return null;
        }

        dynamic selectionRange = _wordApplication.Selection.Range;
        dynamic placeholderRange = _pendingReferenceRange;
        int selectionStart = GetRangeStart(selectionRange);
        int selectionEnd = GetRangeEnd(selectionRange);
        int placeholderStart = GetRangeStart(placeholderRange);
        int placeholderEnd = GetRangeEnd(placeholderRange);
        bool selected = selectionStart == selectionEnd
            ? selectionStart >= placeholderStart && selectionStart <= placeholderEnd
            : RangesOverlap(selectionStart, selectionEnd, placeholderStart, placeholderEnd);
        return selected ? _pendingReferenceRange : null;
    }

    private static bool IsLaTeXSnipperReferenceField(dynamic field)
    {
        string code = Convert.ToString(field.Code.Text) ?? string.Empty;
        return code.IndexOf(" REF " + WordEquationNumbering.BookmarkPrefix, StringComparison.Ordinal) >= 0;
    }

    private static void DeleteReferenceField(object selected)
    {
        dynamic field = selected;
        field.Delete();
    }

    private void DeletePendingReferencePlaceholder(object selected)
    {
        dynamic range = selected;
        range.Delete();
        _pendingReferenceRange = null;
    }

    private static bool IsNumberingBoundary(dynamic control, out WordNumberingBoundary boundary)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        if (string.Equals(tag, ChapterBoundaryTag, StringComparison.Ordinal))
        {
            boundary = WordNumberingBoundary.Chapter;
            return true;
        }

        boundary = WordNumberingBoundary.Section;
        return string.Equals(tag, SectionBoundaryTag, StringComparison.Ordinal);
    }

    private void ApplyNumberingBoundaryVisibility(WordPluginSettings settings)
    {
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            if (IsNumberingBoundary(control, out WordNumberingBoundary boundary))
            {
                ApplyBoundaryVisibility(control, boundary, settings);
            }
        }
    }

    private static void ApplyBoundaryVisibility(dynamic control, WordNumberingBoundary boundary, WordPluginSettings settings)
    {
        HideContentControlChrome(control);
        bool hidden = boundary == WordNumberingBoundary.Chapter
            ? settings.HideChapterBoundary
            : settings.HideSectionBoundary;
        TryCom(() => control.Range.Font.Hidden = hidden ? -1 : 0);
    }
}
