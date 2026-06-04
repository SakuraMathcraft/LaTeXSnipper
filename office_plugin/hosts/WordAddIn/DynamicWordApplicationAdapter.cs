using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class DynamicWordApplicationAdapter : IWordApplicationAdapter
{
    private const double WordOleBaseFontPoints = 10.5;
    private const int WdCollapseEnd = 0;
    private const int WdCharacter = 1;
    private const int WdMove = 0;
    private const int WdAlignParagraphCenter = 1;
    private const int WdAlignTabCenter = 1;
    private const int WdAlignTabRight = 2;
    private const int WdTabLeaderSpaces = 0;
    private const int WdContentControlRichText = 0;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _wordApplication;

    private sealed class NumberedFormulaEntry
    {
        public NumberedFormulaEntry(string equationId, object numberControl, FormulaMetadata metadata, int start)
        {
            EquationId = equationId;
            NumberControl = numberControl;
            Metadata = metadata;
            Start = start;
        }

        public string EquationId { get; }

        public object NumberControl { get; }

        public FormulaMetadata Metadata { get; }

        public int Start { get; }
    }

    public DynamicWordApplicationAdapter(object wordApplication)
    {
        _wordApplication = wordApplication ?? throw new ArgumentNullException(nameof(wordApplication));
    }

    public double GetCurrentFontSizePoints()
    {
        double fontSize = ReadPointSize(_wordApplication.Selection.Font.Size);
        return fontSize > 0 ? fontSize : WordOleBaseFontPoints;
    }

    public Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        ValidateInsertionTarget(range);
        return Task.CompletedTask;
    }

    public Task InsertManagedEquationAsync(string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic selection = _wordApplication.Selection;
            dynamic range = ResolveInsertionTargetRange(selection);
            ValidateInsertionTarget(range);
            range.InsertXML(ooxml);
            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
            MoveSelectionAfterInsertedFormula(metadata, display);
        });

        return Task.CompletedTask;
    }

    public Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic selection = _wordApplication.Selection;
            dynamic range = ResolveInsertionTargetRange(selection);
            ValidateInsertionTarget(range);
            dynamic inlineShape = metadata.NumberingMode == NumberingMode.None
                ? InsertPlainOleInlineShape(range, metadata, presentation, display)
                : InsertNumberedOleInlineShape(range, metadata, presentation);
            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
            SaveOleNaturalSize(metadata.Identity.EquationId, presentation);
            MoveSelectionAfterInlineShape(inlineShape, metadata.Identity.EquationId, display);
        });

        return Task.CompletedTask;
    }

    public Task UpdateOleFormulaObjectAsync(string equationId, FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic inlineShape = FindOleInlineShapeById(equationId);
            (float originalWidth, float originalHeight) = GetInlineShapeSize((object)inlineShape);
            object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
            if (metadata.NumberingMode == NumberingMode.None && numberControl != null)
            {
                dynamic paragraphRange = GetContainingParagraphRange(inlineShape);
                int insertionPoint = GetRangeStart(paragraphRange);
                paragraphRange.Delete();
                dynamic range = CreateDocumentRange(insertionPoint, insertionPoint);
                dynamic inserted = InsertPlainOleInlineShape(range, metadata, presentation, display);
                _ = ApplyUserScaleToReplacement(inserted, metadata.Identity.EquationId, originalWidth, originalHeight, presentation, display);
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
                SaveOleNaturalSize(metadata.Identity.EquationId, presentation);
                MoveSelectionAfterInlineShape(inserted, metadata.Identity.EquationId, display);
                return;
            }

            if (metadata.NumberingMode != NumberingMode.None && numberControl == null)
            {
                dynamic paragraphRange = GetContainingParagraphRange(inlineShape);
                dynamic range = ClearParagraphContent(paragraphRange);
                dynamic inserted = InsertNumberedOleInlineShape(range, metadata, presentation);
                float shapeScale = ApplyUserScaleToReplacement(inserted, metadata.Identity.EquationId, originalWidth, originalHeight, presentation, display);
                ApplyNumberedOleInlineShapeBaseline(inserted, presentation, shapeScale);
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
                SaveOleNaturalSize(metadata.Identity.EquationId, presentation);
                MoveSelectionAfterInlineShape(inserted, metadata.Identity.EquationId, display);
                return;
            }

            dynamic replacement = ReplaceOleInlineShape(inlineShape, metadata, presentation);
            float replacementScale = ApplyUserScaleToReplacement(replacement, metadata.Identity.EquationId, originalWidth, originalHeight, presentation, display);
            if (metadata.NumberingMode != NumberingMode.None)
            {
                ApplyNumberedOleInlineShapeBaseline(replacement, presentation, replacementScale);
                ReplaceNumberControlTextById(metadata.Identity.EquationId, metadata.NumberText);
                NormalizeNumberedParagraph(metadata.Identity.EquationId);
            }

            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
            SaveOleNaturalSize(metadata.Identity.EquationId, presentation);
            MoveSelectionAfterInlineShape(replacement, metadata.Identity.EquationId, display);
        });

        return Task.CompletedTask;
    }

    private dynamic InsertPlainOleInlineShape(dynamic range, FormulaMetadata metadata, OlePresentationResult presentation, bool display)
    {
        if (display)
        {
            TryCom(() => range.ParagraphFormat.Alignment = WdAlignParagraphCenter);
        }

        return AddOleInlineShapeAtRange(range, metadata, presentation);
    }

    private dynamic InsertNumberedOleInlineShape(dynamic range, FormulaMetadata metadata, OlePresentationResult presentation)
    {
        dynamic cursor = range.Duplicate;
        cursor.Collapse(WdCollapseEnd);
        ApplyNumberedParagraphLayout(cursor);
        WordNumberPlacement placement = WordPluginSettings.Load().NumberPlacement;
        dynamic paragraphRange = cursor.Paragraphs.Item(1).Range;
        int paragraphStart = GetRangeStart(paragraphRange);
        if (placement == WordNumberPlacement.Left)
        {
            InsertTextAtRange(cursor, "\t");
        }
        else
        {
            InsertTextAtRange(cursor, "\t");
        }

        dynamic inlineShape = AddOleInlineShapeAtRange(cursor, metadata, presentation);
        ApplyNumberedOleInlineShapeBaseline(inlineShape, presentation);
        cursor = CreateDocumentRange(GetRangeEnd(inlineShape.Range), GetRangeEnd(inlineShape.Range));
        if (placement == WordNumberPlacement.Left)
        {
            _ = InsertNumberControlAtRange(CreateDocumentRange(paragraphStart, paragraphStart), metadata);
        }
        else
        {
            InsertTextAtRange(cursor, "\t");
            _ = InsertNumberControlAtRange(cursor, metadata);
        }

        NormalizeNumberedParagraph(metadata.Identity.EquationId);
        return inlineShape;
    }

    private dynamic AddOleInlineShapeAtRange(dynamic range, FormulaMetadata metadata, OlePresentationResult presentation)
    {
        OleFormulaPendingPayloadStore.SavePendingPayload(metadata, presentation);
        dynamic inlineShape = _wordApplication.ActiveDocument.InlineShapes.AddOLEObject(
            OleFormulaProgId,
            Type.Missing,
            false,
            false,
            Type.Missing,
            Type.Missing,
            Type.Missing,
            range);
        ApplyOleInlineShapeLayout(inlineShape, presentation, metadata.DisplayMode == FormulaDisplayMode.Display);
        TagOleInlineShape(inlineShape, metadata);
        return inlineShape;
    }

    private dynamic ReplaceOleInlineShape(dynamic inlineShape, FormulaMetadata metadata, OlePresentationResult presentation)
    {
        int insertionPoint = GetRangeStart(inlineShape.Range);
        inlineShape.Delete();
        return AddOleInlineShapeAtRange(CreateDocumentRange(insertionPoint, insertionPoint), metadata, presentation);
    }

    private static void InsertTextAtRange(dynamic range, string text)
    {
        range.Text = text;
        range.Collapse(WdCollapseEnd);
    }

    private dynamic ClearParagraphContent(dynamic paragraphRange)
    {
        int start = GetRangeStart(paragraphRange);
        int end = Math.Max(start, GetRangeEnd(paragraphRange) - 1);
        dynamic content = CreateDocumentRange(start, end);
        content.Delete();
        return CreateDocumentRange(start, start);
    }

    private dynamic InsertNumberControlAtRange(dynamic range, FormulaMetadata metadata)
    {
        dynamic control = range.ContentControls.Add(WdContentControlRichText);
        TryCom(() => control.Tag = WordFormulaMetadataStore.BuildNumberTag(metadata.Identity.EquationId));
        TryCom(() => control.Title = WordFormulaMetadataStore.BuildNumberAlias(metadata.Identity.EquationId));
        TryCom(() => control.Range.Text = metadata.NumberText);
        int insertionPoint = GetRangeEnd(control.Range);
        return CreateDocumentRange(insertionPoint, insertionPoint);
    }

    private void ApplyNumberedParagraphLayout(dynamic range)
    {
        dynamic paragraphRange = range.Paragraphs.Item(1).Range;
        double contentWidth = GetPageContentWidthPoints();
        TryCom(() => paragraphRange.ParagraphFormat.Alignment = 0);
        TryCom(() => paragraphRange.ParagraphFormat.SpaceBefore = 0);
        TryCom(() => paragraphRange.ParagraphFormat.SpaceAfter = 0);
        TryCom(() => paragraphRange.ParagraphFormat.LineSpacingRule = 0);
        TryCom(() => paragraphRange.ParagraphFormat.DisableLineHeightGrid = true);
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.ClearAll());
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.Add(contentWidth / 2, WdAlignTabCenter, WdTabLeaderSpaces));
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.Add(contentWidth, WdAlignTabRight, WdTabLeaderSpaces));
    }

    private double GetPageContentWidthPoints()
    {
        try
        {
            dynamic setup = _wordApplication.ActiveDocument.PageSetup;
            double width = Convert.ToDouble(setup.PageWidth) - Convert.ToDouble(setup.LeftMargin) - Convert.ToDouble(setup.RightMargin);
            return width > 0 ? width : 468;
        }
        catch
        {
            return 468;
        }
    }

    private static void ApplyOleInlineShapeLayout(dynamic inlineShape, OlePresentationResult presentation, bool display)
    {
        SetOleInlineShapeSize(inlineShape, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
        if (!display)
        {
            ApplyOleInlineShapeBaseline(inlineShape, presentation);
        }
    }

    private static (float Width, float Height) GetInlineShapeSize(object inlineShape)
    {
        dynamic shape = inlineShape;
        float width = (float)shape.Width;
        float height = (float)shape.Height;
        if (width <= 0 || height <= 0)
        {
            throw new InvalidOperationException("OLE formula object size is invalid.");
        }

        return (width, height);
    }

    private float ApplyUserScaleToReplacement(dynamic inlineShape, string equationId, float originalWidth, float originalHeight, OlePresentationResult presentation, bool display)
    {
        float shapeScale = 1f;
        if (WordFormulaMetadataStore.TryLoadOleNaturalSize(_wordApplication.ActiveDocument, equationId, out double naturalWidth, out double naturalHeight))
        {
            float widthScale = naturalWidth > 0 ? originalWidth / (float)naturalWidth : 1f;
            float heightScale = naturalHeight > 0 ? originalHeight / (float)naturalHeight : 1f;
            shapeScale = Math.Max(0.05f, Math.Min(widthScale, heightScale));
        }

        SetOleInlineShapeSize(
            inlineShape,
            (float)presentation.WidthPoints * shapeScale,
            (float)presentation.HeightPoints * shapeScale);
        if (!display)
        {
            ApplyOleInlineShapeBaseline(inlineShape, presentation, shapeScale);
        }

        return shapeScale;
    }

    private static void SetOleInlineShapeSize(dynamic inlineShape, float width, float height)
    {
        if (width <= 0 || height <= 0)
        {
            throw new InvalidOperationException("OLE formula object size is invalid.");
        }

        TryCom(() => inlineShape.LockAspectRatio = true);
        inlineShape.Width = width;
        inlineShape.Height = height;
        TryCom(() => inlineShape.LockAspectRatio = true);
    }

    private static void ApplyOleInlineShapeBaseline(dynamic inlineShape, OlePresentationResult presentation, float scale = 1f)
    {
        double baseline = presentation.BaselinePoints * scale;
        if (baseline <= 0)
        {
            return;
        }

        TryCom(() => inlineShape.Range.Font.Position = -baseline);
    }

    private static void ApplyNumberedOleInlineShapeBaseline(dynamic inlineShape, OlePresentationResult presentation, float scale = 1f)
    {
        double offset = Math.Max(0.5, Math.Min(18.0, presentation.HeightPoints * 0.22 * scale));
        TryCom(() => inlineShape.Range.Font.Position = -offset);
    }

    private static double ReadPointSize(object value)
    {
        try
        {
            double points = Convert.ToDouble(value, System.Globalization.CultureInfo.InvariantCulture);
            return points > 0 && points < 200 ? points : 0;
        }
        catch (FormatException)
        {
            return 0;
        }
        catch (InvalidCastException)
        {
            return 0;
        }
    }

    private void SaveOleNaturalSize(string equationId, OlePresentationResult presentation)
    {
        WordFormulaMetadataStore.SaveOleNaturalSize(_wordApplication.ActiveDocument, equationId, presentation.WidthPoints, presentation.HeightPoints);
    }

    private static void TagOleInlineShape(dynamic inlineShape, FormulaMetadata metadata)
    {
        string tag = WordFormulaMetadataStore.BuildEquationTag(metadata.Identity.EquationId, metadata);
        TryCom(() => inlineShape.AlternativeText = tag);
        TryCom(() => inlineShape.Title = "LaTeXSnipper Equation");
    }

    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        SelectedWordFormula selected = FindSelectedFormula();
        return Task.FromResult(selected.Metadata);
    }

    public Task UpdateFormulaAsync(string equationId, string ooxml, string equationOoxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        ValidateManagedEquationInput(equationOoxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        object control = FindFormulaControlById(equationId);
        ExecuteWithScreenUpdatingSuspended(() => ReplaceFormulaContent(control, ooxml, equationOoxml, metadata));
        return Task.CompletedTask;
    }

    public Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var selectedFormulas = new List<SelectedWordFormula>(FindSelectedFormulas());
        selectedFormulas.Sort((left, right) => GetFormulaStart(right).CompareTo(GetFormulaStart(left)));
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach (SelectedWordFormula selected in selectedFormulas)
            {
                DeleteFormula(selected);
            }
        });

        return Task.CompletedTask;
    }

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
        var entries = new List<NumberedFormulaEntry>(LoadNumberedFormulaEntries());
        entries.Sort((left, right) => left.Start.CompareTo(right.Start));
        int number = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach (NumberedFormulaEntry entry in entries)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.Metadata.NumberingMode != NumberingMode.Automatic)
                {
                    continue;
                }

                number++;
                string numberText = WordAutomaticNumberFormatter.Format(number);
                ReplaceNumberControlText(entry.NumberControl, numberText);
                FormulaMetadata renumbered = new FormulaMetadata(
                    entry.Metadata.Identity,
                    entry.Metadata.Latex,
                    FormulaDisplayMode.Display,
                    NumberingMode.Automatic,
                    numberText,
                    entry.Metadata.RenderEngine,
                    entry.Metadata.SchemaVersion);
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, renumbered);
            }
        });

        SetNextAutomaticNumber(number + 1);
        return Task.FromResult(number);
    }

    private IReadOnlyList<NumberedFormulaEntry> LoadNumberedFormulaEntries()
    {
        var entries = new List<NumberedFormulaEntry>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int i = 1; i <= count; i++)
        {
            dynamic control = controls.Item(i);
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            string equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
            if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
            {
                continue;
            }

            FormulaMetadata metadata = LoadFormulaMetadataById(equationId);
            entries.Add(new NumberedFormulaEntry(equationId, control, metadata, GetRangeStart(control.Range)));
        }

        return entries;
    }

    private FormulaMetadata LoadFormulaMetadataById(string equationId)
    {
        try
        {
            return WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
        }
        catch
        {
            object equationControl = FindFormulaControlById(equationId);
            return LoadFormulaMetadata((dynamic)equationControl, equationId);
        }
    }

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

        FormulaMetadata metadata = LoadFormulaMetadata(inlineShape, equationId);
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
            FormulaMetadata metadata = LoadFormulaMetadata(control, equationId);
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

    private void ReplaceFormulaContent(object contentControl, string ooxml, string equationOoxml, FormulaMetadata metadata)
    {
        dynamic control = contentControl;
        object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, metadata.Identity.EquationId);
        if (metadata.NumberingMode != NumberingMode.None && numberControl != null)
        {
            ReplaceNumberedFormulaControl(control, equationOoxml);
            ReplaceNumberControlText(numberControl, metadata.NumberText);
            NormalizeNumberedParagraph(metadata.Identity.EquationId);
        }
        else if (metadata.NumberingMode != NumberingMode.None)
        {
            ReplaceParagraphWithNumberedFormula(control, ooxml);
            NormalizeNumberedParagraph(metadata.Identity.EquationId);
        }
        else
        {
            dynamic range = ResolveReplacementRange(control, metadata);
            range.InsertXML(ooxml);
        }

        WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
    }

    private void ReplaceFormulaContent(object contentControl, string ooxml, FormulaMetadata metadata)
    {
        ReplaceFormulaContent(contentControl, ooxml, ooxml, metadata);
    }

    private void ReplaceParagraphWithNumberedFormula(object contentControl, string ooxml)
    {
        dynamic control = contentControl;
        dynamic paragraphRange = GetContainingParagraphRange(control);
        int insertionPoint = GetRangeStart(paragraphRange);
        paragraphRange.Delete();
        dynamic insertionRange = CreateDocumentRange(insertionPoint, insertionPoint);
        insertionRange.InsertXML(ooxml);
    }

    private static void ReplaceNumberedFormulaControl(object contentControl, string equationOoxml)
    {
        dynamic control = contentControl;
        dynamic range = GetContainingParagraphRange(control);
        range.InsertXML(equationOoxml);
    }

    private static dynamic ResolveReplacementRange(dynamic control, FormulaMetadata metadata)
    {
        return metadata.DisplayMode == FormulaDisplayMode.Display
            ? GetContainingParagraphRange(control)
            : control.Range;
    }

    private void ValidateInsertionTarget(dynamic range)
    {
        if (RangeTouchesManagedFormula(range) || RangeIntersectsManagedFormula(range))
        {
            throw new InvalidOperationException(WordAddInText.Get("InsertInsideFormulaError"));
        }
    }

    private dynamic ResolveInsertionTargetRange(dynamic selection)
    {
        return selection.Range;
    }

    private void MoveSelectionAfterInsertedFormula(FormulaMetadata metadata, bool display)
    {
        try
        {
            string equationId = metadata.Identity.EquationId;
            dynamic control = FindFormulaControlById(equationId);
            if (metadata.NumberingMode != NumberingMode.None)
            {
                NormalizeNumberedParagraph(equationId);
                MoveSelectionAfterDisplayParagraph(control, equationId);
                return;
            }

            if (!display)
            {
                MoveSelectionAfterInlineControl(control, equationId);
                return;
            }

            MoveSelectionAfterDisplayParagraph(control, equationId);
        }
        catch
        {
        }
    }

    private void MoveSelectionAfterInlineControl(dynamic control, string equationId)
    {
        object? metadataControl = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        MoveSelectionAfterContentControl(metadataControl ?? control, equationId);
    }

    private void MoveSelectionAfterDisplayParagraph(dynamic control, string equationId)
    {
        dynamic paragraphRange = GetContainingParagraphRange(control);
        int insertionPoint = GetRangeEnd(paragraphRange);
        bool paragraphInserted = TryInsertParagraphAfter(paragraphRange);
        if (paragraphInserted &&
            (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1)))
        {
            return;
        }

        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterContentControl(object contentControl, string equationId)
    {
        dynamic control = contentControl;
        int insertionPoint = Convert.ToInt32(control.Range.End);
        if (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            return;
        }

        dynamic target = CreateDocumentRange(insertionPoint, insertionPoint);
        target.Select();
        MoveSelectionRight();
        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterInlineShape(object inlineShape, string equationId, bool display)
    {
        dynamic shape = inlineShape;
        int insertionPoint = GetRangeEnd(shape.Range);
        if (display)
        {
            dynamic paragraphRange = shape.Range.Paragraphs.Item(1).Range;
            insertionPoint = GetRangeEnd(paragraphRange);
            bool paragraphInserted = TryInsertParagraphAfter(paragraphRange);
            if (paragraphInserted &&
                (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1)))
            {
                return;
            }
        }

        if (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            return;
        }

        dynamic target = CreateDocumentRange(insertionPoint, insertionPoint);
        target.Select();
        MoveSelectionRight();
        EnsureSelectionOutsideFormula(equationId);
    }

    private bool TryMoveSelectionOutsideFormula(int position)
    {
        try
        {
            int safePosition = ClampDocumentPosition(position);
            dynamic target = _wordApplication.ActiveDocument.Range(safePosition, safePosition);
            if (RangeTouchesManagedFormula(target))
            {
                return false;
            }

            try
            {
                _wordApplication.Selection.SetRange(safePosition, safePosition);
            }
            catch
            {
                target.Select();
            }

            return true;
        }
        catch
        {
            return false;
        }
    }

    private void EnsureSelectionOutsideFormula(string equationId)
    {
        try
        {
            for (int i = 0; i < 12; i++)
            {
                dynamic range = _wordApplication.Selection.Range;
                object? control = TryGetParentContentControl(range)
                    ?? TryGetFirstManagedContentControl(range);
                if (control == null)
                {
                    return;
                }

                if (GetEquationId((dynamic)control) != equationId)
                {
                    return;
                }

                MoveSelectionRight();
            }
        }
        catch
        {
        }
    }

    private static bool TryInsertParagraphAfter(dynamic range)
    {
        try
        {
            range.InsertParagraphAfter();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void MoveSelectionRight()
    {
        try
        {
            _wordApplication.Selection.MoveRight(WdCharacter, 1, WdMove);
        }
        catch
        {
        }
    }

    private static dynamic GetContainingParagraphRange(dynamic control)
    {
        dynamic paragraphs = control.Range.Paragraphs;
        return paragraphs.Item(1).Range;
    }

    private void NormalizeNumberedParagraph(string equationId)
    {
        try
        {
            object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
            if (numberControl == null)
            {
                return;
            }

            ApplyNumberedParagraphLayout(((dynamic)numberControl).Range);
        }
        catch
        {
        }
    }

    private void DeleteFormula(SelectedWordFormula selected)
    {
        if (selected.IsOleInlineShape)
        {
            DeleteOleInlineShape(selected);
            return;
        }

        dynamic control = selected.ContentControl;
        string equationId = selected.Metadata.Identity.EquationId;
        object? metadataControl = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        WordFormulaMetadataStore.Delete(_wordApplication.ActiveDocument, equationId);
        if (selected.Metadata.NumberingMode != NumberingMode.None)
        {
            DeleteNumberedParagraphBlock(control);
            DeleteMetadataControl(metadataControl);
            return;
        }

        control.Delete(true);
        DeleteMetadataControl(metadataControl);
    }

    private void DeleteOleInlineShape(SelectedWordFormula selected)
    {
        string equationId = selected.Metadata.Identity.EquationId;
        WordFormulaMetadataStore.Delete(_wordApplication.ActiveDocument, equationId);
        dynamic inlineShape = selected.ContentControl;
        object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        if (numberControl != null)
        {
            DeleteNumberedParagraphBlock(numberControl);
            return;
        }

        inlineShape.Delete();
    }

    private static void DeleteNumberedParagraphBlock(object anchor)
    {
        dynamic control = anchor;
        dynamic paragraphRange = GetContainingParagraphRange(control);
        paragraphRange.Delete();
    }

    private static void DeleteMetadataControl(object? metadataControl)
    {
        if (metadataControl == null)
        {
            return;
        }

        dynamic backup = metadataControl;
        backup.Delete(true);
    }

    private static int GetFormulaStart(SelectedWordFormula formula)
    {
        try
        {
            return Convert.ToInt32(((dynamic)formula.ContentControl).Range.Start);
        }
        catch
        {
            return 0;
        }
    }

    private FormulaMetadata LoadFormulaMetadata(dynamic control, string equationId)
    {
        try
        {
            return WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
        }
        catch
        {
            return CreateRecoveredFormulaMetadata(control, equationId);
        }
    }

    private FormulaMetadata CreateRecoveredFormulaMetadata(dynamic control, string equationId)
    {
        string numberText = ReadNumberText(equationId);
        NumberingMode numberingMode = string.IsNullOrWhiteSpace(numberText) ? NumberingMode.None : NumberingMode.Manual;
        FormulaDisplayMode displayMode = numberingMode != NumberingMode.None || IsCenteredParagraph(control)
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        return new FormulaMetadata(
            new FormulaIdentity("active-document", equationId),
            ReadFormulaText(control),
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: 1);
    }

    private string ReadNumberText(string equationId)
    {
        object? control = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        return control == null ? string.Empty : CleanRangeText(((dynamic)control).Range.Text);
    }

    private void ReplaceNumberControlTextById(string equationId, string numberText)
    {
        object? control = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        if (control != null)
        {
            ReplaceNumberControlText(control, numberText);
        }
    }

    private static void ReplaceNumberControlText(object numberControl, string numberText)
    {
        dynamic control = numberControl;
        TryCom(() => control.Range.Text = numberText);
    }

    private static string ReadFormulaText(dynamic control)
    {
        try
        {
            return CleanRangeText(Convert.ToString(control.Range.Text) ?? string.Empty);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool IsCenteredParagraph(dynamic control)
    {
        try
        {
            int alignment = Convert.ToInt32(control.Range.ParagraphFormat.Alignment);
            return alignment == WdAlignParagraphCenter;
        }
        catch
        {
            return false;
        }
    }

    private static string CleanRangeText(string value)
    {
        return value
            .Replace("\a", string.Empty)
            .Replace("\r", string.Empty)
            .Replace("\n", string.Empty)
            .Trim();
    }

    private static object? TryGetNumberControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildNumberTag(equationId));
    }

    private static object? TryGetMetadataControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildMetadataTag(equationId));
    }

    private static object? TryGetControlByTag(dynamic document, string expectedTag)
    {
        try
        {
            dynamic controls = document.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (string.Equals(tag, expectedTag, StringComparison.Ordinal))
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private dynamic CreateDocumentRange(int start, int end)
    {
        try
        {
            return _wordApplication.ActiveDocument.Range(start, end);
        }
        catch
        {
            return _wordApplication.ActiveDocument.Range(Math.Max(0, start - 1), Math.Max(0, end - 1));
        }
    }

    private dynamic CreateRangeAtDocumentPosition(int position)
    {
        int safePosition = ClampDocumentPosition(position);
        return _wordApplication.ActiveDocument.Range(safePosition, safePosition);
    }

    private int ClampDocumentPosition(int position)
    {
        try
        {
            int documentStart = Convert.ToInt32(_wordApplication.ActiveDocument.Content.Start);
            int documentEnd = Convert.ToInt32(_wordApplication.ActiveDocument.Content.End);
            return Math.Min(Math.Max(position, documentStart), documentEnd);
        }
        catch
        {
            return Math.Max(0, position);
        }
    }

    private static int GetRangeEnd(dynamic range)
    {
        return Convert.ToInt32(range.End);
    }

    private static int GetRangeStart(dynamic range)
    {
        return Convert.ToInt32(range.Start);
    }

    private static bool RangesOverlap(int leftStart, int leftEnd, int rightStart, int rightEnd)
    {
        return leftStart < rightEnd && leftEnd > rightStart;
    }

    private static bool IsCollapsedRange(dynamic range)
    {
        try
        {
            return Convert.ToInt32(range.Start) == Convert.ToInt32(range.End);
        }
        catch
        {
            return false;
        }
    }

    private static bool RangeTouchesManagedFormula(dynamic range)
    {
        return TryGetParentContentControl(range) != null
            || TryGetFirstManagedContentControl(range) != null;
    }

    private bool RangeIntersectsManagedFormula(dynamic range)
    {
        int rangeStart = GetRangeStart(range);
        int rangeEnd = GetRangeEnd(range);
        try
        {
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (!IsManagedControl(control))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(control.Range), GetRangeEnd(control.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        try
        {
            dynamic inlineShapes = _wordApplication.ActiveDocument.InlineShapes;
            int count = Convert.ToInt32(inlineShapes.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic inlineShape = inlineShapes.Item(i);
                if (string.IsNullOrWhiteSpace(GetOleInlineShapeEquationId(inlineShape)))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(inlineShape.Range), GetRangeEnd(inlineShape.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private static bool RangesIntersectOrContainPoint(int rangeStart, int rangeEnd, int targetStart, int targetEnd)
    {
        if (rangeStart == rangeEnd)
        {
            return rangeStart >= targetStart && rangeStart < targetEnd;
        }

        return RangesOverlap(rangeStart, rangeEnd, targetStart, targetEnd);
    }

    private void ExecuteWithScreenUpdatingSuspended(Action action)
    {
        bool restore = false;
        bool original = true;
        try
        {
            original = Convert.ToBoolean(_wordApplication.ScreenUpdating);
            restore = true;
            _wordApplication.ScreenUpdating = false;
        }
        catch
        {
        }

        try
        {
            action();
        }
        finally
        {
            if (restore)
            {
                TryCom(() => _wordApplication.ScreenUpdating = original);
            }
        }
    }

    private static void TryCom(Action action)
    {
        try
        {
            action();
        }
        catch
        {
        }
    }

    private static object? TryGetParentContentControl(dynamic range)
    {
        try
        {
            dynamic control = range.ParentContentControl;
            return IsManagedControl(control) ? control : null;
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetFirstManagedContentControl(dynamic range)
    {
        try
        {
            dynamic controls = range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (IsManagedControl(control))
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private static bool IsManagedControl(dynamic control)
    {
        try
        {
            return !string.IsNullOrWhiteSpace(GetManagedEquationId(control));
        }
        catch
        {
            return false;
        }
    }

    private static string GetEquationId(dynamic control)
    {
        return GetManagedEquationId(control);
    }

    private static string GetEquationControlId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        return WordFormulaMetadataStore.EquationIdFromTag(tag);
    }

    private static string GetManagedEquationId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        string equationId = WordFormulaMetadataStore.EquationIdFromTag(tag);
        if (!string.IsNullOrWhiteSpace(equationId))
        {
            return equationId;
        }

        equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
        return string.IsNullOrWhiteSpace(equationId)
            ? WordFormulaMetadataStore.EquationIdFromMetadataTag(tag)
            : equationId;
    }

    private static string GetOleInlineShapeEquationId(dynamic inlineShape)
    {
        try
        {
            string tag = Convert.ToString(inlineShape.AlternativeText) ?? string.Empty;
            return WordFormulaMetadataStore.EquationIdFromTag(tag);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool IsEquationControl(dynamic control)
    {
        try
        {
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            return !string.IsNullOrWhiteSpace(WordFormulaMetadataStore.EquationIdFromTag(tag));
        }
        catch
        {
            return false;
        }
    }

    private static void ValidateManagedEquationInput(string ooxml, FormulaMetadata metadata)
    {
        if (string.IsNullOrWhiteSpace(ooxml))
        {
            throw new ArgumentException("OOXML is required.", nameof(ooxml));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }
    }
}
