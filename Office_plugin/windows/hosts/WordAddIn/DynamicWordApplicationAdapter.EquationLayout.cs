using System;
using System.Collections.Generic;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    // Word expands bookmarks when content is inserted exactly at their boundaries.
    private sealed class EquationBookmarkScope : IDisposable
    {
        private readonly dynamic _document;
        private readonly List<(string Name, object Range, int Length, bool Before)> _bookmarks = new();

        public EquationBookmarkScope(object document, object formulaRange, string? equationId = null, object? replacedNumber = null)
        {
            _document = document;
            dynamic formula = formulaRange;
            dynamic paragraph = formula.Paragraphs.Item(1).Range;
            // InsertXML can expand bookmarks at the adjacent paragraph boundary too.
            dynamic neighborhood = paragraph.Duplicate;
            neighborhood.MoveStart(4, -1); // wdParagraph
            neighborhood.MoveEnd(4, 1);
            string? owned = equationId != null ? WordEquationNumbering.BuildBookmarkName(equationId) : null;
            if (owned != null && Convert.ToBoolean(_document.Bookmarks.Exists(owned)))
                owned = Convert.ToString(_document.Bookmarks.Item(owned).Name);
            foreach (dynamic bookmark in neighborhood.Bookmarks)
            {
                string name = Convert.ToString((object)bookmark.Name)!;
                dynamic range = bookmark.Range;
                int start = GetRangeStart(range), end = GetRangeEnd(range);
                if (string.Equals(name, owned, StringComparison.OrdinalIgnoreCase) || start == end) continue;
                if (replacedNumber != null && start >= GetRangeStart((dynamic)replacedNumber!) &&
                    end <= GetRangeEnd((dynamic)replacedNumber!)) continue;
                bool before = end <= GetRangeStart(formula);
                if (before || start >= GetRangeEnd(formula))
                    _bookmarks.Add((name, (object)range.Duplicate, end - start, before));
            }
        }

        public void Dispose()
        {
            foreach (var bookmark in _bookmarks)
            {
                dynamic range = bookmark.Range;
                int start = bookmark.Before ? GetRangeStart(range) : GetRangeEnd(range) - bookmark.Length;
                _document.Bookmarks.Add(bookmark.Name, _document.Range(start, start + bookmark.Length));
            }
        }
    }

    private double GetEquationContentWidthPoints(dynamic range)
    {
        if (Convert.ToBoolean(range.Information[12])) // wdWithInTable
        {
            dynamic cell = range.Cells.Item(1);
            return Math.Max(1, Convert.ToDouble(cell.Width) - Convert.ToDouble(cell.LeftPadding)
                - Convert.ToDouble(cell.RightPadding));
        }

        dynamic setup = range.Sections.Item(1).PageSetup;
        dynamic columns = setup.TextColumns;
        int count = Convert.ToInt32(columns.Count);
        if (count == 1 || Convert.ToInt32(columns.EvenlySpaced) != 0)
            return Convert.ToDouble(columns.Item(1).Width);

        // Word resolves the actual column after pagination, including continuous sections.
        dynamic point = range.Duplicate;
        point.Collapse(WdCollapseEnd);
        CurrentDocument.Repaginate();
        double pageX = Convert.ToDouble(point.Information[5]);
        double textX = Convert.ToDouble(point.Information[7]);
        if (pageX < 0 || textX < 0)
            throw new InvalidOperationException("Word 无法确定公式所在栏的位置。");
        double columnLeft = pageX - textX;
        double left = Convert.ToDouble(setup.LeftMargin);
        double bestDistance = double.MaxValue;
        double width = 0;
        for (int index = 1; index <= count; index++)
        {
            dynamic column = columns.Item(index);
            double candidate = Convert.ToDouble(column.Width);
            double distance = Math.Abs(columnLeft - left);
            if (distance < bestDistance) { bestDistance = distance; width = candidate; }
            if (index < count) left += candidate + Convert.ToDouble(column.SpaceAfter);
        }
        return width;
    }

    private dynamic RemoveFormulaForReplacement(dynamic formulaRange, FormulaMetadata? metadata, bool display)
    {
        dynamic source = formulaRange.Duplicate;
        object? parent = TryGetParentContentControl(source) ?? TryGetFirstManagedContentControl(source);
        string? equationId = metadata?.Identity.EquationId;
        bool numbered = false;
        if (metadata != null && metadata.NumberingMode != NumberingMode.None
            && TryFindEquationNumberRangeById(metadata.Identity.EquationId, out object? number))
        {
            object? owned = FindOwnedNumberForRemoval(number!, (object)source, metadata);
            CurrentDocument.Bookmarks.Item(WordEquationNumbering.BuildBookmarkName(metadata.Identity.EquationId)).Delete();
            if (owned != null && (GetRangeEnd((dynamic)owned) <= GetRangeStart(source)
                || GetRangeStart((dynamic)owned) >= GetRangeEnd(source)))
            {
                numbered = true;
                ((dynamic)owned!).Delete();
            }
        }

        if (parent != null && equationId != null && GetEquationId((dynamic)parent) == equationId)
        {
            dynamic control = parent!;
            control.LockContents = false;
            control.LockContentControl = false;
            dynamic anchor = control.Range.Duplicate;
            anchor.Collapse(1);
            control.Delete(true);
            source = anchor;
        }

        // Only the immediately adjacent layout tabs belong to the formula scaffold.
        if (numbered)
        {
            int start = GetRangeStart(source), end = GetRangeEnd(source);
            dynamic paragraph = source.Paragraphs.Item(1).Range;
            if (start > GetRangeStart(paragraph) &&
                Convert.ToString(CreateDocumentRange(start - 1, start).Text) == "\t") start--;
            if (end < GetRangeEnd(paragraph) - 1 &&
                Convert.ToString(CreateDocumentRange(end, end + 1).Text) == "\t") end++;
            source.SetRange(start, end);
        }
        int position = GetRangeStart(source);
        if (GetRangeEnd(source) > position) source.Delete();
        dynamic insertion = CreateDocumentRange(position, position);
        if (!display) return insertion;

        dynamic remaining = insertion.Paragraphs.Item(1).Range;
        int paragraphStart = GetRangeStart(remaining);
        int paragraphEnd = GetRangeEnd(remaining);
        // Keep both sides in place; isolate the replacement instead of clearing the paragraph.
        bool before = position > paragraphStart;
        bool after = position < paragraphEnd - (Convert.ToString(remaining.Text)?.EndsWith("\r\a") == true ? 2 : 1);
        if (before || after)
        {
            insertion.Text = (before ? "\r" : "") + (after ? "\r" : "");
            position += before ? 1 : 0;
        }
        return CreateDocumentRange(position, position);
    }

    private object? FindOwnedNumberForRemoval(object bookmarkRange, object formulaRange, FormulaMetadata metadata)
    {
        dynamic bookmark = bookmarkRange, formula = formulaRange;
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            object field = LaTeXSnipperNumberField(bookmarkRange);
            return ReferenceEquals(field, bookmarkRange) ? null : field;
        }

        // Word may expand the bookmark to include text typed at an edge of the label.
        string text = Convert.ToString((object?)bookmark.Text) ?? string.Empty;
        if (metadata.NumberText.Length == 0) return null;
        bool numberOnLeft = GetRangeEnd(bookmark) <= GetRangeStart(formula);
        foreach (WordNumberEnclosure enclosure in Enum.GetValues(typeof(WordNumberEnclosure)))
        {
            string label = WordEquationNumbering.GetLeftEnclosure(enclosure) + metadata.NumberText
                + WordEquationNumbering.GetRightEnclosure(enclosure);
            int index = numberOnLeft ? text.LastIndexOf(label, StringComparison.Ordinal) : text.IndexOf(label, StringComparison.Ordinal);
            if (index >= 0)
            {
                int start = GetRangeStart(bookmark) + index;
                return (object)RangeInStory(bookmarkRange, start, start + label.Length);
            }
        }
        return null;
    }
}
