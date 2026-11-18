using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    public MathTypeFormulaTarget? CaptureMathTypeFormula(object? selection)
    {
        try
        {
            dynamic selected = selection ?? (object)_wordApplication.Selection;
            dynamic shapes = selected.Range.InlineShapes;
            object? shape = Convert.ToInt32((object)shapes.Count) == 1
                && MathTypeOleBridge.IsEquation((object)shapes.Item(1)) ? (object)shapes.Item(1) : null;
            if (shape == null && selection != null)
            {
                var point = Cursor.Position;
                shape = FindInlineShapeAtScreenPoint(point.X, point.Y, MathTypeOleBridge.IsEquation);
            }

            if (shape == null) return null;
            dynamic range = ((dynamic)shape).Range.Duplicate;
            return new MathTypeFormulaTarget(CurrentDocument, GetCurrentDocumentId(),
                GetRangeStart(range), anchor: (object)range);
        }
        catch (COMException) { return null; }
    }

    private static bool IsCapturedMathTypeFormulaValid(MathTypeFormulaTarget target)
    {
        if (target.Anchor == null) return false;
        dynamic range = target.Anchor;
        dynamic shapes = range.InlineShapes;
        return WordDocumentIdentityStore.GetOrCreate(range.Document) == target.DocumentId
            && Convert.ToInt32((object)shapes.Count) == 1
            && Convert.ToBoolean((object)range.IsEqual(shapes.Item(1).Range))
            && MathTypeOleBridge.IsEquation((object)shapes.Item(1));
    }

    public Task InsertMathTypeAsync(FormulaMetadata metadata, byte[] compoundFile,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            ExecuteWithScreenUpdatingSuspended(() =>
            {
                dynamic selection = _wordApplication.Selection, selected = selection.Range;
                bool display = metadata.DisplayMode == FormulaDisplayMode.Display;
                int selectedStart = GetRangeStart(selected), selectedEnd = GetRangeEnd(selected);
                int originalLength = Convert.ToInt32((object)selected.StoryLength);
                dynamic range = ResolveInsertionTargetRange(selection, display).Duplicate;
                range.Collapse(WdCollapseEnd);
                int insertionStart = GetRangeStart(range);
                int addedParagraphs = Convert.ToInt32((object)range.StoryLength) - originalLength;
                object shape;
                try { shape = InsertNewMathTypeFormula((object)range, metadata, compoundFile, presentation, cancellationToken); }
                catch
                {
                    if (addedParagraphs > 0)
                    {
                        dynamic padding = RangeInStory((object)range, insertionStart, insertionStart + addedParagraphs);
                        if ((Convert.ToString((object?)padding.Text) ?? "").Trim('\r').Length == 0) padding.Delete();
                    }
                    throw;
                }
                if (!display && selectedEnd > selectedStart) RangeInStory((object)range, selectedStart, selectedEnd).Delete();
                MoveSelectionAfterInlineShape(shape, metadata.Identity.EquationId, display);
            });
            return true;
        }, cancellationToken);

    public Task ReplaceParsedMathTypeAsync(WordLatexParseCandidate candidate, FormulaMetadata metadata,
        byte[] compoundFile, OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            ValidateParsedFormulaInput(candidate, metadata);
            ExecuteWithScreenUpdatingSuspended(() =>
            {
                var target = PrepareParsedFormulaTarget(GetCurrentParsedSourceRange(candidate), candidate,
                    metadata.DisplayMode == FormulaDisplayMode.Display, useWholeDisplayParagraph: false);
                try { InsertNewMathTypeFormula((object)target.Range, metadata, compoundFile, presentation, cancellationToken); }
                catch
                {
                    RestoreParsedFormulaText(candidate, metadata, target);
                    throw;
                }
            });
            return true;
        }, cancellationToken);

    public Task UpdateMathTypeAsync(MathTypeFormulaTarget target, FormulaMetadata metadata, byte[] compoundFile,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            using var document = UseDocument(target.Document);
            dynamic original = FindMathTypeFormula(target);
            dynamic range = original.Range.Duplicate;
            range.Collapse(WdCollapseEnd);
            dynamic replacement;
            using (new EquationBookmarkScope(CurrentDocument, original.Range))
            {
                replacement = InsertNativeMathTypeInlineShape((object)range, compoundFile, presentation);
                try
                {
                    replacement.AlternativeText = original.AlternativeText;
                    SetOleInlineShapeSize(replacement, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
                    replacement.Range.Font.Position = original.Range.Font.Position;
                    cancellationToken.ThrowIfCancellationRequested();
                    original.Delete();
                }
                catch
                {
                    TryCom(() => replacement.Delete());
                    throw;
                }
            }
            MoveSelectionAfterInlineShape(replacement, metadata.Identity.EquationId, metadata.DisplayMode == FormulaDisplayMode.Display);
            return true;
        }, cancellationToken);

    private object InsertNewMathTypeFormula(object point, FormulaMetadata metadata, byte[] compoundFile,
        OlePresentationResult presentation, CancellationToken cancellationToken)
    {
        dynamic range = point, paragraph = range.Paragraphs.Item(1).Range;
        dynamic format = paragraph.ParagraphFormat.Duplicate, style = paragraph.Style;
        string styleName = Convert.ToString((object)style.NameLocal)!;
        int start = GetRangeStart(range), length = Convert.ToInt32((object)range.StoryLength);
        bool display = metadata.DisplayMode == FormulaDisplayMode.Display;
        bool numbered = metadata.NumberingMode != NumberingMode.None;
        object InsertShape(object cursor)
        {
            dynamic inserted = InsertNativeMathTypeInlineShape(cursor, compoundFile, presentation);
            ApplyOleInlineShapeLayout(inserted, presentation, display);
            if (numbered)
                inserted.AlternativeText = WordFormulaMetadataStore.BuildEquationTag(metadata.Identity.EquationId) + "|" + metadata.NumberText;
            return (object)inserted;
        }

        try
        {
            if (!numbered && display) range.ParagraphFormat.Alignment = WdAlignParagraphCenter;
            object shape = numbered
                ? (object)InsertNumberedInlineShape(point, metadata, presentation, InsertShape,
                    (cursor, state) => InsertNativeMathTypeNumber(cursor, state, metadata))
                : InsertShape(point);
            cancellationToken.ThrowIfCancellationRequested();
            return shape;
        }
        catch
        {
            RemoveInsertedStoryContent(point, start, length);
            RestoreMathTypeParagraph((object)range.Paragraphs.Item(1).Range, (object)format, (object)style, styleName);
            throw;
        }
    }

    private dynamic InsertNativeMathTypeInlineShape(object point, byte[] compoundFile, OlePresentationResult presentation)
    {
        dynamic insertion = point, paragraph = insertion.Paragraphs.Item(1).Range;
        dynamic format = paragraph.ParagraphFormat.Duplicate, style = paragraph.Style;
        string styleName = Convert.ToString((object)style.NameLocal)!;
        int start = GetRangeStart(insertion), length = Convert.ToInt32((object)insertion.StoryLength);
        byte[] native = MathTypeCompoundFile.ReadNative(compoundFile);
        string package = MathTypeWordPackage.Create(compoundFile, presentation,
            (float)presentation.WidthPoints, (float)presentation.HeightPoints);
        try
        {
            insertion.InsertXML(package);
            int end = start + Convert.ToInt32((object)insertion.StoryLength) - length;
            dynamic inserted = RangeInStory(point, start, end);
            if (Convert.ToInt32((object)inserted.InlineShapes.Count) != 1)
                throw new InvalidDataException("Word did not insert exactly one MathType equation.");
            dynamic shape = inserted.InlineShapes.Item(1);
            DeleteMathTypeInsertionPadding(point, GetRangeEnd(shape.Range), end);
            DeleteMathTypeInsertionPadding(point, start, GetRangeStart(shape.Range));
            RestoreMathTypeParagraph((object)shape.Range.Paragraphs.Item(1).Range, (object)format, (object)style, styleName);
            if (!MathTypeOleBridge.IsEquation((object)shape)
                || !MathTypeWordPackage.ReadNative(Convert.ToString((object)shape.Range.WordOpenXML)!).SequenceEqual(native))
                throw new InvalidDataException("Word did not preserve the native MathType equation.");
            return shape;
        }
        catch
        {
            RemoveInsertedStoryContent(point, start, length);
            RestoreMathTypeParagraph((object)insertion.Paragraphs.Item(1).Range, (object)format, (object)style, styleName);
            throw;
        }
    }

    private static void DeleteMathTypeInsertionPadding(object anchor, int start, int end)
    {
        if (end <= start) return;
        dynamic padding = RangeInStory(anchor, start, end);
        if ((Convert.ToString((object)padding.Text) ?? "").Trim('\r').Length != 0)
            throw new InvalidDataException("Word inserted unexpected text around the MathType equation.");
        padding.Delete();
    }

    private static void RemoveInsertedStoryContent(object anchor, int start, int length)
    {
        int added = Convert.ToInt32((object)((dynamic)anchor).StoryLength) - length;
        if (added > 0) RangeInStory(anchor, start, start + added).Delete();
    }

    private static dynamic RangeInStory(object anchor, int start, int end)
    {
        dynamic range = ((dynamic)anchor).Duplicate;
        range.SetRange(start, end);
        return range;
    }

    private object InsertNativeMathTypeNumber(object target, WordEquationNumberState state, FormulaMetadata metadata)
    {
        dynamic cursor = target;
        string left = WordEquationNumbering.GetLeftEnclosure(state.Enclosure);
        string right = WordEquationNumbering.GetRightEnclosure(state.Enclosure);
        object source;
        string label;
        string sequenceSwitch;
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            int position = GetRangeStart(cursor);
            sequenceSwitch = ShouldResetMathTypeSequence(position) ? @" \r 1" : "";
            dynamic field = CurrentDocument.Fields.Add(cursor, WdFieldEmpty,
                "SEQ " + WordMathTypeNumberRuns.EquationSequence + sequenceSwitch + " \\* Arabic", false);
            field.Update();
            string result = Convert.ToString((object)field.Result.Text)!.Trim();
            if (result.Length == 0 || result.Any(character => character is < '0' or > '9'))
                throw new InvalidDataException("Word did not calculate the MathType equation number.");
            label = left + state.Prefix + result + right;
            source = WholeNumberField((object)field);
        }
        else
        {
            sequenceSwitch = @" \c";
            label = left + metadata.NumberText + right;
            int start = GetRangeStart(cursor);
            InsertTextAtRange(cursor, label);
            source = (object)RangeInStory(target, start, start + label.Length);
        }
        string xml = WordMathTypeNumberRuns.CreateMathTypeNumber(label, metadata.NumberingMode,
            ReadNativeNumberFormat(), sequenceSwitch);
        return ReplaceNumberField(source, xml, label, true, metadata.Identity.EquationId);
    }

    private bool ShouldResetMathTypeSequence(int position)
    {
        dynamic before = CreateDocumentRange(0, position);
        int lastBoundary = -1, lastEquation = -1;
        foreach (dynamic control in before.ContentControls)
            if (IsNumberingBoundary(control, out WordNumberingBoundary _))
                lastBoundary = Math.Max(lastBoundary, GetRangeStart(control.Range));
        foreach (dynamic field in before.Fields)
        {
            if (IsFieldCode((object)field, WordMathTypeNumberRuns.SectionBoundary))
                lastBoundary = Math.Max(lastBoundary, GetRangeStart(field.Code));
            if (!IsFieldCode((object)field, WordMathTypeNumberRuns.PlaceReference)) continue;
            foreach (dynamic counter in field.Code.Fields)
                if (IsFieldCode((object)counter, "SEQ " + WordMathTypeNumberRuns.EquationSequence)
                    && Convert.ToString((object)counter.Code.Text)!.Contains(@"\h")
                    && !Convert.ToString((object)counter.Code.Text)!.Contains(@"\c"))
                    lastEquation = Math.Max(lastEquation, GetRangeStart(counter.Code));
        }
        return lastEquation < lastBoundary;
    }
}
