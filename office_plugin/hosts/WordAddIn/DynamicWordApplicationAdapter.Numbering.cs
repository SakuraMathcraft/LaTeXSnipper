using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task ApplyAutomaticNumberAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            string equationId = metadata.Identity.EquationId;
            object? formulaObject = TryFindOleInlineShapeById(equationId)
                ?? TryGetEquationControlById(equationId);
            if (formulaObject == null)
            {
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
            }

            dynamic formulaRange = ((dynamic)formulaObject).Range;
            dynamic paragraphRange = formulaRange.Paragraphs.Item(1).Range;
            int paragraphStart = GetRangeStart(paragraphRange);
            WordNumberPlacement placement = WordPluginSettings.Load().NumberPlacement;
            object numberControl;
            if (placement == WordNumberPlacement.Left)
            {
                numberControl = InsertNumberControlAtRange(
                    CreateDocumentRange(paragraphStart, paragraphStart),
                    metadata);
                dynamic cursor = CreateDocumentRange(
                    GetRangeEnd(((dynamic)numberControl).Range),
                    GetRangeEnd(((dynamic)numberControl).Range));
                InsertTextAtRange(cursor, "\t");
            }
            else
            {
                CreateDocumentRange(paragraphStart, paragraphStart).Text = "\t";
                formulaObject = TryFindOleInlineShapeById(equationId)
                    ?? TryGetEquationControlById(equationId)
                    ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                formulaRange = ((dynamic)formulaObject).Range;
                dynamic cursor = CreateDocumentRange(
                    GetRangeEnd(formulaRange),
                    GetRangeEnd(formulaRange));
                InsertTextAtRange(cursor, "\t");
                numberControl = InsertNumberControlAtRange(cursor, metadata);
            }

            formulaObject = TryFindOleInlineShapeById(equationId)
                ?? TryGetEquationControlById(equationId)
                ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
            formulaRange = ((dynamic)formulaObject).Range;
            if (TryGetEquationControlById(equationId) is object equationControl)
            {
                HideContentControlChrome((dynamic)equationControl);
            }

            ApplyNumberedParagraphLayout(formulaRange, formulaRange);
            ApplyNumberControlVerticalAlignment(numberControl, metadata);
            SaveFormulaMetadata(metadata);
        });
        return Task.CompletedTask;
    }

    public int GetNextAutomaticNumber()
    {
        return WordFormulaMetadataStore.GetAutoNumberCounter(_wordApplication.ActiveDocument);
    }

    public string GetNextAutomaticNumberText()
    {
        dynamic document = _wordApplication.ActiveDocument;
        WordPluginSettings settings = WordPluginSettings.Load();
        return WordAutomaticNumberFormatter.Format(
            WordFormulaMetadataStore.GetAutoNumberChapter(document),
            WordFormulaMetadataStore.GetAutoNumberSection(document),
            WordFormulaMetadataStore.GetAutoNumberCounter(document),
            settings);
    }

    public void SetNextAutomaticNumber(int number)
    {
        WordFormulaMetadataStore.SetAutoNumberCounter(_wordApplication.ActiveDocument, number);
    }

    public Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        WordPluginSettings settings = WordPluginSettings.Load();
        IReadOnlyList<NumberingDocumentEntry> entries = LoadNumberingDocumentEntries();
        int chapter = settings.IncludeChapter ? 1 : 0;
        int section = settings.IncludeSection ? 1 : 0;
        int equation = 0;
        int count = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            Dictionary<string, object> metadataControls = LoadMetadataControlIndex();
            foreach (NumberingDocumentEntry entry in entries)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.Boundary == WordNumberingBoundary.Chapter)
                {
                    chapter++;
                    section = settings.IncludeSection ? 1 : 0;
                    equation = 0;
                    continue;
                }

                if (entry.Boundary == WordNumberingBoundary.Section)
                {
                    section++;
                    equation = 0;
                    continue;
                }

                NumberedFormulaEntry formula = entry.Formula!;
                if (formula.Metadata.NumberingMode != NumberingMode.Automatic)
                {
                    continue;
                }

                equation++;
                count++;
                string numberText = WordAutomaticNumberFormatter.Format(chapter, section, equation, settings);
                string currentNumberText = CleanRangeText(
                    Convert.ToString(((dynamic)formula.NumberControl).Range.Text) ?? string.Empty);
                if (string.Equals(currentNumberText, numberText, StringComparison.Ordinal) &&
                    string.Equals(formula.Metadata.NumberText, numberText, StringComparison.Ordinal))
                {
                    continue;
                }

                ReplaceNumberControlText(formula.NumberControl, numberText);
                FormulaMetadata renumbered = new FormulaMetadata(
                    formula.Metadata.Identity,
                    formula.Metadata.Latex,
                    FormulaDisplayMode.Display,
                    NumberingMode.Automatic,
                    numberText,
                    formula.Metadata.RenderEngine,
                    formula.Metadata.SchemaVersion,
                    formula.Metadata.FontColor,
                    formula.Metadata.FontStyle,
                    formula.Metadata.FontScale);
                ApplyNumberControlVerticalAlignment(formula.NumberControl, renumbered);
                SaveFormulaMetadata(renumbered, metadataControls);
            }

            UpdateFormulaReferences(entries);
        });

        SetNextAutomaticNumber(equation + 1);
        WordFormulaMetadataStore.SetAutoNumberChapter(_wordApplication.ActiveDocument, chapter);
        WordFormulaMetadataStore.SetAutoNumberSection(_wordApplication.ActiveDocument, section);
        return Task.FromResult(count);
    }
}
