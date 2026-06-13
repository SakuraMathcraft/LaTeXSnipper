using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private const string InlineConversionAnchor = "\u2060";

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
                bool restoreInlineParagraph = false;
                bool useInlineAnchor =
                    metadata.NumberingMode == NumberingMode.None &&
                    metadata.DisplayMode == FormulaDisplayMode.Inline;
                if (useInlineAnchor)
                {
                    restoreInlineParagraph = HasContentAfterRangeInParagraph(inlineShape.Range);
                    int insertionPoint = GetRangeStart(inlineShape.Range);
                    InsertInlineConversionAnchorAfter(inlineShape.Range);
                    inlineShape.Delete();
                    insertionRange = GetInlineConversionRange(insertionPoint);
                    replacementOoxml = equationOoxml;
                }
                else
                {
                    insertionRange = ClearParagraphContent(GetContainingParagraphRange(inlineShape));
                    replacementOoxml = ooxml;
                }

                if (useInlineAnchor)
                {
                    try
                    {
                        insertionRange.InsertXML(replacementOoxml);
                    }
                    finally
                    {
                        RemoveInlineConversionAnchor(GetRangeStart(insertionRange));
                    }
                }
                else
                {
                    insertionRange.InsertXML(replacementOoxml);
                }

                if (restoreInlineParagraph)
                {
                    MergeFollowingParagraphIntoFormulaParagraph(metadata.Identity.EquationId);
                }

                ApplyManagedEquationStyleById(metadata);
                object insertedControl = FindFormulaControlById(metadata.Identity.EquationId);
                WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                    _wordApplication.ActiveDocument,
                    metadata.Identity.EquationId,
                    ReadManagedEquationFontSize(insertedControl));
                SaveFormulaMetadata(metadata);
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
        TryCom(() => control.LockContents = false);
        TryCom(() => control.LockContentControl = false);
        control.Delete(true);
        if (metadata.DisplayMode == FormulaDisplayMode.Display)
        {
            dynamic paragraph = CreateDocumentRange(insertionPoint, insertionPoint).Paragraphs.Item(1).Range;
            TryCom(() => paragraph.ParagraphFormat.Alignment = WdAlignParagraphCenter);
        }

        return insertionPoint;
    }

    private void InsertInlineConversionAnchorAfter(dynamic sourceRange)
    {
        int end = GetRangeEnd(sourceRange);
        dynamic anchor = CreateDocumentRange(end, end);
        anchor.Text = InlineConversionAnchor;
    }

    private dynamic GetInlineConversionRange(int insertionPoint)
    {
        return CreateDocumentRange(insertionPoint, insertionPoint + InlineConversionAnchor.Length);
    }

    private void RemoveInlineConversionAnchor(int insertionPoint)
    {
        int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
        int end = Math.Min(documentEnd, insertionPoint + 3);
        dynamic nearby = CreateDocumentRange(insertionPoint, end);
        string text = Convert.ToString(nearby.Text) ?? string.Empty;
        int anchorOffset = text.IndexOf(InlineConversionAnchor, StringComparison.Ordinal);
        if (anchorOffset < 0)
        {
            return;
        }

        CreateDocumentRange(
            insertionPoint + anchorOffset,
            insertionPoint + anchorOffset + InlineConversionAnchor.Length).Delete();
    }

    private bool HasContentAfterRangeInParagraph(dynamic sourceRange)
    {
        dynamic paragraphRange = sourceRange.Paragraphs.Item(1).Range;
        int start = GetRangeEnd(sourceRange);
        int end = Math.Max(start, GetRangeEnd(paragraphRange) - 1);
        if (end <= start)
        {
            return false;
        }

        dynamic trailing = CreateDocumentRange(start, end);
        string text = Convert.ToString(trailing.Text) ?? string.Empty;
        return !string.IsNullOrWhiteSpace(text)
            || Convert.ToInt32(trailing.ContentControls.Count) > 0
            || Convert.ToInt32(trailing.InlineShapes.Count) > 0
            || Convert.ToInt32(trailing.OMaths.Count) > 0;
    }

    private void MergeFollowingParagraphIntoFormulaParagraph(string equationId)
    {
        dynamic control = FindFormulaControlById(equationId);
        dynamic paragraphRange = GetContainingParagraphRange(control);
        int paragraphEnd = GetRangeEnd(paragraphRange);
        int documentEnd = GetRangeEnd(_wordApplication.ActiveDocument.Content);
        if (paragraphEnd >= documentEnd)
        {
            return;
        }

        CreateDocumentRange(paragraphEnd - 1, paragraphEnd).Delete();
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
        var selectedFormulas = new List<SelectedWordFormula>(CollectSelectedFormulas());
        AddOleInlineShapesInsideSelection(selectedFormulas);
        IReadOnlyList<object> selectedCommandControls = FindSelectedCommandControls();
        if (selectedFormulas.Count == 0 && selectedCommandControls.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        string[] deletedEquationIds = selectedFormulas
            .Select(formula => formula.Metadata.Identity.EquationId)
            .ToArray();
        var targets = new List<DeletionTarget>();
        foreach (SelectedWordFormula selected in selectedFormulas)
        {
            int start = GetFormulaStart(selected);
            targets.Add(new DeletionTarget(start, start, () => DeleteFormula(selected)));
        }

        foreach (object selected in selectedCommandControls)
        {
            dynamic control = selected;
            int start = GetRangeStart(control.Range);
            int end = GetRangeEnd(control.Range);
            targets.Add(new DeletionTarget(start, end, () => DeleteCommandControl(selected)));
        }

        ExecuteWithScreenUpdatingSuspended(() =>
        {
            DeleteTargetsInDocumentOrder(targets);
        });

        return Task.FromResult<IReadOnlyList<string>>(deletedEquationIds);
    }
}
