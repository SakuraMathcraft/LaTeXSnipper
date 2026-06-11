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

    public Task<IReadOnlyList<FormulaMetadata>> LoadAllFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var entries = new List<(int Start, FormulaMetadata Metadata)>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int controlCount = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= controlCount; index++)
        {
            dynamic control = controls.Item(index);
            string equationId = WordFormulaMetadataStore.EquationIdFromTag(Convert.ToString(control.Tag) ?? string.Empty);
            if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
            {
                continue;
            }

            entries.Add((GetRangeStart(control.Range), LoadFormulaMetadata(control, equationId)));
        }

        dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
        int shapeCount = Convert.ToInt32(inlineShapes.Count);
        for (int index = 1; index <= shapeCount; index++)
        {
            dynamic shape = inlineShapes.Item(index);
            string equationId = GetOleInlineShapeEquationId(shape);
            if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
            {
                continue;
            }

            entries.Add((GetRangeStart(shape.Range), LoadFormulaMetadata(shape, equationId)));
        }

        return Task.FromResult<IReadOnlyList<FormulaMetadata>>(
            entries.OrderBy(entry => entry.Start).Select(entry => entry.Metadata).ToArray());
    }

    public Task InsertReferencePlaceholderAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic range = _wordApplication.Selection.Range;
        dynamic control = range.ContentControls.Add(WdContentControlRichText);
        control.Tag = ReferencePlaceholderTag;
        control.Title = "LaTeXSnipper Reference";
        control.Range.Text = WordAddInText.Get("ReferencePlaceholderText");
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
        document.Fields.Add(placeholderRange, -1, " REF " + bookmarkName + " \\h ", true);
        TryCom(() => placeholder.Delete(false));
        _pendingReferenceControl = null;
        return Task.FromResult(true);
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
        return Task.CompletedTask;
    }

    private static string BuildReferenceBookmarkName(string equationId)
    {
        return "LaTeXSnipperEq_" + equationId;
    }

    private void UpdateFormulaReferences()
    {
        dynamic document = _wordApplication.ActiveDocument;
        foreach (NumberedFormulaEntry entry in LoadNumberedFormulaEntries())
        {
            string bookmarkName = BuildReferenceBookmarkName(entry.EquationId);
            if (Convert.ToBoolean(document.Bookmarks.Exists(bookmarkName)))
            {
                document.Bookmarks.Item(bookmarkName).Delete();
            }

            dynamic numberControl = entry.NumberControl;
            document.Bookmarks.Add(bookmarkName, numberControl.Range);
        }

        TryCom(() => document.Fields.Update());
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
        var entries = LoadNumberedFormulaEntries()
            .Select(formula => new NumberingDocumentEntry(formula.Start, formula, null))
            .ToList();
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            if (IsNumberingBoundary(control, out WordNumberingBoundary boundary))
            {
                entries.Add(new NumberingDocumentEntry(GetRangeStart(control.Range), null, boundary));
            }
        }

        return entries.OrderBy(entry => entry.Start).ToArray();
    }
}
