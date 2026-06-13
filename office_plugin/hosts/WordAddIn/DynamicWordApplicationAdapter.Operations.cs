using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private const string ReferencePlaceholderTag = "latexsnipper-reference-pending";
    private const string ReferenceTagPrefix = "latexsnipper-reference:";
    private const string ChapterBoundaryTag = "latexsnipper-number-boundary-chapter";
    private const string SectionBoundaryTag = "latexsnipper-number-boundary-section";
    private object? _pendingReferenceControl;

    private sealed class NumberingDocumentEntry
    {
        public NumberingDocumentEntry(int start, NumberedFormulaEntry? formula, WordNumberingBoundary? boundary)
        {
            Start = start;
            Formula = formula;
            Boundary = boundary;
        }

        public int Start { get; }

        public NumberedFormulaEntry? Formula { get; }

        public WordNumberingBoundary? Boundary { get; }
    }

    public Task InsertReferencePlaceholderAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic range = _wordApplication.Selection.Range;
        double fontSize = ReadPointSize(range.Font.Size);
        dynamic control = range.ContentControls.Add(WdContentControlRichText);
        control.Tag = ReferencePlaceholderTag;
        control.Title = "LaTeXSnipper Reference";
        control.Range.Text = WordAddInText.Get("ReferencePlaceholderText");
        ApplyReferenceControlFormatting(control, fontSize);
        _pendingReferenceControl = control;
        return Task.CompletedTask;
    }

    public Task<bool> CompletePendingReferenceAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_pendingReferenceControl == null)
        {
            return Task.FromResult(false);
        }

        dynamic selectionRange = _wordApplication.Selection.Range;
        object? selectedControl = TryGetParentContentControl(selectionRange) ?? TryGetFirstManagedContentControl(selectionRange);
        if (selectedControl == null)
        {
            return Task.FromResult(false);
        }

        dynamic numberControl = selectedControl;
        string equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(Convert.ToString(numberControl.Tag) ?? string.Empty);
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return Task.FromResult(false);
        }

        string bookmarkName = BuildReferenceBookmarkName(equationId);
        dynamic document = _wordApplication.ActiveDocument;
        if (Convert.ToBoolean(document.Bookmarks.Exists(bookmarkName)))
        {
            document.Bookmarks.Item(bookmarkName).Delete();
        }

        document.Bookmarks.Add(bookmarkName, numberControl.Range);
        dynamic placeholder = _pendingReferenceControl;
        dynamic placeholderRange = placeholder.Range;
        placeholderRange.Text = string.Empty;
        placeholderRange = placeholder.Range;
        placeholderRange.End = Math.Max(Convert.ToInt32(placeholderRange.Start), Convert.ToInt32(placeholderRange.End) - 1);
        placeholderRange.Collapse(1);
        document.Fields.Add(placeholderRange, -1, " REF " + bookmarkName + " \\h ", true);
        placeholder.Tag = ReferenceTagPrefix + equationId;
        placeholder.Title = "LaTeXSnipper Formula Reference";
        ApplyReferenceControlFormatting(placeholder, ReadSurroundingTextFontSize(placeholder));
        _pendingReferenceControl = null;
        return Task.FromResult(true);
    }

    private static void ApplyReferenceControlFormatting(dynamic control, double fontSize)
    {
        HideContentControlChrome(control);
        TryCom(() => control.Range.Font.Position = 0);
        TryCom(() => control.Range.Font.Superscript = 0);
        TryCom(() => control.Range.Font.Subscript = 0);
        if (fontSize > 0)
        {
            TryCom(() => control.Range.Font.Size = fontSize);
        }
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
        return string.Equals(tag, ReferencePlaceholderTag, StringComparison.Ordinal)
            || tag.StartsWith(ReferenceTagPrefix, StringComparison.Ordinal)
            || string.Equals(tag, ChapterBoundaryTag, StringComparison.Ordinal)
            || string.Equals(tag, SectionBoundaryTag, StringComparison.Ordinal);
    }

    private void DeleteCommandControl(object selected)
    {
        dynamic control = selected;
        string tag = ReadControlTag(control);
        if (string.Equals(tag, ReferencePlaceholderTag, StringComparison.Ordinal))
        {
            _pendingReferenceControl = null;
        }

        control.Delete(true);
    }

    private static string BuildReferenceBookmarkName(string equationId)
    {
        return "LaTeXSnipperEq_" + equationId;
    }

    private void UpdateFormulaReferences(IReadOnlyList<NumberingDocumentEntry> entries)
    {
        dynamic document = _wordApplication.ActiveDocument;
        foreach (NumberingDocumentEntry documentEntry in entries)
        {
            NumberedFormulaEntry? entry = documentEntry.Formula;
            if (entry == null)
            {
                continue;
            }

            string bookmarkName = BuildReferenceBookmarkName(entry.EquationId);
            if (!Convert.ToBoolean(document.Bookmarks.Exists(bookmarkName)))
            {
                dynamic numberControl = entry.NumberControl;
                document.Bookmarks.Add(bookmarkName, numberControl.Range);
            }
        }

        dynamic controls = document.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            if (ReadControlTag(control).StartsWith(ReferenceTagPrefix, StringComparison.Ordinal))
            {
                TryCom(() => control.Range.Fields.Update());
            }
        }
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

    private IReadOnlyList<NumberingDocumentEntry> LoadNumberingDocumentEntries()
    {
        var entries = new List<NumberingDocumentEntry>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var formulaObjects = new Dictionary<string, IndexedFormulaObject>(StringComparer.Ordinal);
        int previousStart = -1;
        bool ordered = true;
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            string equationId = GetEquationControlId(control);
            if (!string.IsNullOrWhiteSpace(equationId))
            {
                formulaObjects[equationId] = new IndexedFormulaObject(control, RenderEngineKind.Omml);
            }
        }

        dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
        int shapeCount = Convert.ToInt32(inlineShapes.Count);
        for (int index = 1; index <= shapeCount; index++)
        {
            dynamic inlineShape = inlineShapes.Item(index);
            string equationId = GetOleInlineShapeEquationId(inlineShape);
            if (!string.IsNullOrWhiteSpace(equationId))
            {
                formulaObjects[equationId] = new IndexedFormulaObject(
                    inlineShape,
                    RenderEngineKind.MathJaxSvg);
            }
        }

        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            if (IsNumberingBoundary(control, out WordNumberingBoundary boundary))
            {
                int start = GetRangeStart(control.Range);
                ordered &= start >= previousStart;
                previousStart = start;
                entries.Add(new NumberingDocumentEntry(start, null, boundary));
                continue;
            }

            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            string equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
            if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
            {
                continue;
            }

            if (!formulaObjects.TryGetValue(equationId, out IndexedFormulaObject formulaObject))
            {
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
            }

            FormulaMetadata metadata = LoadFormulaMetadata(
                formulaObject.Value,
                equationId,
                formulaObject.RenderEngine);
            var formula = new NumberedFormulaEntry(
                equationId,
                formulaObject.Value,
                control,
                metadata,
                GetRangeStart(control.Range));
            ordered &= formula.Start >= previousStart;
            previousStart = formula.Start;
            entries.Add(new NumberingDocumentEntry(formula.Start, formula, null));
        }

        return ordered
            ? entries
            : entries.OrderBy(entry => entry.Start).ToArray();
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
