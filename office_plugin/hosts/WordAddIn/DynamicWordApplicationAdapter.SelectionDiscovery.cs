using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private SelectedWordFormula FindSelectedFormula()
    {
        IReadOnlyList<SelectedWordFormula> formulas = FindSelectedFormulas();
        return formulas[0];
    }

    private IReadOnlyList<SelectedWordFormula> FindSelectedFormulas()
    {
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        var formulas = new List<SelectedWordFormula>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        AddSelectedFormula(formulas, seen, TryGetParentContentControl(range));
        AddSelectedFormulasFromRange(formulas, seen, range);
        AddSelectedOleInlineShapes(formulas, seen, range);
        AddSelectedOleInlineShapesFromAnchor(formulas, seen, selection, range);
        if (formulas.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return formulas;
    }

    private void AddSelectedFormulasFromRange(ICollection<SelectedWordFormula> formulas, ISet<string> seen, dynamic range)
    {
        try
        {
            dynamic controls = range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                AddSelectedFormula(formulas, seen, controls.Item(i));
            }
        }
        catch
        {
        }
    }

    private void AddSelectedOleInlineShapes(ICollection<SelectedWordFormula> formulas, ISet<string> seen, dynamic range)
    {
        try
        {
            dynamic inlineShapes = range.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                AddSelectedOleInlineShape(formulas, seen, inlineShapes.Item(i));
            }
        }
        catch
        {
        }

        try
        {
            dynamic inlineShapes = _wordApplication.Selection.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                AddSelectedOleInlineShape(formulas, seen, inlineShapes.Item(i));
            }
        }
        catch
        {
        }

    }

    private void AddSelectedOleInlineShapesFromAnchor(
        ICollection<SelectedWordFormula> formulas,
        ISet<string> seen,
        dynamic selection,
        dynamic selectionRange)
    {
        try
        {
            int selectionType = Convert.ToInt32(selection.Type);
            if (selectionType != 6 && selectionType != 7 && selectionType != 8)
            {
                return;
            }

            int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
            int start = Math.Max(0, GetRangeStart(selectionRange) - 1);
            int end = Math.Min(documentEnd, Math.Max(start + 1, GetRangeEnd(selectionRange) + 1));
            AddSelectedOleInlineShapes(
                formulas,
                seen,
                CreateDocumentRange(start, end));

            if (formulas.Count == 0)
            {
                dynamic paragraphRange = selectionRange.Paragraphs.Item(1).Range;
                AddSelectedOleInlineShapes(formulas, seen, paragraphRange);
            }
        }
        catch
        {
        }
    }

    private void AddSelectedOleInlineShape(ICollection<SelectedWordFormula> formulas, ISet<string> seen, object? candidate)
    {
        if (candidate == null)
        {
            return;
        }

        dynamic inlineShape = candidate;
        string equationId = GetOleInlineShapeEquationId(inlineShape);
        if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
        {
            return;
        }

        FormulaMetadata metadata = LoadFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg);
        formulas.Add(new SelectedWordFormula(inlineShape, metadata, isOleInlineShape: true));
    }

    private void AddSelectedFormula(ICollection<SelectedWordFormula> formulas, ISet<string> seen, object? candidate)
    {
        if (candidate == null)
        {
            return;
        }

        dynamic control = candidate;
        string equationId = GetEquationId(control);
        if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
        {
            return;
        }

        if (IsEquationControl(control) || IsNumberControl(control))
        {
            FormulaMetadata metadata = LoadFormulaMetadata(control, equationId, RenderEngineKind.Omml);
            formulas.Add(new SelectedWordFormula(candidate, metadata));
        }
    }

    private static bool IsNumberControl(dynamic control)
    {
        try
        {
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            return !string.IsNullOrWhiteSpace(WordFormulaMetadataStore.EquationIdFromNumberTag(tag));
        }
        catch
        {
            return false;
        }
    }

    private object FindFormulaControlById(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int i = 1; i <= count; i++)
        {
            dynamic control = controls.Item(i);
            if (GetEquationControlId(control) == equationId)
            {
                return control;
            }
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
    }

    private object FindOleInlineShapeById(string equationId)
    {
        object? inlineShape = TryFindOleInlineShapeById(equationId);
        if (inlineShape == null)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return inlineShape;
    }

    private object? TryFindOleInlineShapeById(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return null;
        }

        try
        {
            dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic inlineShape = inlineShapes.Item(i);
                if (string.Equals(GetOleInlineShapeEquationId(inlineShape), equationId, StringComparison.Ordinal))
                {
                    return inlineShape;
                }
            }
        }
        catch
        {
        }

        return null;
    }
}
