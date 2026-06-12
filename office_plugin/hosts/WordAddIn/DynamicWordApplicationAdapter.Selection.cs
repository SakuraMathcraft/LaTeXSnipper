using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        SelectedWordFormula selected = FindSelectedFormula();
        return Task.FromResult(selected.Metadata);
    }

    public Task<IReadOnlyList<WordFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        IReadOnlyList<WordFormulaEntry> entries = FindSelectedFormulas()
            .Select(item => new WordFormulaEntry(GetFormulaStart(item), item.Metadata))
            .OrderByDescending(item => item.Start)
            .ToArray();
        return Task.FromResult(entries);
    }

    public Task UpdateFormulaAsync(string equationId, string ooxml, string equationOoxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        ValidateManagedEquationInput(equationOoxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            object? ole = TryFindOleInlineShapeById(equationId);
            if (ole != null)
            {
                dynamic inlineShape = ole;
                dynamic insertionRange;
                string replacementOoxml;
                if (metadata.NumberingMode == NumberingMode.None)
                {
                    int insertionPoint = GetRangeStart(inlineShape.Range);
                    inlineShape.Delete();
                    insertionRange = CreateDocumentRange(insertionPoint, insertionPoint);
                    replacementOoxml = equationOoxml;
                }
                else
                {
                    insertionRange = ClearParagraphContent(GetContainingParagraphRange(inlineShape));
                    replacementOoxml = ooxml;
                }

                insertionRange.InsertXML(replacementOoxml);
                if (metadata.NumberingMode == NumberingMode.None &&
                    metadata.DisplayMode == FormulaDisplayMode.Display)
                {
                    dynamic inserted = FindFormulaControlById(metadata.Identity.EquationId);
                    TryCom(() => inserted.Range.ParagraphFormat.Alignment = WdAlignParagraphCenter);
                }

                ApplyManagedEquationStyleById(metadata);
                object insertedControl = FindFormulaControlById(metadata.Identity.EquationId);
                WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                    _wordApplication.ActiveDocument,
                    metadata.Identity.EquationId,
                    ReadManagedEquationFontSize(insertedControl));
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
                MoveSelectionAfterInsertedFormula(metadata, display);
                return;
            }

            object control = FindFormulaControlById(equationId);
            double fontSizePoints = ReadManagedEquationFontSize(control);
            ReplaceFormulaContent(control, ooxml, equationOoxml, metadata);
            ApplyManagedEquationFontSizeById(
                metadata.Identity.EquationId,
                metadata.FontScale == 1 ? fontSizePoints : WordOleBaseFontPoints * metadata.FontScale);
            ApplyManagedEquationStyleById(metadata);
        });
        return Task.CompletedTask;
    }

    private int RemoveOmmlConversionSource(dynamic control, FormulaMetadata metadata)
    {
        if (metadata.NumberingMode != NumberingMode.None)
        {
            dynamic insertionRange = ClearParagraphContent(GetContainingParagraphRange(control));
            return GetRangeStart(insertionRange);
        }

        int insertionPoint = GetRangeStart(control.Range);
        control.Delete(true);
        if (metadata.DisplayMode == FormulaDisplayMode.Display)
        {
            dynamic paragraph = CreateDocumentRange(insertionPoint, insertionPoint).Paragraphs.Item(1).Range;
            TryCom(() => paragraph.ParagraphFormat.Alignment = WdAlignParagraphCenter);
        }

        return insertionPoint;
    }

    public bool HasCustomFormulaScale(FormulaMetadata metadata)
    {
        if (metadata.RenderEngine != RenderEngineKind.MathJaxSvg)
        {
            return false;
        }

        object? shape = TryFindOleInlineShapeById(metadata.Identity.EquationId);
        if (shape == null)
        {
            return false;
        }

        if (!WordFormulaMetadataStore.TryLoadOleNaturalSize(
            _wordApplication.ActiveDocument,
            metadata.Identity.EquationId,
            out double naturalWidth,
            out double naturalHeight))
        {
            return false;
        }

        dynamic inlineShape = shape;
        double width = Convert.ToDouble(inlineShape.Width, System.Globalization.CultureInfo.InvariantCulture);
        double height = Convert.ToDouble(inlineShape.Height, System.Globalization.CultureInfo.InvariantCulture);
        return Math.Abs(width / naturalWidth - 1) > 0.01
            || Math.Abs(height / naturalHeight - 1) > 0.01;
    }

    public Task<IReadOnlyList<string>> DeleteSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (TryDeleteSelectedCommandControl())
        {
            return Task.FromResult<IReadOnlyList<string>>(Array.Empty<string>());
        }

        var selectedFormulas = new List<SelectedWordFormula>(FindSelectedFormulas());
        string[] deletedEquationIds = selectedFormulas
            .Select(formula => formula.Metadata.Identity.EquationId)
            .ToArray();
        selectedFormulas.Sort((left, right) => GetFormulaStart(right).CompareTo(GetFormulaStart(left)));
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach (SelectedWordFormula selected in selectedFormulas)
            {
                DeleteFormula(selected);
            }
        });

        return Task.FromResult<IReadOnlyList<string>>(deletedEquationIds);
    }
}
