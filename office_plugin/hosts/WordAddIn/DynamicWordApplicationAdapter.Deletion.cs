using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private void DeleteFormula(SelectedWordFormula selected)
    {
        dynamic formula = selected.ContentControl;
        if (selected.Metadata.NumberingMode != NumberingMode.None)
        {
            RemoveFormulaForReplacement(formula.Range, selected.Metadata.Identity.EquationId, display: false);
        }
        else if (selected.IsOleInlineShape)
        {
            formula.Delete();
        }
        else
        {
            formula.Delete(true);
        }
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
