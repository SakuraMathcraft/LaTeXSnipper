using System;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private dynamic ResolveInsertionTargetRange(dynamic selection, bool display)
    {
        dynamic selectedRange = selection.Range;
        if (!display)
        {
            return selectedRange;
        }

        dynamic insertionPoint = selectedRange.Duplicate;
        insertionPoint.Collapse(WdCollapseEnd);
        dynamic paragraphRange = insertionPoint.Paragraphs.Item(1).Range;
        if (!ParagraphHasContent(paragraphRange))
        {
            int paragraphStart = GetRangeStart(paragraphRange);
            return CreateDocumentRange(paragraphStart, paragraphStart);
        }

        int nextParagraphStart = GetRangeEnd(paragraphRange);
        paragraphRange.InsertParagraphAfter();
        return CreateDocumentRange(nextParagraphStart, nextParagraphStart);
    }

    private dynamic ResolveManagedEquationInsertionRange(dynamic selection, bool display)
    {
        if (!display)
        {
            return selection.Range;
        }

        dynamic insertionPoint = ResolveInsertionTargetRange(selection, display: true);
        return insertionPoint.Paragraphs.Item(1).Range;
    }

    private static bool ParagraphHasContent(dynamic paragraphRange)
    {
        dynamic content = paragraphRange.Duplicate;
        int start = GetRangeStart(content);
        int end = Math.Max(start, GetRangeEnd(content) - 1);
        content.SetRange(start, end);
        string text = Convert.ToString(content.Text) ?? string.Empty;
        if (!string.IsNullOrWhiteSpace(text))
        {
            return true;
        }

        return Convert.ToInt32(content.ContentControls.Count) > 0 ||
            Convert.ToInt32(content.InlineShapes.Count) > 0 ||
            Convert.ToInt32(content.OMaths.Count) > 0;
    }

    private bool TryMoveSelectionToFollowingParagraph(dynamic paragraphRange)
    {
        int nextParagraphStart = GetRangeEnd(paragraphRange);
        int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
        if (nextParagraphStart >= documentEnd)
        {
            return false;
        }

        dynamic target = CreateDocumentRange(nextParagraphStart, nextParagraphStart);
        dynamic targetParagraph = target.Paragraphs.Item(1).Range;
        if (GetRangeStart(targetParagraph) < nextParagraphStart)
        {
            return false;
        }

        return TryMoveSelectionOutsideFormula(nextParagraphStart);
    }

    private void RemoveEmptyParagraphBeforeFollowingContent(string equationId)
    {
        dynamic control = FindFormulaControlById(equationId);
        dynamic formulaParagraph = GetContainingParagraphRange(control);
        int nextParagraphStart = GetRangeEnd(formulaParagraph);
        int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
        if (nextParagraphStart >= documentEnd)
        {
            return;
        }

        dynamic nextParagraph = CreateDocumentRange(nextParagraphStart, nextParagraphStart).Paragraphs.Item(1).Range;
        if (ParagraphHasContent(nextParagraph))
        {
            return;
        }

        int followingParagraphStart = GetRangeEnd(nextParagraph);
        if (followingParagraphStart >= documentEnd)
        {
            return;
        }

        dynamic followingParagraph = CreateDocumentRange(followingParagraphStart, followingParagraphStart).Paragraphs.Item(1).Range;
        if (!ParagraphHasContent(followingParagraph))
        {
            return;
        }

        nextParagraph.Delete();
    }
}
