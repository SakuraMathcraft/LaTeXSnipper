using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void ResetSelectionFormulaTextFormatting()
    {
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        // Only reset typing at a paragraph end. Existing following text owns its formatting.
        if (GetRangeStart(range) != GetRangeEnd(range)
            || GetRangeEnd(range) < GetRangeEnd(range.Paragraphs.Item(1).Range) - 1)
        {
            return;
        }
        TryCom(() => selection.Font.Position = 0);
        TryCom(() => selection.Font.Superscript = 0);
        TryCom(() => selection.Font.Subscript = 0);
    }

    private void NormalizeManagedInlineEquationBaseline(FormulaMetadata metadata, object contentControl)
    {
        if (metadata.DisplayMode != FormulaDisplayMode.Inline || metadata.NumberingMode != NumberingMode.None)
        {
            return;
        }

        ResetManagedEquationBaseline(contentControl);
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
        string originalTag = ReadControlTag(control);
        RestoreManagedEquationControlIdentity(control, originalTag, metadata.Identity.EquationId);
    }

    private static void RestoreManagedEquationControlIdentity(dynamic control, string originalTag, string equationId)
    {
        string tag = string.Equals(
            WordFormulaMetadataStore.EquationIdFromTag(originalTag),
            equationId,
            StringComparison.Ordinal)
            ? originalTag
            : WordFormulaMetadataStore.BuildEquationTag(equationId);
        TryCom(() => control.Tag = tag);
        TryCom(() => control.Title = "LaTeXSnipper Equation");
    }

}
