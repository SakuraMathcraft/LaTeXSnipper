using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task<WordRenumberResult> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        int count = 0;
        int skipped = 0;
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

                if (!TryLoadAutomaticFormulaMetadata(control, equationId, RenderEngineKind.Omml, out FormulaMetadata? metadata))
                {
                    skipped++;
                    continue;
                }

                FormulaMetadata loadedMetadata = metadata!;
                if (loadedMetadata.NumberingMode == NumberingMode.Automatic)
                {
                    formulas.Add(new NumberedFormulaEntry(
                        equationId,
                        (object)control,
                        loadedMetadata,
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

                if (!TryLoadAutomaticFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg, out FormulaMetadata? metadata))
                {
                    skipped++;
                    continue;
                }

                FormulaMetadata loadedMetadata = metadata!;
                if (loadedMetadata.NumberingMode == NumberingMode.Automatic)
                {
                    formulas.Add(new NumberedFormulaEntry(
                        equationId,
                        (object)inlineShape,
                        loadedMetadata,
                        GetRangeStart(inlineShape.Range),
                        RenderEngineKind.MathJaxSvg));
                }
            }

            IReadOnlyDictionary<string, WordEquationNumberState> states = BuildEquationNumberStates(
                formulas,
                boundaries,
                settings);
            IReadOnlyDictionary<string, object> sequenceFields = BuildEquationSequenceFieldMap(document, formulas);
            foreach (NumberedFormulaEntry formula in formulas.OrderBy(entry => entry.Start))
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic formulaRange = formula.RenderEngine == RenderEngineKind.Omml
                    ? ((dynamic)formula.FormulaObject).Range
                    : ((dynamic)formula.FormulaObject).Range;
                double formulaHeight = formula.RenderEngine == RenderEngineKind.MathJaxSvg
                    ? Convert.ToDouble(((dynamic)formula.FormulaObject).Height)
                    : 0;
                if (!TryFindEquationNumberRange(formulaRange, formula.Metadata, out object? numberRange))
                {
                    skipped++;
                    continue;
                }

                if (!TryReplaceEquationNumberAtRange(
                    formula.Metadata,
                    states[formula.EquationId],
                    formulaHeight,
                    sequenceFields))
                {
                    skipped++;
                    continue;
                }

                count++;
            }

            UpdateEquationReferenceFields(document);
            foreach (NumberedFormulaEntry formula in formulas.Where(entry => entry.RenderEngine == RenderEngineKind.MathJaxSvg))
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic inlineShape = formula.FormulaObject;
                if (!TryFindEquationNumberRange(inlineShape.Range, formula.Metadata, out object? numberRange))
                {
                    skipped++;
                    continue;
                }

                ApplyEquationNumberBaseline(
                    numberRange,
                    Convert.ToDouble(inlineShape.Height));
            }
        });

        return Task.FromResult(new WordRenumberResult(count, skipped));
    }

    private bool TryLoadAutomaticFormulaMetadata(
        dynamic formulaObject,
        string equationId,
        RenderEngineKind renderEngine,
        out FormulaMetadata? metadata)
    {
        try
        {
            metadata = LoadFormulaMetadata(formulaObject, equationId, renderEngine);
            return true;
        }
        catch (InvalidOperationException exc) when (IsMetadataMissingError(exc))
        {
            metadata = null;
            return false;
        }
    }

    private static bool IsMetadataMissingError(InvalidOperationException exc)
    {
        return string.Equals(exc.Message, WordAddInText.Get("SelectedFormulaMetadataMissing"), StringComparison.Ordinal);
    }

    private bool TryFindEquationNumberRange(dynamic formulaRange, FormulaMetadata metadata, out object? numberRange)
    {
        try
        {
            numberRange = FindEquationNumberRange(formulaRange, metadata);
            return true;
        }
        catch (InvalidOperationException exc) when (IsMetadataMissingError(exc))
        {
            numberRange = null;
            return false;
        }
    }

    private static IReadOnlyDictionary<string, WordEquationNumberState> BuildEquationNumberStates(
        IEnumerable<NumberedFormulaEntry> formulas,
        IEnumerable<NumberingBoundaryEntry> boundaries,
        WordPluginSettings settings)
    {
        var states = new Dictionary<string, WordEquationNumberState>(StringComparer.Ordinal);
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

            states[formula.EquationId] = new WordEquationNumberState(
                BuildEquationNumberPrefix(settings, chapter, section),
                resetNextSequence,
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

    private WordEquationNumberState BuildEquationNumberStateAtPosition(int position, WordPluginSettings settings)
    {
        int chapter = 1;
        int section = 1;
        bool resetSequence = true;
        List<NumberingTimelineEntry> timeline = LoadNumberingTimelineEntriesBeforePosition(position);
        foreach (NumberingTimelineEntry entry in timeline.OrderBy(item => item.Start))
        {
            if (entry.Boundary == WordNumberingBoundary.Chapter)
            {
                chapter++;
                section = 1;
                resetSequence = true;
                continue;
            }

            if (entry.Boundary == WordNumberingBoundary.Section)
            {
                section++;
                resetSequence = true;
                continue;
            }

            if (entry.IsAutomaticFormula)
            {
                resetSequence = false;
            }
        }

        return new WordEquationNumberState(
            BuildEquationNumberPrefix(settings, chapter, section),
            resetSequence,
            settings.NumberEnclosure);
    }

    private List<NumberingTimelineEntry> LoadNumberingTimelineEntriesBeforePosition(int position)
    {
        var timeline = new List<NumberingTimelineEntry>();
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
                timeline.Add(new NumberingTimelineEntry(start, boundary, isAutomaticFormula: false));
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
                timeline.Add(new NumberingTimelineEntry(start, null, isAutomaticFormula: true));
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
                timeline.Add(new NumberingTimelineEntry(start, null, isAutomaticFormula: true));
            }
        }

        return timeline;
    }

    private static void UpdateEquationReferenceFields(dynamic document)
    {
        dynamic fields = document.Fields;
        int count = Convert.ToInt32(fields.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic field = fields.Item(index);
            string code = Convert.ToString(field.Code.Text) ?? string.Empty;
            if (code.IndexOf("REF " + WordEquationNumbering.BookmarkPrefix, StringComparison.Ordinal) >= 0)
            {
                TryCom(() => field.Update());
            }
        }
    }
}
