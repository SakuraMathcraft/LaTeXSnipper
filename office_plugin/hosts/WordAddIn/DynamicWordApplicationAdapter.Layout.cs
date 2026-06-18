using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void ReplaceFormulaContent(
        object contentControl,
        string ooxml,
        string equationContentOoxml,
        FormulaMetadata metadata,
        FormulaMetadata currentMetadata)
    {
        dynamic control = contentControl;
        if (metadata.NumberingMode != currentMetadata.NumberingMode ||
            metadata.NumberingMode != NumberingMode.None ||
            metadata.DisplayMode != FormulaDisplayMode.Inline)
        {
            ReplaceParagraphWithFormula(control, ooxml, metadata);
            return;
        }

        ReplaceExistingEquationControlContent(control, equationContentOoxml, metadata);
        SaveFormulaMetadata(control, metadata);
        NormalizeManagedInlineEquationBaseline(metadata, control);
    }

    private void ReplaceParagraphWithFormula(object contentControl, string ooxml, FormulaMetadata metadata)
    {
        dynamic control = contentControl;
        dynamic insertionRange = ClearParagraphContent(GetContainingParagraphRange(control));
        insertionRange.InsertXML(ooxml);
        RemoveEmptyParagraphBeforeFollowingContent(metadata.Identity.EquationId);
        ApplyNumberControlVerticalAlignmentById(metadata);
        NormalizeNumberedParagraph(metadata.Identity.EquationId);
        SaveFormulaMetadata(metadata);
        NormalizeManagedInlineEquationBaseline(metadata, FindFormulaControlById(metadata.Identity.EquationId));
    }

    private void ReplaceExistingEquationControlContent(dynamic control, string equationContentOoxml, FormulaMetadata metadata)
    {
        TryCom(() => control.LockContents = false);
        TryCom(() => control.LockContentControl = false);
        dynamic equations = control.Range.OMaths;
        if (Convert.ToInt32(equations.Count) == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        ReplaceOmmlRangeWithParsedFormula(equations.Item(1).Range, equationContentOoxml);
        ShowContentControlChrome(control);
        if (metadata.DisplayMode == FormulaDisplayMode.Display)
        {
            TryCom(() => control.Range.ParagraphFormat.Alignment = WdAlignParagraphCenter);
        }
    }

    private void ReplaceOmmlRangeWithParsedFormula(dynamic targetEquationRange, string equationContentOoxml)
    {
        dynamic? scratchDocument = null;
        try
        {
            scratchDocument = _wordApplication.Documents.Add();
            scratchDocument.Range(0, 0).InsertXML(equationContentOoxml);
            dynamic scratchEquations = scratchDocument.OMaths;
            if (Convert.ToInt32(scratchEquations.Count) == 0)
            {
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
            }

            targetEquationRange.FormattedText = scratchEquations.Item(1).Range.FormattedText;
        }
        finally
        {
            if (scratchDocument != null)
            {
                TryCom(() => scratchDocument.Close(false));
            }
        }
    }

    private void ValidateInsertionTarget(dynamic range)
    {
        if (RangeTouchesManagedFormula(range) || RangeIntersectsManagedFormula(range))
        {
            throw new InvalidOperationException(WordAddInText.Get("InsertInsideFormulaError"));
        }
    }

    private void MoveSelectionAfterInsertedFormula(FormulaMetadata metadata, bool display)
    {
        try
        {
            MoveSelectionAfterInsertedFormula(
                FindFormulaControlById(metadata.Identity.EquationId),
                metadata,
                display);
        }
        catch
        {
        }
    }

    private void MoveSelectionAfterInsertedFormula(
        object contentControl,
        FormulaMetadata metadata,
        bool display)
    {
        dynamic control = contentControl;
        string equationId = metadata.Identity.EquationId;
        if (metadata.NumberingMode != NumberingMode.None)
        {
            ApplyNumberedParagraphLayout(control.Range, control.Range);
            MoveSelectionAfterDisplayParagraph(control, equationId);
            return;
        }

        if (!display)
        {
            NormalizePlainTextBaselineAroundRange(control.Range);
            MoveSelectionAfterInlineControl(control, equationId);
            return;
        }

        MoveSelectionAfterDisplayParagraph(control, equationId);
    }

    private void MoveSelectionAfterInlineControl(dynamic control, string equationId)
    {
        MoveSelectionAfterContentControl(control, equationId);
    }

    private void MoveSelectionAfterDisplayParagraph(dynamic control, string equationId)
    {
        dynamic paragraphRange = GetContainingParagraphRange(control);
        if (TryMoveSelectionToFollowingParagraph(paragraphRange))
        {
            return;
        }

        int insertionPoint = GetRangeEnd(paragraphRange);
        bool paragraphInserted = TryInsertParagraphAfter(paragraphRange);
        if (paragraphInserted &&
            (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1)))
        {
            return;
        }

        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterContentControl(object contentControl, string equationId)
    {
        dynamic control = contentControl;
        int insertionPoint = Convert.ToInt32(control.Range.End);
        if (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            return;
        }

        dynamic target = CreateDocumentRange(insertionPoint, insertionPoint);
        target.Select();
        MoveSelectionRight();
        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterInlineShape(object inlineShape, string equationId, bool display)
    {
        dynamic shape = inlineShape;
        int insertionPoint = GetRangeEnd(shape.Range);
        if (display)
        {
            dynamic paragraphRange = shape.Range.Paragraphs.Item(1).Range;
            if (TryMoveSelectionToFollowingParagraph(paragraphRange))
            {
                return;
            }

            insertionPoint = GetRangeEnd(paragraphRange);
            bool paragraphInserted = TryInsertParagraphAfter(paragraphRange);
            if (paragraphInserted &&
                (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1)))
            {
                return;
            }
        }

        if (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            if (!display)
            {
                NormalizePlainTextBaselineAroundRange(shape.Range);
            }

            return;
        }

        dynamic target = CreateDocumentRange(insertionPoint, insertionPoint);
        target.Select();
        MoveSelectionRight();
        if (!display)
        {
            NormalizePlainTextBaselineAroundRange(shape.Range);
        }

        EnsureSelectionOutsideFormula(equationId);
    }

    private bool TryMoveSelectionOutsideFormula(int position)
    {
        try
        {
            int safePosition = ClampDocumentPosition(position);
            dynamic target = _wordApplication.ActiveDocument.Range(safePosition, safePosition);
            if (RangeTouchesManagedFormula(target))
            {
                return false;
            }

            try
            {
                _wordApplication.Selection.SetRange(safePosition, safePosition);
            }
            catch
            {
                target.Select();
            }

            ResetSelectionFormulaTextFormatting();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void EnsureSelectionOutsideFormula(string equationId)
    {
        try
        {
            for (int i = 0; i < 12; i++)
            {
                dynamic range = _wordApplication.Selection.Range;
                object? control = TryGetParentContentControl(range)
                    ?? TryGetFirstManagedContentControl(range);
                if (control == null)
                {
                    return;
                }

                if (GetEquationId((dynamic)control) != equationId)
                {
                    return;
                }

                MoveSelectionRight();
            }
        }
        catch
        {
        }
    }

    private static bool TryInsertParagraphAfter(dynamic range)
    {
        try
        {
            range.InsertParagraphAfter();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void MoveSelectionRight()
    {
        try
        {
            _wordApplication.Selection.MoveRight(WdCharacter, 1, WdMove);
            ResetSelectionFormulaTextFormatting();
        }
        catch
        {
        }
    }

    private static dynamic GetContainingParagraphRange(dynamic control)
    {
        dynamic paragraphs = control.Range.Paragraphs;
        return paragraphs.Item(1).Range;
    }

    private void NormalizeNumberedParagraph(string equationId)
    {
        try
        {
            object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
            if (numberControl == null)
            {
                return;
            }

            object? equationControl = TryGetEquationControlById(equationId);
            if (equationControl != null)
            {
                ApplyNumberedParagraphLayout(
                    ((dynamic)numberControl).Range,
                    ((dynamic)equationControl).Range);
                return;
            }

            object? inlineShape = TryFindOleInlineShapeById(equationId);
            ApplyNumberedParagraphLayout(
                ((dynamic)numberControl).Range,
                inlineShape == null ? null : ((dynamic)inlineShape).Range);
        }
        catch
        {
        }
    }
}
