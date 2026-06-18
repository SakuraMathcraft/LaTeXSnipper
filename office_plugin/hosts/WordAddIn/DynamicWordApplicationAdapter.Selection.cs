using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private const string InlineConversionSlot = "\u2060";

    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        SelectedWordFormula selected = FindSelectedFormula();
        return Task.FromResult(selected.Metadata);
    }

    public Task<IReadOnlyList<WordFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        IReadOnlyList<WordFormulaEntry> entries = CollectSelectedFormulas()
            .Select(item => new WordFormulaEntry(GetFormulaStart(item), item.Metadata))
            .Concat(CollectSelectedNativeWordFormulaEntries())
            .OrderByDescending(item => item.Start)
            .ToArray();
        if (entries.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return Task.FromResult(entries);
    }

    public Task UpdateFormulaAsync(
        string equationId,
        string ooxml,
        string equationOoxml,
        string equationContentOoxml,
        FormulaMetadata metadata,
        bool display,
        CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        ValidateManagedEquationInput(equationOoxml, metadata);
        ValidateManagedEquationContentInput(equationContentOoxml);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            object? ole = TryFindOleInlineShapeById(equationId);
            if (ole != null)
            {
                dynamic inlineShape = ole;
                double oleFontSizePoints = ReadOleEquivalentFontSize(inlineShape);
                dynamic insertionRange;
                string replacementOoxml;
                if (metadata.NumberingMode == NumberingMode.None)
                {
                    bool restoreInlineParagraph =
                        metadata.DisplayMode == FormulaDisplayMode.Inline &&
                        HasContentAfterRangeInParagraph(inlineShape.Range);
                    int insertionPoint = GetRangeStart(inlineShape.Range);
                    inlineShape.Delete();
                    insertionRange = CreateInlineConversionSlot(insertionPoint);
                    replacementOoxml = equationOoxml;
                    insertionRange.InsertXML(replacementOoxml);
                    if (restoreInlineParagraph)
                    {
                        MergeFollowingParagraphIntoFormulaParagraph(metadata.Identity.EquationId);
                    }
                }
                else
                {
                    insertionRange = ClearParagraphContent(GetContainingParagraphRange(inlineShape));
                    replacementOoxml = ooxml;
                    insertionRange.InsertXML(replacementOoxml);
                }

                if (metadata.NumberingMode == NumberingMode.None &&
                    metadata.DisplayMode == FormulaDisplayMode.Display)
                {
                    dynamic inserted = FindFormulaControlById(metadata.Identity.EquationId);
                    TryCom(() => inserted.Range.ParagraphFormat.Alignment = WdAlignParagraphCenter);
                }

                ApplyManagedEquationStyleById(metadata);
                object insertedControl = FindFormulaControlById(metadata.Identity.EquationId);
                ApplyManagedEquationFontSize(insertedControl, oleFontSizePoints);
                NormalizeManagedInlineEquationBaseline(metadata, insertedControl);
                WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                    _wordApplication.ActiveDocument,
                    metadata.Identity.EquationId,
                    oleFontSizePoints);
                SaveFormulaMetadata(metadata);
                MoveSelectionAfterInsertedFormula(metadata, display);
                return;
            }

            object control = FindFormulaControlById(equationId);
            double fontSizePoints = ReadManagedEquationFontSize(control);
            FormulaMetadata currentMetadata = LoadFormulaMetadata((dynamic)control, equationId, RenderEngineKind.Omml);
            ReplaceFormulaContent(control, ooxml, equationContentOoxml, metadata, currentMetadata);
            ApplyManagedEquationFontSizeById(
                metadata.Identity.EquationId,
                ScaleFontSize(fontSizePoints, metadata.FontScale));
            ApplyManagedEquationStyleById(metadata);
            NormalizeManagedInlineEquationBaseline(metadata, FindFormulaControlById(metadata.Identity.EquationId));
            SaveFormulaMetadata(metadata);
        });
        return Task.CompletedTask;
    }

    private double ReadOleEquivalentFontSize(dynamic inlineShape)
    {
        double fontSize = ReadPointSize(inlineShape.Range.Font.Size);
        if (fontSize <= 0)
        {
            fontSize = GetCurrentFontSizePoints();
        }

        try
        {
            double currentHeight = Convert.ToDouble(inlineShape.Height, System.Globalization.CultureInfo.InvariantCulture);
            string tag = Convert.ToString(inlineShape.AlternativeText) ?? string.Empty;
            if (WordFormulaMetadataStore.TryLoadOleNaturalSize(
                    _wordApplication.ActiveDocument,
                    tag,
                    out double naturalWidth,
                    out double naturalHeight) &&
                naturalHeight > 0 &&
                currentHeight > 0)
            {
                fontSize *= Math.Max(0.05, currentHeight / naturalHeight);
            }
        }
        catch
        {
        }

        return Math.Max(1, fontSize);
    }

    private dynamic RemoveOmmlConversionSource(dynamic control, FormulaMetadata metadata)
    {
        if (metadata.NumberingMode != NumberingMode.None)
        {
            return ClearParagraphContent(GetContainingParagraphRange(control));
        }

        int insertionPoint = GetRangeStart(control.Range);
        TryCom(() => control.LockContents = false);
        TryCom(() => control.LockContentControl = false);
        dynamic equations = control.Range.OMaths;
        for (int index = Convert.ToInt32(equations.Count); index >= 1; index--)
        {
            equations.Item(index).Remove();
        }

        control.Range.Text = InlineConversionSlot;
        control.Delete(false);
        dynamic insertionRange = CreateDocumentRange(
            insertionPoint,
            insertionPoint + InlineConversionSlot.Length);
        if (metadata.DisplayMode == FormulaDisplayMode.Display)
        {
            dynamic paragraph = insertionRange.Paragraphs.Item(1).Range;
            TryCom(() => paragraph.ParagraphFormat.Alignment = WdAlignParagraphCenter);
        }

        return insertionRange;
    }

    private dynamic CreateInlineConversionSlot(int insertionPoint)
    {
        dynamic slot = CreateDocumentRange(insertionPoint, insertionPoint);
        slot.Text = InlineConversionSlot;
        return CreateDocumentRange(
            insertionPoint,
            insertionPoint + InlineConversionSlot.Length);
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
        if (paragraphEnd < documentEnd)
        {
            CreateDocumentRange(paragraphEnd - 1, paragraphEnd).Delete();
        }
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

        dynamic inlineShape = shape;
        if (!WordFormulaMetadataStore.TryLoadOleNaturalSize(
            _wordApplication.ActiveDocument,
            Convert.ToString(inlineShape.AlternativeText) ?? string.Empty,
            out double naturalWidth,
            out double naturalHeight))
        {
            return false;
        }

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
