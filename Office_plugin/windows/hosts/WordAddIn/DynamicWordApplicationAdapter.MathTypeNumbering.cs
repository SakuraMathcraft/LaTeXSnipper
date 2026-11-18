using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private static (object Whole, object Caption)? FindNativeMathTypeNumber(object scope)
    {
        foreach (dynamic field in ((dynamic)scope).Fields)
        {
            if (!IsFieldCode((object)field, WordMathTypeNumberRuns.PlaceReference)) continue;
            foreach (dynamic sequence in field.Code.Fields)
            {
                if (IsFieldCode((object)sequence, "SEQ " + WordMathTypeNumberRuns.EquationSequence)
                    && Convert.ToString((object)sequence.Code.Text)!.IndexOf(@"\h", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    dynamic caption = field.Code.Duplicate;
                    caption.Start = sequence.Result.End;
                    caption.TextRetrievalMode.IncludeFieldCodes = false;
                    caption.TextRetrievalMode.IncludeHiddenText = false;
                    if (caption.Start >= caption.End) break;
                    return (WholeNumberField((object)field), (object)caption);
                }
            }
        }
        return null;
    }

    private static bool IsFieldCode(object target, string name)
    {
        string code = (Convert.ToString((object?)((dynamic)target).Code.Text) ?? "").TrimStart();
        return code.StartsWith(name, StringComparison.OrdinalIgnoreCase)
            && (code.Length == name.Length || char.IsWhiteSpace(code[name.Length]));
    }

    private static object WholeNumberField(object target)
    {
        dynamic field = target;
        dynamic range = field.Code.Duplicate;
        range.Start = GetRangeStart(range) - 1;
        range.End = field.Result.End + (field.Result.Start < field.Result.End ? 1 : 0);
        return (object)range;
    }

    private object LaTeXSnipperNumberField(object result)
    {
        dynamic number = result;
        foreach (dynamic field in number.Paragraphs.Item(1).Range.Fields)
        {
            if (IsFieldCode((object)field, "SEQ " + WordEquationNumbering.SequenceName)
                && GetRangeStart(field.Result) >= GetRangeStart(number)
                && GetRangeEnd(field.Result) <= GetRangeEnd(number))
                return WholeNumberField((object)field);
        }
        return result;
    }

    private bool IsFirstNumberInSection(int end)
    {
        bool seenNumber = false;
        foreach (dynamic field in CreateDocumentRange(0, end).Fields)
        {
            if (IsFieldCode((object)field, WordMathTypeNumberRuns.SectionBoundary)) seenNumber = false;
            else if (IsFieldCode((object)field, WordMathTypeNumberRuns.PlaceReference) ||
                IsFieldCode((object)field, "SEQ " + WordEquationNumbering.SequenceName))
                seenNumber = true;
        }
        return !seenNumber;
    }

    private string? ReadNativeNumberFormat()
    {
        foreach (dynamic property in CurrentDocument.CustomDocumentProperties)
            if (string.Equals(Convert.ToString((object)property.Name), "MTEquationNumber2", StringComparison.OrdinalIgnoreCase))
                return Convert.ToString((object?)property.Value);
        return null;
    }

    private object ReplaceNumberField(object source, string? xml, string label, bool toMathType, string equationId)
    {
        dynamic old = source;
        int start = GetRangeStart(old), end = GetRangeEnd(old);
        var names = new List<string>();
        foreach (dynamic bookmark in old.Bookmarks)
            if (GetRangeStart(bookmark.Range) >= start && GetRangeEnd(bookmark.Range) <= end)
                names.Add(Convert.ToString((object)bookmark.Name)!);
        string own = WordEquationNumbering.BuildBookmarkName(equationId);
        if (!names.Contains(own)) names.Add(own);

        int baseline = Convert.ToInt32((object)old.Font.Position);
        if (xml == null)
        {
            old.Text = label;
            dynamic plain = CreateDocumentRange(start, start + label.Length);
            if (baseline != 9999999) plain.Font.Position = baseline; // wdUndefined for mixed formatting.
            foreach (string name in names)
                CurrentDocument.Bookmarks.Add(name, plain);
            return (object)plain;
        }

        dynamic paragraph = old.Paragraphs.Item(1).Range;
        dynamic format = paragraph.ParagraphFormat.Duplicate, style = paragraph.Style;
        string styleName = Convert.ToString((object)style.NameLocal)!;
        int before = GetRangeEnd(CurrentDocument.Content);
        dynamic insertion = CreateDocumentRange(end, end);
        dynamic? caption = null;
        try
        {
            insertion.InsertXML(xml);
            int limit = end + GetRangeEnd(CurrentDocument.Content) - before;
            dynamic inserted = CreateDocumentRange(end, limit);
            int fieldEnd = limit;
            if (toMathType)
            {
                var native = FindNativeMathTypeNumber((object)inserted)
                    ?? throw new InvalidOperationException("Word did not insert the MathType number field.");
                caption = native.Caption;
                fieldEnd = GetRangeEnd((dynamic)native.Whole);
            }
            else
            {
                foreach (dynamic field in inserted.Fields)
                {
                    if (!IsFieldCode((object)field, "SEQ " + WordEquationNumbering.SequenceName)) continue;
                    caption = field.Result.Duplicate;
                    fieldEnd = GetRangeEnd((dynamic)WholeNumberField((object)field));
                    break;
                }
                if (caption == null)
                    caption = CreateDocumentRange(end, end + label.Length);
                if (fieldEnd == limit && inserted.Fields.Count == 0)
                    fieldEnd = GetRangeEnd(caption);
            }
            if (!string.Equals(Convert.ToString((object)caption.Text), label, StringComparison.Ordinal))
                throw new InvalidOperationException("Word changed the formula number during conversion.");
            if (fieldEnd < limit)
            {
                dynamic trailing = CreateDocumentRange(fieldEnd, limit);
                if ((Convert.ToString((object?)trailing.Text) ?? "").Trim('\r').Length != 0)
                    throw new InvalidOperationException("Word inserted unexpected text after the formula number.");
                trailing.Delete();
            }
            if (baseline != 9999999) caption.Font.Position = baseline;
            RestoreMathTypeParagraph((object)caption.Paragraphs.Item(1).Range, (object)format, (object)style, styleName);
        }
        catch
        {
            int insertedLength = GetRangeEnd(CurrentDocument.Content) - before;
            if (insertedLength > 0) CreateDocumentRange(end, end + insertedLength).Delete();
            RestoreMathTypeParagraph((object)old.Paragraphs.Item(1).Range, (object)format, (object)style, styleName);
            throw;
        }
        CreateDocumentRange(start, end).Delete();
        foreach (string name in names)
            CurrentDocument.Bookmarks.Add(name, caption);
        return (object)caption;
    }
}
