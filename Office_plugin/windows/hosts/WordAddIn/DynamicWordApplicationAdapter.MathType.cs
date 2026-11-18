using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private WordFormulaEntry[] CollectSelectedMathTypeEntries()
    {
        dynamic shapes = _wordApplication.Selection.Range.InlineShapes;
        var entries = new System.Collections.Generic.List<WordFormulaEntry>();
        string documentId = GetCurrentDocumentId();
        for (int i = 1; i <= Convert.ToInt32(shapes.Count); i++)
        {
            dynamic shape = shapes.Item(i);
            if (MathTypeOleBridge.IsEquation((object)shape))
                entries.Add(new WordFormulaEntry(new MathTypeFormulaTarget(CurrentDocument, documentId, GetRangeStart(shape.Range))));
        }
        return entries.ToArray();
    }

    private dynamic FindMathTypeFormula(MathTypeFormulaTarget target)
    {
        if (target.Anchor != null)
        {
            if (IsCapturedMathTypeFormulaValid(target)) return ((dynamic)target.Anchor).InlineShapes.Item(1);
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }
        dynamic shapes = ((dynamic)target.Document).InlineShapes;
        for (int i = 1; i <= Convert.ToInt32(shapes.Count); i++)
        {
            dynamic shape = shapes.Item(i);
            if (GetRangeStart(shape.Range) == target.Location && MathTypeOleBridge.IsEquation((object)shape)) return shape;
        }
        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
    }

    public Task<(MathTypeFormulaContent Content, string? EquationId, NumberingMode NumberingMode, string NumberText)> ReadMathTypeAsync(
        MathTypeFormulaTarget target, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync<(MathTypeFormulaContent, string?, NumberingMode, string)>(() =>
        {
            using var document = UseDocument(target.Document);
            dynamic shape = FindMathTypeFormula(target);
            var content = MathTypeWordPackage.ReadContent(Convert.ToString(shape.Range.WordOpenXML)!);
            var number = ReadMathTypeNumber((object)shape);
            return (content, number?.EquationId, number?.Mode ?? NumberingMode.None, number?.Text ?? string.Empty);
        }, cancellationToken);

    private (string? EquationId, NumberingMode Mode, string Text, object Range, object? NativeField)? ReadMathTypeNumber(object shape)
    {
        dynamic equation = shape;
        string marker = Convert.ToString((object?)equation.AlternativeText) ?? string.Empty;
        int markerSeparator = marker.IndexOf('|');
        string equationId = WordFormulaMetadataStore.EquationIdFromTag(marker);
        dynamic range = equation.Range;
        dynamic paragraph = range.Paragraphs.Item(1).Range;
        var nativeField = FindNativeMathTypeNumber((object)paragraph);
        if (nativeField is { } native)
        {
            dynamic full = native.Whole;
            dynamic caption = native.Caption;
            if (GetRangeEnd(full) <= GetRangeStart(range) || GetRangeStart(full) >= GetRangeEnd(range))
            {
                if (equationId.Length != 0 && TryFindEquationNumberRangeById(equationId, out object? savedCaption))
                {
                    dynamic bookmark = savedCaption!;
                    if (GetRangeStart(bookmark) >= GetRangeStart(full) && GetRangeEnd(bookmark) <= GetRangeEnd(full))
                        caption = bookmark;
                }
                string label = (Convert.ToString((object?)caption.Text) ?? string.Empty).Trim();
                string manual = markerSeparator >= 0 ? marker.Substring(markerSeparator + 1) : string.Empty;
                if (manual.Length == 0 && !WordMathTypeNumberRuns.HasArabicCounter(label)) manual = label;
                return (equationId.Length == 0 ? null : equationId,
                    manual.Length == 0 ? NumberingMode.Automatic : NumberingMode.Manual, manual, (object)caption, native.Whole);
            }
        }
        if (markerSeparator >= 0 && equationId.Length != 0 && TryFindEquationNumberRangeById(equationId, out object? ownedRange))
        {
            dynamic number = ownedRange!;
            if (GetRangeStart(number) >= GetRangeStart(paragraph) && GetRangeEnd(number) <= GetRangeEnd(paragraph))
            {
                string manual = marker.Substring(markerSeparator + 1);
                return manual.Length == 0
                    ? (equationId, NumberingMode.Automatic, string.Empty, ownedRange!, null)
                    : (equationId, NumberingMode.Manual, manual, ownedRange!, null);
            }
        }

        if (!string.Equals(Convert.ToString((object?)paragraph.Style.NameLocal), "MTDisplayEquation", StringComparison.OrdinalIgnoreCase)
            || Convert.ToInt32((object)paragraph.InlineShapes.Count) != 1)
            return null;

        int start = GetRangeStart(paragraph);
        int end = GetRangeEnd(paragraph) - 1;
        dynamic left = CreateDocumentRange(start, GetRangeStart(range));
        dynamic right = CreateDocumentRange(GetRangeEnd(range), end);
        bool leftNumber = ContainsSequenceField((object)left);
        bool rightNumber = ContainsSequenceField((object)right);
        if (leftNumber == rightNumber) return null;
        dynamic numberSide = leftNumber ? left : right;
        while (GetRangeStart(numberSide) < GetRangeEnd(numberSide) &&
            Convert.ToString((object?)CreateDocumentRange(GetRangeStart(numberSide), GetRangeStart(numberSide) + 1).Text) == "\t")
            numberSide.MoveStart(WdCharacter, 1);
        while (GetRangeStart(numberSide) < GetRangeEnd(numberSide) &&
            Convert.ToString((object?)CreateDocumentRange(GetRangeEnd(numberSide) - 1, GetRangeEnd(numberSide)).Text) == "\t")
            numberSide.MoveEnd(WdCharacter, -1);
        return (null, NumberingMode.Automatic, string.Empty, (object)numberSide, null);
    }

    private static bool ContainsSequenceField(object range)
    {
        dynamic fields = ((dynamic)range).Fields;
        for (int index = 1; index <= Convert.ToInt32((object)fields.Count); index++)
        {
            string code = Convert.ToString((object?)fields.Item(index).Code.Text) ?? string.Empty;
            if (code.TrimStart().StartsWith("SEQ ", StringComparison.OrdinalIgnoreCase)) return true;
        }
        return false;
    }

    public Task ReplaceMathTypeWithOleAsync(MathTypeFormulaTarget target, FormulaMetadata metadata,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            using (UseDocument(target.Document))
            using (BeginUndoRecord())
            {
                dynamic original = FindMathTypeFormula(target);
                var number = ReadMathTypeNumber((object)original);
                if ((number?.Mode ?? NumberingMode.None) != metadata.NumberingMode)
                    throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
                using var bookmarks = new EquationBookmarkScope(CurrentDocument, original.Range, replacedNumber: number?.NativeField);
                float width = Convert.ToSingle(original.Width);
                float height = Convert.ToSingle(original.Height);
                int baseline = Convert.ToInt32((object)original.Range.Font.Position);
                int aspectRatio = Convert.ToInt32((object)original.LockAspectRatio);
                dynamic insertion = original.Range.Duplicate;
                // Insert after the original, keeping its captured start stable until replacement succeeds.
                insertion.Collapse(0);
                dynamic? converted = null;
                bool addedBookmark = false;
                try
                {
                    converted = InsertPlainOleInlineShape(insertion, metadata, presentation, false);
                    converted.LockAspectRatio = 0;
                    converted.Width = width;
                    converted.Height = height;
                    converted.LockAspectRatio = aspectRatio;
                    converted.Range.Font.Position = baseline;
                    SaveFormulaMetadata(metadata);
                    cancellationToken.ThrowIfCancellationRequested();
                    if (number is { NativeField: not null } native)
                    {
                        dynamic caption = native.Range;
                        string label = Convert.ToString((object)caption.Text)!.Trim();
                        bool first = IsFirstNumberInSection(GetRangeStart((dynamic)native.NativeField));
                        string? numberXml = metadata.NumberingMode == NumberingMode.Automatic
                            ? WordMathTypeNumberRuns.CreateLaTeXSnipperNumber(label, first) : null;
                        _ = ReplaceNumberField(native.NativeField!, numberXml, label, false, metadata.Identity.EquationId);
                    }
                    else if (number is { EquationId: null })
                    {
                        AddOrReplaceEquationBookmark(metadata.Identity.EquationId, (dynamic)number.Value.Range);
                        addedBookmark = true;
                    }
                    original.Delete();
                }
                catch
                {
                    if (converted != null) converted.Delete();
                    if (addedBookmark) TryCom(() => CurrentDocument.Bookmarks.Item(
                        WordEquationNumbering.BuildBookmarkName(metadata.Identity.EquationId)).Delete());
                    throw;
                }
                TryCom(() => converted.Range.Select());
            }
            return true;
        }, cancellationToken);

    public Task<System.Collections.Generic.IReadOnlyList<WordFormulaEditTarget>> LoadSelectedFormulaTargetsAsync(CancellationToken cancellationToken)
    {
        return _officeThread.InvokeAsync(() =>
        {
            object document = CurrentDocument;
            return (System.Collections.Generic.IReadOnlyList<WordFormulaEditTarget>)CollectSelectedFormulas()
                .Select(EnsureUniqueFormulaIdentity)
                .OrderByDescending(GetFormulaStart)
                .Select(item => new WordFormulaEditTarget(document, item.ContentControl, item.Metadata, item.IsOleInlineShape))
                .ToArray();
        }, cancellationToken);
    }

    public Task ReplaceWithMathTypeAsync(WordFormulaEditTarget target, byte[] compoundFile, OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            if (!target.IsOle || !IsFormulaEditTargetValid(target))
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
            using (UseDocument(target.Document))
            using (BeginUndoRecord())
            {
                dynamic original = TryFindOleInlineShapeById(target.Metadata.Identity.EquationId)
                    ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                cancellationToken.ThrowIfCancellationRequested();
                bool numbered = target.Metadata.NumberingMode != NumberingMode.None;
                object? numberRange = numbered ? (object)FindEquationNumberRangeById(target.Metadata.Identity.EquationId) : null;
                object? oldNumber = numberRange == null ? null : LaTeXSnipperNumberField(numberRange);
                using var bookmarks = new EquationBookmarkScope(CurrentDocument, original.Range, replacedNumber: oldNumber);
                dynamic paragraph = original.Range.Paragraphs.Item(1).Range;
                dynamic paragraphFormat = paragraph.ParagraphFormat.Duplicate;
                dynamic style = paragraph.Style;
                string styleName = Convert.ToString((object?)style.NameLocal) ?? string.Empty;
                int baseline = Convert.ToInt32((object)original.Range.Font.Position);
                dynamic insertion = original.Range.Duplicate;
                insertion.Collapse(0);
                float width = Convert.ToSingle(original.Width);
                float height = Convert.ToSingle(original.Height);
                string package = MathTypeWordPackage.Create(compoundFile, presentation, width, height);
                byte[] expected = MathTypeCompoundFile.ReadNative(compoundFile);
                int originalCount = Convert.ToInt32(CurrentDocument.InlineShapes.Count);
                int insertionStart = Convert.ToInt32(insertion.Start);
                int documentEnd = Convert.ToInt32(CurrentDocument.Content.End);
                dynamic? converted = null;
                dynamic? inserted = null;
                try
                {
                    insertion.InsertXML(package);
                    int insertedLength = Convert.ToInt32(CurrentDocument.Content.End) - documentEnd;
                    inserted = CurrentDocument.Range(insertionStart, insertionStart + insertedLength);
                    if (Convert.ToInt32(inserted.InlineShapes.Count) != 1)
                        throw new InvalidOperationException("MathType insertion did not produce exactly one equation.");
                    converted = inserted.InlineShapes.Item(1);
                    dynamic trailing = CurrentDocument.Range(Convert.ToInt32(converted.Range.End), Convert.ToInt32(inserted.End));
                    dynamic leading = CurrentDocument.Range(Convert.ToInt32(inserted.Start), Convert.ToInt32(converted.Range.Start));
                    string trailingText = Convert.ToString((object?)trailing.Text) ?? string.Empty;
                    string leadingText = Convert.ToString((object?)leading.Text) ?? string.Empty;
                    if (trailingText.Trim('\r').Length != 0 || leadingText.Trim('\r').Length != 0)
                        throw new InvalidOperationException("MathType insertion unexpectedly introduced surrounding text.");
                    if (Convert.ToInt32(trailing.End) > Convert.ToInt32(trailing.Start)) trailing.Delete();
                    if (Convert.ToInt32(leading.End) > Convert.ToInt32(leading.Start)) leading.Delete();
                    dynamic convertedParagraph = converted.Range.Paragraphs.Item(1).Range;
                    if (GetRangeStart(convertedParagraph) != GetRangeStart(original.Range.Paragraphs.Item(1).Range))
                        throw new InvalidOperationException("MathType insertion split the equation paragraph.");
                    RestoreMathTypeParagraph((object)convertedParagraph, (object)paragraphFormat, (object)style, styleName);
                    if (!MathTypeOleBridge.IsEquation((object)converted))
                        throw new InvalidOperationException(WordAddInText.Get("MathTypeNativeRequired"));
                    converted.AlternativeText = numbered
                        ? WordFormulaMetadataStore.BuildEquationTag(target.Metadata.Identity.EquationId) + "|" + target.Metadata.NumberText
                        : string.Empty;
                    converted.Range.Font.Position = baseline;
                    float insertedWidth = Convert.ToSingle((object)converted.Width);
                    float insertedHeight = Convert.ToSingle((object)converted.Height);
                    if (Math.Abs(insertedWidth - width) > 0.1f || Math.Abs(insertedHeight - height) > 0.1f)
                    {
                        int lockAspectRatio = Convert.ToInt32((object)original.LockAspectRatio);
                        converted.LockAspectRatio = 0;
                        converted.Width = width;
                        converted.Height = height;
                        converted.LockAspectRatio = lockAspectRatio;
                    }
                    byte[] actual = MathTypeWordPackage.ReadNative(Convert.ToString(converted.Range.WordOpenXML)!);
                    if (!actual.SequenceEqual(expected))
                        throw new InvalidOperationException("Word changed the MathType native equation stream.");
                    if (Convert.ToInt32(CurrentDocument.InlineShapes.Count) != originalCount + 1)
                        throw new InvalidOperationException("Word changed the MathType equation count during insertion.");
                    float actualWidth = Convert.ToSingle((object)converted.Width);
                    float actualHeight = Convert.ToSingle((object)converted.Height);
                    if (Math.Abs(actualWidth - width) > 0.1f || Math.Abs(actualHeight - height) > 0.1f)
                        throw new InvalidOperationException($"Word changed the MathType equation size from {width} × {height} to {actualWidth} × {actualHeight} pt.");
                    cancellationToken.ThrowIfCancellationRequested();
                    if (oldNumber != null)
                    {
                        dynamic caption = numberRange!;
                        string label = Convert.ToString((object)caption.Text)!;
                        string numberXml = WordMathTypeNumberRuns.CreateMathTypeNumber(label, target.Metadata.NumberingMode,
                            ReadNativeNumberFormat());
                        _ = ReplaceNumberField(oldNumber, numberXml, label, true, target.Metadata.Identity.EquationId);
                    }
                    original.Delete();
                }
                catch
                {
                    if (inserted != null)
                    {
                        if (Convert.ToInt32(inserted.End) > Convert.ToInt32(inserted.Start)) inserted.Delete();
                    }
                    else
                    {
                        int insertedLength = Convert.ToInt32(CurrentDocument.Content.End) - documentEnd;
                        if (insertedLength > 0) CurrentDocument.Range(insertionStart, insertionStart + insertedLength).Delete();
                    }
                    RestoreMathTypeParagraph((object)original.Range.Paragraphs.Item(1).Range, (object)paragraphFormat,
                        (object)style, styleName);
                    throw;
                }
                TryCom(() => converted.Range.Select());
            }
            return true;
        }, cancellationToken);

    private static void RestoreMathTypeParagraph(object paragraph, object format, object style, string styleName)
    {
        dynamic range = paragraph;
        if (Convert.ToString((object?)range.Style.NameLocal) != styleName) range.Style = style;
        range.ParagraphFormat = format;
    }
}
