using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
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
        IReadOnlyList<SelectedWordFormula> formulas = CollectSelectedFormulas();
        if (formulas.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return formulas;
    }

    private IReadOnlyList<SelectedWordFormula> CollectSelectedFormulas()
    {
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        var formulas = new List<SelectedWordFormula>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        AddSelectedFormula(formulas, seen, TryGetParentContentControl(range));
        AddSelectedFormulasFromRange(formulas, seen, range);
        AddSelectedOleInlineShapes(formulas, seen, range);
        AddSelectedOleInlineShapesFromAnchor(formulas, seen, selection, range);
        return formulas;
    }

    private IReadOnlyList<WordFormulaEntry> CollectSelectedNativeWordFormulaEntries()
    {
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        var entries = new List<WordFormulaEntry>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        AddNativeWordFormulasFromRange(entries, seen, range);
        try
        {
            AddNativeWordFormulasFromRange(entries, seen, selection);
        }
        catch
        {
        }

        return entries;
    }

    private void AddNativeWordFormulasFromRange(ICollection<WordFormulaEntry> entries, ISet<string> seen, dynamic range)
    {
        try
        {
            dynamic equations = range.OMaths;
            int count = Convert.ToInt32(equations.Count);
            for (int index = 1; index <= count; index++)
            {
                AddNativeWordFormula(entries, seen, equations.Item(index));
            }
        }
        catch
        {
        }
    }

    private void AddNativeWordFormula(ICollection<WordFormulaEntry> entries, ISet<string> seen, object? candidate)
    {
        if (candidate == null)
        {
            return;
        }

        dynamic equation = candidate;
        dynamic range = equation.Range;
        if (TryGetParentContentControl(range) != null)
        {
            return;
        }

        int start = GetRangeStart(range);
        int end = GetRangeEnd(range);
        string key = start.ToString(System.Globalization.CultureInfo.InvariantCulture)
            + ":"
            + end.ToString(System.Globalization.CultureInfo.InvariantCulture);
        if (!seen.Add(key))
        {
            return;
        }

        string omml = ExtractNativeOmml(range);
        string mathMl = _ommlToMathMlConverter.Convert(omml);
        entries.Add(new WordFormulaEntry(start, mathMl, InferNativeFormulaDisplayMode(range)));
    }

    private static string ExtractNativeOmml(dynamic range)
    {
        string wordOpenXml = Convert.ToString(range.WordOpenXML) ?? string.Empty;
        if (string.IsNullOrWhiteSpace(wordOpenXml))
        {
            throw new InvalidOperationException("Selected Word equation did not expose OOXML.");
        }

        var document = XDocument.Parse(wordOpenXml, LoadOptions.PreserveWhitespace);
        XNamespace math = "http://schemas.openxmlformats.org/officeDocument/2006/math";
        XElement? equation = document.Descendants(math + "oMathPara").FirstOrDefault()
            ?? document.Descendants(math + "oMath").FirstOrDefault();
        if (equation == null)
        {
            throw new InvalidOperationException("Selected Word equation OOXML did not contain OMML.");
        }

        return equation.ToString(SaveOptions.DisableFormatting);
    }

    private FormulaDisplayMode InferNativeFormulaDisplayMode(dynamic formulaRange)
    {
        try
        {
            dynamic paragraphRange = formulaRange.Paragraphs.Item(1).Range;
            int paragraphStart = GetRangeStart(paragraphRange);
            int paragraphEnd = Math.Max(paragraphStart, GetRangeEnd(paragraphRange) - 1);
            int formulaStart = GetRangeStart(formulaRange);
            int formulaEnd = GetRangeEnd(formulaRange);
            dynamic leading = CreateDocumentRange(paragraphStart, Math.Max(paragraphStart, formulaStart));
            dynamic trailing = CreateDocumentRange(Math.Min(formulaEnd, paragraphEnd), paragraphEnd);
            string leadingText = Convert.ToString(leading.Text) ?? string.Empty;
            string trailingText = Convert.ToString(trailing.Text) ?? string.Empty;
            int equationCount = Convert.ToInt32(paragraphRange.OMaths.Count);
            return equationCount == 1
                && string.IsNullOrWhiteSpace(leadingText)
                && string.IsNullOrWhiteSpace(trailingText)
                    ? FormulaDisplayMode.Display
                    : FormulaDisplayMode.Inline;
        }
        catch
        {
            return FormulaDisplayMode.Inline;
        }
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

        FormulaMetadata metadata = LoadFormulaMetadata(
            inlineShape,
            equationId,
            RenderEngineKind.MathJaxSvg);
        formulas.Add(new SelectedWordFormula(inlineShape, metadata, isOleInlineShape: true));
    }

    private void AddOleInlineShapesInsideSelection(ICollection<SelectedWordFormula> formulas)
    {
        dynamic selectionRange = _wordApplication.Selection.Range;
        int selectionStart = GetRangeStart(selectionRange);
        int selectionEnd = GetRangeEnd(selectionRange);
        if (selectionEnd <= selectionStart)
        {
            return;
        }

        var seen = new HashSet<string>(
            formulas.Select(item => item.Metadata.Identity.EquationId),
            StringComparer.Ordinal);
        dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
        int count = Convert.ToInt32(inlineShapes.Count);
        for (int i = 1; i <= count; i++)
        {
            dynamic inlineShape = inlineShapes.Item(i);
            int shapeStart = GetRangeStart(inlineShape.Range);
            int shapeEnd = GetRangeEnd(inlineShape.Range);
            bool selected =
                (shapeStart >= selectionStart && shapeStart < selectionEnd) ||
                (shapeEnd > selectionStart && shapeEnd <= selectionEnd) ||
                RangesOverlap(selectionStart, selectionEnd, shapeStart, shapeEnd);
            if (selected)
            {
                AddSelectedOleInlineShape(formulas, seen, inlineShape);
            }
        }
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

        if (IsEquationControl(control))
        {
            FormulaMetadata metadata = LoadFormulaMetadata(control, equationId, RenderEngineKind.Omml);
            formulas.Add(new SelectedWordFormula(candidate, metadata));
            return;
        }

        if (IsNumberControl(control))
        {
            SelectedWordFormula formula = LoadFormulaFromNumberControl(equationId);
            formulas.Add(formula);
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

    private SelectedWordFormula LoadFormulaFromNumberControl(string equationId)
    {
        object? equationControl = TryGetEquationControlById(equationId);
        if (equationControl != null)
        {
            FormulaMetadata metadata = LoadFormulaMetadata(
                (dynamic)equationControl,
                equationId,
                RenderEngineKind.Omml);
            return new SelectedWordFormula(equationControl, metadata);
        }

        object? inlineShape = TryFindOleInlineShapeById(equationId);
        if (inlineShape != null)
        {
            FormulaMetadata metadata = LoadFormulaMetadata(
                (dynamic)inlineShape,
                equationId,
                RenderEngineKind.MathJaxSvg);
            return new SelectedWordFormula(inlineShape, metadata, isOleInlineShape: true);
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
    }
}
