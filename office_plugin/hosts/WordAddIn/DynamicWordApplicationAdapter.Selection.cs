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
        SelectedWordFormula selected = EnsureUniqueFormulaIdentity(FindSelectedFormula());
        return Task.FromResult(selected.Metadata);
    }

    public Task<WordFormulaEditTarget> LoadSelectedFormulaTargetAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        SelectedWordFormula selected = EnsureUniqueFormulaIdentity(FindSelectedFormula());
        return Task.FromResult(new WordFormulaEditTarget(
            CurrentDocument,
            _wordApplication.ActiveWindow,
            selected.ContentControl,
            Convert.ToInt32(_wordApplication.ActiveWindow.Hwnd),
            selected.Metadata,
            selected.IsOleInlineShape,
            GetFormulaEditTargetFontSize(selected)));
    }

    public WordFormulaEditTarget? TryCaptureOleFormulaEditTarget(
        object document,
        object window,
        object selection)
    {
        if (document == null)
        {
            throw new ArgumentNullException(nameof(document));
        }

        if (window == null)
        {
            throw new ArgumentNullException(nameof(window));
        }

        if (selection == null)
        {
            throw new ArgumentNullException(nameof(selection));
        }

        SelectedWordFormula selected;
        try
        {
            using (UseDocument(document))
            {
                selected = EnsureUniqueFormulaIdentity(FindSelectedFormula(selection));
            }
        }
        catch (InvalidOperationException)
        {
            return null;
        }

        return selected.IsOleInlineShape
            ? new WordFormulaEditTarget(
                document,
                window,
                selected.ContentControl,
                Convert.ToInt32(((dynamic)window).Hwnd),
                selected.Metadata,
                isOle: true,
                ReadOleEquivalentFontSize((dynamic)selected.ContentControl))
            : null;
    }

    private double GetFormulaEditTargetFontSize(SelectedWordFormula selected)
    {
        return selected.IsOleInlineShape
            ? ReadOleEquivalentFontSize((dynamic)selected.ContentControl)
            : ReadManagedEquationFontSize(selected.ContentControl);
    }

    public bool IsFormulaEditTargetValid(WordFormulaEditTarget target)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        try
        {
            dynamic document = target.Document;
            if (!string.Equals(
                WordDocumentIdentityStore.GetOrCreate(document),
                target.Metadata.Identity.DocumentId,
                StringComparison.Ordinal))
            {
                return false;
            }

            dynamic capturedObject = target.FormulaObject;
            string capturedEquationId = target.IsOle
                ? GetOleInlineShapeEquationId(capturedObject)
                : GetEquationControlId(capturedObject);
            if (!string.Equals(
                capturedEquationId,
                target.Metadata.Identity.EquationId,
                StringComparison.Ordinal))
            {
                return false;
            }

            dynamic inlineShapes = document.InlineShapes;
            int matches = 0;
            for (int index = 1; index <= Convert.ToInt32(inlineShapes.Count); index++)
            {
                dynamic inlineShape = inlineShapes.Item(index);
                if (string.Equals(
                    GetOleInlineShapeEquationId(inlineShape),
                    target.Metadata.Identity.EquationId,
                    StringComparison.Ordinal))
                {
                    matches++;
                }
            }

            if (target.IsOle)
            {
                return matches == 1;
            }

            dynamic controls = document.ContentControls;
            for (int index = 1; index <= Convert.ToInt32(controls.Count); index++)
            {
                if (string.Equals(
                    GetEquationControlId(controls.Item(index)),
                    target.Metadata.Identity.EquationId,
                    StringComparison.Ordinal))
                {
                    matches++;
                }
            }

            return matches == 1;
        }
        catch
        {
            return false;
        }
    }

    public Task<IReadOnlyList<WordFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        IReadOnlyList<WordFormulaEntry> entries = CollectSelectedFormulas()
            .Select(EnsureUniqueFormulaIdentity)
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

    public bool ContainsFormula(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return false;
        }

        return TryGetEquationControlById(equationId) != null ||
            TryFindOleInlineShapeById(equationId) != null;
    }

    public bool ContainsNativeWordFormula(int start)
    {
        dynamic equations = CurrentDocument.OMaths;
        int count = Convert.ToInt32(equations.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic equation = equations.Item(index);
            if (GetRangeStart(equation.Range) == start)
            {
                return true;
            }
        }

        return false;
    }

    private SelectedWordFormula EnsureUniqueFormulaIdentity(SelectedWordFormula selected)
    {
        string documentId = WordDocumentIdentityStore.GetOrCreate(CurrentDocument);
        string equationId = selected.Metadata.Identity.EquationId;
        if (string.Equals(selected.Metadata.Identity.DocumentId, documentId, StringComparison.Ordinal)
            && CountManagedFormulasById(equationId) <= 1)
        {
            return selected;
        }

        FormulaMetadata metadata = WithNewIdentity(selected.Metadata, documentId);
        SaveFormulaMetadata(selected.ContentControl, metadata);
        return new SelectedWordFormula(selected.ContentControl, metadata, selected.IsOleInlineShape);
    }

    private int CountManagedFormulasById(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return 0;
        }

        int count = 0;
        dynamic controls = CurrentDocument.ContentControls;
        int controlCount = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= controlCount; index++)
        {
            if (string.Equals(GetEquationControlId(controls.Item(index)), equationId, StringComparison.Ordinal))
            {
                count++;
            }
        }

        dynamic inlineShapes = CurrentDocument.InlineShapes;
        int shapeCount = Convert.ToInt32(inlineShapes.Count);
        for (int index = 1; index <= shapeCount; index++)
        {
            if (string.Equals(GetOleInlineShapeEquationId(inlineShapes.Item(index)), equationId, StringComparison.Ordinal))
            {
                count++;
            }
        }

        return count;
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
        return UpdateFormulaCoreAsync(
            equationId,
            ooxml,
            equationOoxml,
            equationContentOoxml,
            metadata,
            display,
            moveSelection: true,
            cancellationToken);
    }

    private Task UpdateFormulaCoreAsync(
        string equationId,
        string ooxml,
        string equationOoxml,
        string equationContentOoxml,
        FormulaMetadata metadata,
        bool display,
        bool moveSelection,
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
                int insertionPoint = GetRangeStart(inlineShape.Range);
                double oleFontSizePoints = ReadOleEquivalentFontSize(inlineShape);
                dynamic insertionRange;
                string replacementOoxml;
                if (metadata.NumberingMode == NumberingMode.None)
                {
                    bool restoreInlineParagraph =
                        metadata.DisplayMode == FormulaDisplayMode.Inline &&
                        HasContentAfterRangeInParagraph(inlineShape.Range);
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
                if (metadata.NumberingMode != NumberingMode.None)
                {
                    dynamic insertedRange = ((dynamic)insertedControl).Range;
                    ApplyNumberedFormulaParagraphLayout(insertedRange);
                    if (metadata.NumberingMode == NumberingMode.Automatic)
                    {
                        InsertManagedEquationNumber(
                            insertedControl,
                            metadata,
                            BuildEquationNumberStateAtPosition(insertionPoint, WordPluginSettings.Load()));
                    }
                }

                NormalizeManagedInlineEquationBaseline(metadata, insertedControl);
                SaveFormulaMetadata(metadata);
                if (moveSelection)
                {
                    MoveSelectionAfterInsertedFormula(metadata, display);
                }
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

    public async Task UpdateFormulaAsync(
        WordFormulaEditTarget target,
        string ooxml,
        string equationOoxml,
        string equationContentOoxml,
        FormulaMetadata metadata,
        bool display,
        CancellationToken cancellationToken)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        if (!IsFormulaEditTargetValid(target)
            || !string.Equals(
                target.Metadata.Identity.DocumentId,
                metadata.Identity.DocumentId,
                StringComparison.Ordinal)
            || !string.Equals(
                target.Metadata.Identity.EquationId,
                metadata.Identity.EquationId,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        using (UseDocument(target.Document))
        {
            await UpdateFormulaCoreAsync(
                target.Metadata.Identity.EquationId,
                ooxml,
                equationOoxml,
                equationContentOoxml,
                metadata,
                display,
                moveSelection: false,
                cancellationToken).ConfigureAwait(true);
        }
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
            if (WordFormulaMetadataStore.TryLoadOleNaturalSize(
                    inlineShape,
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
        int documentEnd = GetRangeEnd(CurrentDocument.Content);
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
            inlineShape,
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
        IReadOnlyList<object> selectedReferenceFields = FindSelectedReferenceFields();
        object? selectedPendingReference = FindSelectedPendingReferencePlaceholder();
        if (selectedFormulas.Count == 0 &&
            selectedCommandControls.Count == 0 &&
            selectedReferenceFields.Count == 0 &&
            selectedPendingReference == null)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        string[] deletedEquationIds = selectedFormulas
            .Select(formula => formula.Metadata.Identity.EquationId)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        var targets = new List<(int Start, int End, Action Delete)>();
        var formulaDeleteIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (SelectedWordFormula selected in selectedFormulas)
        {
            formulaDeleteIds.Add(selected.Metadata.Identity.EquationId);
            int start = GetFormulaStart(selected);
            targets.Add((start, start, () => DeleteFormula(selected)));
        }

        foreach (object selected in selectedCommandControls)
        {
            dynamic control = selected;
            int start = GetRangeStart(control.Range);
            int end = GetRangeEnd(control.Range);
            targets.Add((start, end, () => DeleteCommandControl(selected)));
        }

        foreach (object selected in selectedReferenceFields)
        {
            dynamic field = selected;
            int start = GetRangeStart(field.Result);
            int end = GetRangeEnd(field.Result);
            targets.Add((start, end, () => DeleteReferenceField(selected)));
        }

        if (selectedPendingReference != null)
        {
            dynamic range = selectedPendingReference;
            int start = GetRangeStart(range);
            int end = GetRangeEnd(range);
            targets.Add((start, end, () => DeletePendingReferencePlaceholder(selectedPendingReference)));
        }

        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach ((int _, int _, Action delete) in targets.OrderByDescending(target => target.Start))
            {
                delete();
            }
        });

        return Task.FromResult<IReadOnlyList<string>>(deletedEquationIds);
    }
}
