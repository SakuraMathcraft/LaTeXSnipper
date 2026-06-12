using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public int GetNextAutomaticNumber()
    {
        return WordFormulaMetadataStore.GetAutoNumberCounter(_wordApplication.ActiveDocument);
    }

    public void SetNextAutomaticNumber(int number)
    {
        WordFormulaMetadataStore.SetAutoNumberCounter(_wordApplication.ActiveDocument, number);
    }

    public Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        WordPluginSettings settings = WordPluginSettings.Load();
        IReadOnlyList<NumberingDocumentEntry> entries = LoadNumberingDocumentEntries(settings);
        int chapter = settings.IncludeChapter ? 1 : 0;
        int section = settings.IncludeSection ? 1 : 0;
        int equation = 0;
        int count = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
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
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, renumbered);
            }

            UpdateFormulaReferences(entries);
        });

        SetNextAutomaticNumber(equation + 1);
        return Task.FromResult(count);
    }
}
