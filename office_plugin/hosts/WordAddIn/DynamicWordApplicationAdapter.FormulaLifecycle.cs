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
            object equationControl = FindInsertedFormulaControl(insertionPoint, metadata.Identity.EquationId);

            double naturalFontSize = ScaleFontSize(fontSizePoints, metadata.FontScale);
            ApplyManagedEquationFontSize(equationControl, naturalFontSize);
            ShowContentControlChrome((dynamic)equationControl);
            WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                _wordApplication.ActiveDocument,
                metadata.Identity.EquationId,
                naturalFontSize);
            ApplyManagedEquationStyle(equationControl, metadata);
            if (metadata.DisplayMode == FormulaDisplayMode.Inline)
            {
                ResetManagedEquationBaseline(equationControl);
            }
            else if (metadata.NumberingMode != NumberingMode.None)
            {
                dynamic formulaRange = ((dynamic)equationControl).Range;
                ApplyNumberedFormulaParagraphLayout(formulaRange);
                if (metadata.NumberingMode == NumberingMode.Automatic)
                {
                    ReplaceEquationNumberAtRange(
                        FindEquationNumberRange(formulaRange, metadata),
                        metadata,
                        BuildEquationNumberStateAtPosition(insertionPoint, WordPluginSettings.Load()),
                        formulaHeightPoints: 0);
                }
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

    public Task ReplaceNativeWordFormulaWithOleAsync(
        int sourceStart,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        bool display,
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
            dynamic nativeEquation = FindNativeWordFormulaByStart(sourceStart);
            string originalOoxml = Convert.ToString(nativeEquation.Range.WordOpenXML) ?? string.Empty;
            dynamic insertionRange = RemoveNativeWordFormulaSource(nativeEquation, display);
            try
            {
                dynamic inserted = InsertPlainOleInlineShape(insertionRange, metadata, presentation, display);
                SaveFormulaMetadata(metadata);
                MoveSelectionAfterInlineShape(inserted, metadata.Identity.EquationId, display);
            }
            catch
            {
                RestoreNativeWordFormula(insertionRange, originalOoxml);
                throw;
            }
        });
        return Task.CompletedTask;
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
            FormulaMetadata currentMetadata = LoadFormulaMetadata(
                inlineShape,
                equationId,
                RenderEngineKind.MathJaxSvg);
            if (metadata.NumberingMode != currentMetadata.NumberingMode ||
                metadata.NumberingMode != NumberingMode.None)
            {
                dynamic paragraphRange = GetContainingParagraphRange(inlineShape);
                dynamic range = ClearParagraphContent(paragraphRange);
                dynamic inserted = metadata.NumberingMode == NumberingMode.None
                    ? InsertPlainOleInlineShape(range, metadata, presentation, display)
                    : InsertNumberedOleInlineShape(range, metadata, presentation);
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
                if (metadata.NumberingMode == NumberingMode.None && !display)
                {
                    ApplyOleInlineShapeBaseline(inserted, presentation, shapeScale);
                }

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
            NormalizeFormulaParagraphAfterOleReplacement(replacement, metadata, presentation, replacementScale, display);

            SaveFormulaMetadata(metadata);
            MoveSelectionAfterInlineShape(replacement, metadata.Identity.EquationId, display);
        });

        return Task.CompletedTask;
    }

    private dynamic FindNativeWordFormulaByStart(int sourceStart)
    {
        dynamic equations = _wordApplication.ActiveDocument.OMaths;
        int count = Convert.ToInt32(equations.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic equation = equations.Item(index);
            if (GetRangeStart(equation.Range) == sourceStart)
            {
                return equation;
            }
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
    }

    private dynamic RemoveNativeWordFormulaSource(dynamic nativeEquation, bool display)
    {
        dynamic sourceRange = nativeEquation.Range;
        if (display)
        {
            dynamic paragraphRange = sourceRange.Paragraphs.Item(1).Range;
            return ClearParagraphContent(paragraphRange);
        }

        int insertionPoint = GetRangeStart(sourceRange);
        sourceRange.Text = InlineConversionSlot;
        return CreateDocumentRange(
            insertionPoint,
            insertionPoint + InlineConversionSlot.Length);
    }

    private static void RestoreNativeWordFormula(dynamic insertionRange, string originalOoxml)
    {
        if (string.IsNullOrWhiteSpace(originalOoxml))
        {
            return;
        }

        try
        {
            insertionRange.Text = string.Empty;
            insertionRange.InsertXML(originalOoxml);
        }
        catch
        {
        }
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
        WordNumberPlacement placement = WordPluginSettings.Load().NumberPlacement;
        EquationNumberState numberState = BuildEquationNumberStateAtPosition(GetRangeStart(cursor), WordPluginSettings.Load());
        ApplyNumberedFormulaParagraphLayout(cursor);
        dynamic? numberRange = null;
        if (placement == WordNumberPlacement.Left)
        {
            numberRange = InsertEquationNumberAtRange(
                cursor,
                metadata,
                numberState.Prefix,
                numberState.ResetSequence,
                numberState.Format,
                numberState.Enclosure);
            InsertTextAtRange(cursor, "\t");
        }
        else
        {
            InsertTextAtRange(cursor, "\t");
        }

        dynamic inlineShape = AddOleInlineShapeAtRange(cursor, metadata, presentation);
        cursor = CreateDocumentRange(GetRangeEnd(inlineShape.Range), GetRangeEnd(inlineShape.Range));
        if (placement == WordNumberPlacement.Right)
        {
            InsertTextAtRange(cursor, "\t");
            numberRange = InsertEquationNumberAtRange(
                cursor,
                metadata,
                numberState.Prefix,
                numberState.ResetSequence,
                numberState.Format,
                numberState.Enclosure);
        }

        if (numberRange != null)
        {
            ApplyEquationNumberBaseline(numberRange, presentation.HeightPoints);
        }

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

    private void NormalizeFormulaParagraphAfterOleReplacement(
        dynamic inlineShape,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        float replacementScale,
        bool display)
    {
        if (metadata.NumberingMode != NumberingMode.None)
        {
            ApplyNumberedFormulaParagraphLayout(inlineShape.Range);
            ApplyNumberedOleInlineShapeBaseline(inlineShape, presentation, replacementScale);
            ApplyEquationNumberBaseline(FindEquationNumberRange(inlineShape.Range, metadata), presentation.HeightPoints * replacementScale);
            return;
        }

        if (!display)
        {
            ApplyOleInlineShapeBaseline(inlineShape, presentation, replacementScale);
        }
    }

    private dynamic ClearParagraphContent(dynamic paragraphRange)
    {
        int start = GetRangeStart(paragraphRange);
        int end = Math.Max(start, GetRangeEnd(paragraphRange) - 1);
        dynamic content = CreateDocumentRange(start, end);
        content.Delete();
        return CreateDocumentRange(start, start);
    }

    private void ApplyNumberedFormulaParagraphLayout(dynamic range)
    {
        dynamic paragraphRange = range.Paragraphs.Item(1).Range;
        double contentWidth = GetPageContentWidthPoints();
        TryCom(() => paragraphRange.ParagraphFormat.Alignment = WdAlignParagraphLeft);
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
        TryCom(() => paragraphRange.ParagraphFormat.TabStops.Add(
            contentWidth,
            WdAlignTabRight,
            WdTabLeaderSpaces));
    }

    private void AddOrReplaceEquationBookmark(string equationId, dynamic range)
    {
        string bookmarkName = WordEquationNumbering.BuildBookmarkName(equationId);
        dynamic document = _wordApplication.ActiveDocument;
        if (Convert.ToBoolean(document.Bookmarks.Exists(bookmarkName)))
        {
            document.Bookmarks.Item(bookmarkName).Delete();
        }

        document.Bookmarks.Add(bookmarkName, range);
    }

    private dynamic FindEquationNumberRange(dynamic formulaRange, FormulaMetadata metadata)
    {
        return FindEquationNumberRangeById(metadata.Identity.EquationId);
    }

    private dynamic FindEquationNumberRangeById(string equationId)
    {
        string bookmarkName = WordEquationNumbering.BuildBookmarkName(equationId);
        dynamic bookmarks = _wordApplication.ActiveDocument.Bookmarks;
        if (Convert.ToBoolean(bookmarks.Exists(bookmarkName)))
        {
            return bookmarks.Item(bookmarkName).Range;
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
    }

    private dynamic InsertEquationNumberAtRange(dynamic range, FormulaMetadata metadata)
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        return InsertEquationNumberAtRange(
            range,
            metadata,
            string.Empty,
            false,
            settings.NumberFormat,
            settings.NumberEnclosure);
    }

    private dynamic InsertEquationNumberAtRange(
        dynamic range,
        FormulaMetadata metadata,
        string prefix,
        bool resetSequence,
        WordNumberFormat format,
        WordNumberEnclosure enclosure)
    {
        int start = GetRangeStart(range);
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            dynamic field = _wordApplication.ActiveDocument.Fields.Add(
                range,
                WdFieldEmpty,
                WordEquationNumbering.BuildSequenceFieldCode(resetSequence, format, prefix, enclosure),
                true);
            TryCom(() => field.Update());
            range = field.Result.Duplicate;
            range.Collapse(WdCollapseEnd);
        }
        else
        {
            InsertTextAtRange(range, WordEquationNumbering.GetLeftEnclosure(enclosure));
            InsertTextAtRange(range, metadata.NumberText);
            InsertTextAtRange(range, WordEquationNumbering.GetRightEnclosure(enclosure));
        }

        int end = GetRangeStart(range);
        dynamic numberRange = CreateDocumentRange(start, end);
        AddOrReplaceEquationBookmark(metadata.Identity.EquationId, numberRange);
        return numberRange;
    }

    private dynamic ReplaceEquationNumberAtRange(
        dynamic numberRange,
        FormulaMetadata metadata,
        EquationNumberState state,
        double formulaHeightPoints)
    {
        int start = GetRangeStart(numberRange);
        numberRange.Delete();
        dynamic inserted = InsertEquationNumberAtRange(
            CreateDocumentRange(start, start),
            metadata,
            state.Prefix,
            state.ResetSequence,
            state.Format,
            state.Enclosure);
        ApplyEquationNumberBaseline(inserted, formulaHeightPoints);
        return inserted;
    }

    private double ReadManagedEquationFontSize(object contentControl)
    {
        dynamic control = contentControl;
        double fontSize = ReadPointSize(control.Range.Font.Size);
        return fontSize > 0 ? fontSize : GetCurrentFontSizePoints();
    }

    private static double ScaleFontSize(double fontSizePoints, double fontScale)
    {
        double baseSize = fontSizePoints > 0 ? fontSizePoints : WordOleBaseFontPoints;
        double scale = fontScale > 0 ? fontScale : 1;
        return baseSize * scale;
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

    private static void ResetManagedEquationBaseline(object contentControl)
    {
        dynamic control = contentControl;
        TryCom(() => control.Range.Font.Position = 0);
        dynamic equations = control.Range.OMaths;
        int equationCount = Convert.ToInt32(equations.Count);
        for (int index = 1; index <= equationCount; index++)
        {
            dynamic equation = equations.Item(index);
            TryCom(() => equation.Range.Font.Position = 0);
        }
    }

    private object FindInsertedFormulaControl(
        int insertionPoint,
        string equationId)
    {
        dynamic paragraph = CreateDocumentRange(insertionPoint, insertionPoint).Paragraphs.Item(1).Range;
        dynamic controls = paragraph.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        object? equationControl = null;
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
        }

        if (equationControl == null)
        {
            throw new InvalidOperationException("Word did not preserve the inserted formula control.");
        }

        return equationControl;
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
        TryCom(() => inlineShape.Range.Font.Position = 0);
    }

    private static void ApplyEquationNumberBaseline(dynamic numberRange, double formulaHeightPoints)
    {
        if (formulaHeightPoints <= WordOleBaseFontPoints)
        {
            TryCom(() => numberRange.Font.Position = 0);
            return;
        }

        double offset = Math.Max(0, (formulaHeightPoints - WordOleBaseFontPoints) * 0.5);
        TryCom(() => numberRange.Font.Position = offset);
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
