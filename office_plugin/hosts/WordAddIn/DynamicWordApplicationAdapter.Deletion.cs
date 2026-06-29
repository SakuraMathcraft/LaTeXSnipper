using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void DeleteFormula(SelectedWordFormula selected)
    {
        if (selected.IsOleInlineShape)
        {
            DeleteOleInlineShape(selected);
            return;
        }

        dynamic control = selected.ContentControl;
        string equationId = selected.Metadata.Identity.EquationId;
        if (selected.Metadata.NumberingMode != NumberingMode.None)
        {
            DeleteNumberedFormulaById(equationId);
            return;
        }

        control.Delete(true);
    }

    private void DeleteOleInlineShape(SelectedWordFormula selected)
    {
        dynamic inlineShape = selected.ContentControl;
        if (selected.Metadata.NumberingMode != NumberingMode.None)
        {
            DeleteNumberedFormulaParagraph(inlineShape.Range);
            return;
        }

        inlineShape.Delete();
    }

    private void DeleteNumberedFormulaById(string equationId)
    {
        object? equationControl = TryGetEquationControlById(equationId);
        object? oleInlineShape = TryFindOleInlineShapeById(equationId);
        if (equationControl != null)
        {
            DeleteNumberedFormulaParagraph(((dynamic)equationControl).Range);
            return;
        }

        if (oleInlineShape != null)
        {
            DeleteNumberedFormulaParagraph(((dynamic)oleInlineShape).Range);
        }
    }

    private static void DeleteNumberedFormulaParagraph(dynamic range)
    {
        dynamic paragraphRange = range.Paragraphs.Item(1).Range;
        paragraphRange.Delete();
    }

    private static int GetFormulaStart(SelectedWordFormula formula)
    {
        try
        {
            return Convert.ToInt32(((dynamic)formula.ContentControl).Range.Start);
        }
        catch
        {
            return 0;
        }
    }
}
