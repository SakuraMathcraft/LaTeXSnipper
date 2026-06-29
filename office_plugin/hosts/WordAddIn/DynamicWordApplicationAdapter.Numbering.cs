using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        int count = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic document = _wordApplication.ActiveDocument;
            WordPluginSettings settings = WordPluginSettings.Load();
            var formulas = new List<NumberedFormulaEntry>();
            var boundaries = new List<NumberingBoundaryEntry>();
            dynamic controls = document.ContentControls;
            int controlCount = Convert.ToInt32(controls.Count);
            for (int index = 1; index <= controlCount; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic control = controls.Item(index);
                if (IsNumberingBoundary(control, out WordNumberingBoundary boundary))
                {
                    boundaries.Add(new NumberingBoundaryEntry(boundary, GetRangeStart(control.Range)));
                    continue;
                }

                string equationId = GetEquationControlId(control);
                if (string.IsNullOrWhiteSpace(equationId))
                {
                    continue;
                }

                FormulaMetadata metadata = LoadFormulaMetadata(control, equationId, RenderEngineKind.Omml);
                if (metadata.NumberingMode == NumberingMode.Automatic)
                {
                    formulas.Add(new NumberedFormulaEntry(
                        equationId,
                        (object)control,
                        metadata,
                        GetRangeStart(control.Range),
                        RenderEngineKind.Omml));
                }
            }

            dynamic inlineShapes = document.InlineShapes;
            int shapeCount = Convert.ToInt32(inlineShapes.Count);
            for (int index = 1; index <= shapeCount; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic inlineShape = inlineShapes.Item(index);
                string equationId = GetOleInlineShapeEquationId(inlineShape);
                if (string.IsNullOrWhiteSpace(equationId))
                {
                    continue;
                }

                FormulaMetadata metadata = LoadFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg);
                if (metadata.NumberingMode == NumberingMode.Automatic)
                {
                    formulas.Add(new NumberedFormulaEntry(
                        equationId,
                        (object)inlineShape,
                        metadata,
                        GetRangeStart(inlineShape.Range),
                        RenderEngineKind.MathJaxSvg));
                }
            }

            IReadOnlyDictionary<string, EquationNumberState> states = BuildEquationNumberStates(
                formulas,
                boundaries,
                settings);
            foreach (NumberedFormulaEntry formula in formulas.OrderBy(entry => entry.Start))
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic formulaRange = formula.RenderEngine == RenderEngineKind.Omml
                    ? ((dynamic)formula.FormulaObject).Range
                    : ((dynamic)formula.FormulaObject).Range;
                double formulaHeight = formula.RenderEngine == RenderEngineKind.MathJaxSvg
                    ? Convert.ToDouble(((dynamic)formula.FormulaObject).Height)
                    : 0;
                ReplaceEquationNumberAtRange(
                    FindEquationNumberRange(formulaRange, formula.Metadata),
                    formula.Metadata,
                    states[formula.EquationId],
                    formulaHeight);
                count++;
            }

            document.Fields.Update();
            foreach (NumberedFormulaEntry formula in formulas.Where(entry => entry.RenderEngine == RenderEngineKind.MathJaxSvg))
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic inlineShape = formula.FormulaObject;
                ApplyEquationNumberBaseline(
                    FindEquationNumberRange(inlineShape.Range, formula.Metadata),
                    Convert.ToDouble(inlineShape.Height));
            }
        });

        return Task.FromResult(count);
    }

    private static IReadOnlyDictionary<string, EquationNumberState> BuildEquationNumberStates(
        IEnumerable<NumberedFormulaEntry> formulas,
        IEnumerable<NumberingBoundaryEntry> boundaries,
        WordPluginSettings settings)
    {
        var states = new Dictionary<string, EquationNumberState>(StringComparer.Ordinal);
        int chapter = 1;
        int section = 1;
        bool resetNextSequence = true;
        var timeline = new List<(int Start, NumberedFormulaEntry? Formula, NumberingBoundaryEntry? Boundary)>();
        timeline.AddRange(formulas.Select(formula => (
            Start: formula.Start,
            Formula: (NumberedFormulaEntry?)formula,
            Boundary: (NumberingBoundaryEntry?)null)));
        timeline.AddRange(boundaries.Select(boundary => (
            Start: boundary.Start,
            Formula: (NumberedFormulaEntry?)null,
            Boundary: (NumberingBoundaryEntry?)boundary)));

        foreach ((int _, NumberedFormulaEntry? formula, NumberingBoundaryEntry? boundary) in timeline.OrderBy(item => item.Start))
        {
            if (boundary != null)
            {
                if (boundary.Boundary == WordNumberingBoundary.Chapter)
                {
                    chapter++;
                    section = 1;
                }
                else
                {
                    section++;
                }

                resetNextSequence = true;
                continue;
            }

            if (formula == null)
            {
                continue;
            }

            states[formula.EquationId] = new EquationNumberState(
                BuildEquationNumberPrefix(settings, chapter, section),
                resetNextSequence,
                settings.NumberFormat,
                settings.NumberEnclosure);
            resetNextSequence = false;
        }

        return states;
    }

    private static string BuildEquationNumberPrefix(WordPluginSettings settings, int chapter, int section)
    {
        var parts = new List<string>(capacity: 2);
        if (settings.IncludeChapter)
        {
            parts.Add(chapter.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }

        if (settings.IncludeSection)
        {
            parts.Add(section.ToString(System.Globalization.CultureInfo.InvariantCulture));
        }

        return parts.Count == 0
            ? string.Empty
            : string.Join(settings.NumberSeparator, parts) + settings.NumberSeparator;
    }

    private EquationNumberState BuildEquationNumberStateAtPosition(int position, WordPluginSettings settings)
    {
        int chapter = 1;
        int section = 1;
        bool resetSequence = true;
        var timeline = new List<(int Start, WordNumberingBoundary? Boundary, bool IsFormula)>();
        dynamic document = _wordApplication.ActiveDocument;
        dynamic controls = document.ContentControls;
        int controlCount = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= controlCount; index++)
        {
            dynamic control = controls.Item(index);
            int start = GetRangeStart(control.Range);
            if (start >= position)
            {
                continue;
            }

            if (IsNumberingBoundary(control, out WordNumberingBoundary boundary))
            {
                timeline.Add((start, boundary, IsFormula: false));
                continue;
            }

            string equationId = GetEquationControlId(control);
            if (string.IsNullOrWhiteSpace(equationId))
            {
                continue;
            }

            FormulaMetadata metadata = LoadFormulaMetadata(control, equationId, RenderEngineKind.Omml);
            if (metadata.NumberingMode == NumberingMode.Automatic)
            {
                timeline.Add((start, null, IsFormula: true));
            }
        }

        dynamic inlineShapes = document.InlineShapes;
        int shapeCount = Convert.ToInt32(inlineShapes.Count);
        for (int index = 1; index <= shapeCount; index++)
        {
            dynamic inlineShape = inlineShapes.Item(index);
            int start = GetRangeStart(inlineShape.Range);
            if (start >= position)
            {
                continue;
            }

            string equationId = GetOleInlineShapeEquationId(inlineShape);
            if (string.IsNullOrWhiteSpace(equationId))
            {
                continue;
            }

            FormulaMetadata metadata = LoadFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg);
            if (metadata.NumberingMode == NumberingMode.Automatic)
            {
                timeline.Add((start, null, IsFormula: true));
            }
        }

        foreach ((int _, WordNumberingBoundary? boundary, bool isFormula) in timeline.OrderBy(item => item.Start))
        {
            if (boundary == WordNumberingBoundary.Chapter)
            {
                chapter++;
                section = 1;
                resetSequence = true;
                continue;
            }

            if (boundary == WordNumberingBoundary.Section)
            {
                section++;
                resetSequence = true;
                continue;
            }

            if (isFormula)
            {
                resetSequence = false;
            }
        }

        return new EquationNumberState(
            BuildEquationNumberPrefix(settings, chapter, section),
            resetSequence,
            settings.NumberFormat,
            settings.NumberEnclosure);
    }
}
