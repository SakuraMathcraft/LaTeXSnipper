using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public Task InsertManagedEquationAsync(
        string ooxml,
        FormulaMetadata metadata,
        bool display,
        CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic selection = _wordApplication.Selection;
            ValidateInsertionTarget(selection.Range);
            dynamic range = ResolveManagedEquationInsertionRange(selection, display);
            int insertionPoint = GetRangeStart(range);
            double fontSizePoints = ReadPointSize(range.Font.Size);
            range.InsertXML(ooxml);
            (object equationControl, object? numberControl) =
                FindInsertedFormulaControls(insertionPoint, metadata.Identity.EquationId);

            double naturalFontSize = metadata.FontScale == 1
                ? fontSizePoints
                : WordOleBaseFontPoints * metadata.FontScale;
            ApplyManagedEquationFontSize(equationControl, naturalFontSize);
            ShowContentControlChrome((dynamic)equationControl);
            WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                _wordApplication.ActiveDocument,
                metadata.Identity.EquationId,
                naturalFontSize);
            ApplyManagedEquationStyle(equationControl, metadata);
            if (numberControl != null)
            {
                ApplyNumberControlVerticalAlignment(numberControl, metadata);
            }

            SaveFormulaMetadata(metadata);
            MoveSelectionAfterInsertedFormula(equationControl, metadata, display);
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
            ValidateInsertionTarget(selection.Range);
            dynamic range = ResolveInsertionTargetRange(selection, display);
            dynamic inlineShape = metadata.NumberingMode == NumberingMode.None
                ? InsertPlainOleInlineShape(range, metadata, presentation, display)
                : InsertNumberedOleInlineShape(range, metadata, presentation);
            SaveFormulaMetadata(metadata);
            MoveSelectionAfterInlineShape(inlineShape, metadata.Identity.EquationId, display);
        });

        return Task.CompletedTask;
    }

    public Task UpdateOleFormulaObjectAsync(string equationId, FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken)
    {
        return ReplaceOleFormulaObjectAsync(equationId, metadata, presentation, display, preserveUserScale: true, cancellationToken);
    }

    public Task ResetOleFormulaObjectAsync(string equationId, FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken)
    {
        return ReplaceOleFormulaObjectAsync(equationId, metadata, presentation, display, preserveUserScale: false, cancellationToken);
    }

    private Task ReplaceOleFormulaObjectAsync(
        string equationId,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        bool display,
        bool preserveUserScale,
        CancellationToken cancellationToken)
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
            object? existingOle = TryFindOleInlineShapeById(equationId);
            if (existingOle == null)
            {
                dynamic control = FindFormulaControlById(equationId);
                dynamic insertionRange = RemoveOmmlConversionSource(control, metadata);
                dynamic converted = metadata.NumberingMode == NumberingMode.None
                    ? InsertPlainOleInlineShape(insertionRange, metadata, presentation, display)
                    : InsertNumberedOleInlineShape(insertionRange, metadata, presentation);
                SaveFormulaMetadata(metadata);
                MoveSelectionAfterInlineShape(converted, metadata.Identity.EquationId, display);
                return;
            }

            dynamic inlineShape = existingOle;
            (float originalWidth, float originalHeight) = GetInlineShapeSize((object)inlineShape);
            (double naturalWidth, double naturalHeight) = GetOleNaturalSize((object)inlineShape);
            object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
            if (metadata.NumberingMode == NumberingMode.None && numberControl != null)
            {
                dynamic paragraphRange = GetContainingParagraphRange(inlineShape);
                dynamic range = ClearParagraphContent(paragraphRange);
                dynamic inserted = InsertPlainOleInlineShape(range, metadata, presentation, display);
                if (preserveUserScale)
                {
                    _ = ApplyUserScaleToReplacement(
                        inserted,
                        naturalWidth,
                        naturalHeight,
                        originalWidth,
                        originalHeight,
                        presentation,
                        display);
                }
                SaveFormulaMetadata(metadata);
                MoveSelectionAfterInlineShape(inserted, metadata.Identity.EquationId, display);
                return;
            }

            if (metadata.NumberingMode != NumberingMode.None && numberControl == null)
            {
                dynamic paragraphRange = GetContainingParagraphRange(inlineShape);
                dynamic range = ClearParagraphContent(paragraphRange);
                dynamic inserted = InsertNumberedOleInlineShape(range, metadata, presentation);
                float shapeScale = preserveUserScale
                    ? ApplyUserScaleToReplacement(
                        inserted,
                        naturalWidth,
                        naturalHeight,
                        originalWidth,
                        originalHeight,
                        presentation,
                        display)
                    : 1f;
                ApplyNumberedOleInlineShapeBaseline(inserted, presentation, shapeScale);
                SaveFormulaMetadata(metadata);
                MoveSelectionAfterInlineShape(inserted, metadata.Identity.EquationId, display);
                return;
            }

            dynamic replacement = ReplaceOleInlineShape(inlineShape, metadata, presentation);
            float replacementScale = preserveUserScale
                ? ApplyUserScaleToReplacement(
                    replacement,
                    naturalWidth,
                    naturalHeight,
                    originalWidth,
                    originalHeight,
                    presentation,
                    display)
                : 1f;
            if (metadata.NumberingMode != NumberingMode.None)
            {
                ApplyNumberedOleInlineShapeBaseline(replacement, presentation, replacementScale);
                ReplaceNumberControlTextById(metadata.Identity.EquationId, metadata.NumberText);
                ApplyNumberControlVerticalAlignmentById(metadata, presentation.HeightPoints * replacementScale);
                NormalizeNumberedParagraph(metadata.Identity.EquationId);
            }

            SaveFormulaMetadata(metadata);
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
            ApplyNumberControlVerticalAlignment(
                InsertNumberControlAtRange(CreateDocumentRange(paragraphStart, paragraphStart), metadata),
                metadata,
                presentation.HeightPoints);
        }
        else
        {
            InsertTextAtRange(cursor, "\t");
            ApplyNumberControlVerticalAlignment(InsertNumberControlAtRange(cursor, metadata), metadata, presentation.HeightPoints);
        }

        ApplyNumberedParagraphLayout(inlineShape.Range, inlineShape.Range);
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
        HideContentControlChrome(control);
        return control;
    }

    private void ApplyNumberControlVerticalAlignmentById(FormulaMetadata metadata, double renderedHeightPoints = 0)
    {
        object? numberControl = TryGetNumberControlById(_wordApplication.ActiveDocument, metadata.Identity.EquationId);
        if (numberControl != null)
        {
            ApplyNumberControlVerticalAlignment(numberControl, metadata, renderedHeightPoints);
        }
    }

    private static void ApplyNumberControlVerticalAlignment(object numberControl, FormulaMetadata metadata, double renderedHeightPoints = 0)
    {
        double offset = CalculateNumberVerticalOffset(metadata, renderedHeightPoints);
        dynamic control = numberControl;
        HideContentControlChrome(control);
        TryCom(() => control.Range.Font.Superscript = 0);
        TryCom(() => control.Range.Font.Subscript = 0);
        TryCom(() => control.Range.Font.Position = offset);
    }

    private double ReadManagedEquationFontSize(object contentControl)
    {
        dynamic control = contentControl;
        double fontSize = ReadPointSize(control.Range.Font.Size);
        return fontSize > 0 ? fontSize : GetCurrentFontSizePoints();
    }

    private void ApplyManagedEquationFontSizeById(string equationId, double fontSizePoints)
    {
        if (fontSizePoints <= 0)
        {
            return;
        }

        try
        {
            ApplyManagedEquationFontSize(FindFormulaControlById(equationId), fontSizePoints);
        }
        catch
        {
        }
    }

    private static void ApplyManagedEquationFontSize(object contentControl, double fontSizePoints)
    {
        if (fontSizePoints <= 0)
        {
            return;
        }

        dynamic control = contentControl;
        ShowContentControlChrome(control);
        TryCom(() => control.Range.Font.Size = fontSizePoints);
    }

    private (object EquationControl, object? NumberControl) FindInsertedFormulaControls(
        int insertionPoint,
        string equationId)
    {
        dynamic paragraph = CreateDocumentRange(insertionPoint, insertionPoint).Paragraphs.Item(1).Range;
        dynamic controls = paragraph.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        object? equationControl = null;
        object? numberControl = null;
        for (int index = 1; index <= count; index++)
        {
            dynamic control = controls.Item(index);
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            if (string.Equals(
                WordFormulaMetadataStore.EquationIdFromTag(tag),
                equationId,
                StringComparison.Ordinal))
            {
                equationControl = control;
            }
            else if (string.Equals(
                WordFormulaMetadataStore.EquationIdFromNumberTag(tag),
                equationId,
                StringComparison.Ordinal))
            {
                numberControl = control;
            }
        }

        if (equationControl == null)
        {
            throw new InvalidOperationException("Word did not preserve the inserted formula control.");
        }

        return (equationControl, numberControl);
    }

    private static double CalculateNumberVerticalOffset(FormulaMetadata metadata, double renderedHeightPoints)
    {
        double heightOffset = renderedHeightPoints > 0
            ? Math.Max(0, (renderedHeightPoints - WordOleBaseFontPoints) / 2)
            : 0;
        double rowOffset = Math.Max(0, EstimateFormulaRows(metadata.Latex) - 1) * WordOleBaseFontPoints * 0.65;
        return Math.Max(heightOffset, rowOffset);
    }

    private static int EstimateFormulaRows(string latex)
    {
        if (string.IsNullOrWhiteSpace(latex))
        {
            return 1;
        }

        return Math.Max(ContainsMultilineEnvironment(latex) ? 2 : 1, CountLatexLineBreaks(latex) + 1);
    }

    private static bool ContainsMultilineEnvironment(string latex)
    {
        return ContainsOrdinal(latex, @"\begin{aligned}")
            || ContainsOrdinal(latex, @"\begin{gathered}")
            || ContainsOrdinal(latex, @"\begin{cases}")
            || ContainsOrdinal(latex, @"\begin{matrix}")
            || ContainsOrdinal(latex, @"\begin{pmatrix}")
            || ContainsOrdinal(latex, @"\begin{bmatrix}")
            || ContainsOrdinal(latex, @"\begin{vmatrix}")
            || ContainsOrdinal(latex, @"\begin{Vmatrix}");
    }

    private static bool ContainsOrdinal(string value, string fragment)
    {
        return value.IndexOf(fragment, StringComparison.Ordinal) >= 0;
    }

    private static int CountLatexLineBreaks(string latex)
    {
        int count = 0;
        for (int index = 0; index < latex.Length - 1; index++)
        {
            if (latex[index] == '\\' && latex[index + 1] == '\\')
            {
                count++;
                index++;
            }
        }

        return count;
    }

    private void ApplyNumberedParagraphLayout(dynamic range, dynamic? formulaRange = null)
    {
        dynamic paragraphRange = range.Paragraphs.Item(1).Range;
        double contentWidth = GetPageContentWidthPoints();
        TryCom(() => paragraphRange.ParagraphFormat.Alignment = 0);
        TryCom(() => paragraphRange.ParagraphFormat.LeftIndent = 0);
        TryCom(() => paragraphRange.ParagraphFormat.RightIndent = 0);
        TryCom(() => paragraphRange.ParagraphFormat.FirstLineIndent = 0);
        TryCom(() => paragraphRange.ParagraphFormat.SpaceBefore = 0);
        TryCom(() => paragraphRange.ParagraphFormat.SpaceAfter = 0);
        TryCom(() => paragraphRange.ParagraphFormat.LineSpacingRule = 0);
        TryCom(() => paragraphRange.ParagraphFormat.DisableLineHeightGrid = true);
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.ClearAll());
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.Add(
            contentWidth / 2,
            WdAlignTabCenter,
            WdTabLeaderSpaces));
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

    private (double Width, double Height) GetOleNaturalSize(object inlineShape)
    {
        dynamic shape = inlineShape;
        string tag = Convert.ToString(shape.AlternativeText) ?? string.Empty;
        if (!WordFormulaMetadataStore.TryLoadOleNaturalSize(
                _wordApplication.ActiveDocument,
                tag,
                out double naturalWidth,
                out double naturalHeight))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return (naturalWidth, naturalHeight);
    }

    private float ApplyUserScaleToReplacement(
        dynamic inlineShape,
        double naturalWidth,
        double naturalHeight,
        float originalWidth,
        float originalHeight,
        OlePresentationResult presentation,
        bool display)
    {
        float widthScale = originalWidth / (float)naturalWidth;
        float heightScale = originalHeight / (float)naturalHeight;
        float shapeScale = Math.Max(0.05f, Math.Min(widthScale, heightScale));
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

    private static void TagOleInlineShape(
        dynamic inlineShape,
        FormulaMetadata metadata)
    {
        (float width, float height) = GetInlineShapeSize((object)inlineShape);
        string tag = WordFormulaMetadataStore.Save(
            inlineShape.Range.Document,
            metadata,
            width,
            height);
        inlineShape.AlternativeText = tag;
        string storedTag = Convert.ToString(inlineShape.AlternativeText) ?? string.Empty;
        if (!string.Equals(storedTag, tag, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Word did not preserve the OLE formula identifier.");
        }

        TryCom(() => inlineShape.Title = "LaTeXSnipper Equation");
    }
}
