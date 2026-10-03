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
        dynamic shapes = ((dynamic)target.Document).InlineShapes;
        for (int i = 1; i <= Convert.ToInt32(shapes.Count); i++)
        {
            dynamic shape = shapes.Item(i);
            if (GetRangeStart(shape.Range) == target.Location && MathTypeOleBridge.IsEquation((object)shape)) return shape;
        }
        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
    }

    public Task<MathTypeFormulaContent> ReadMathTypeAsync(MathTypeFormulaTarget target, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic shape = FindMathTypeFormula(target);
            byte[] native = MathTypeWordPackage.ReadNative(Convert.ToString(shape.Range.WordOpenXML)!);
            return new MathTypeFormulaContent(MathTypeNativeEquation.ReadMathMl(native), MathTypeNativeEquation.ReadFontSizePoints(native));
        }, cancellationToken);

    public Task ReplaceMathTypeWithOleAsync(MathTypeFormulaTarget target, FormulaMetadata metadata,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            using (UseDocument(target.Document))
            using (BeginUndoRecord())
            {
                dynamic original = FindMathTypeFormula(target);
                float height = Convert.ToSingle(original.Height);
                dynamic insertion = original.Range.Duplicate;
                // Insert after the original, keeping its captured start stable until replacement succeeds.
                insertion.Collapse(0);
                dynamic? converted = null;
                try
                {
                    converted = InsertPlainOleInlineShape(insertion, metadata, presentation, false);
                    converted.LockAspectRatio = -1;
                    converted.Height = height;
                    SaveFormulaMetadata(metadata);
                    cancellationToken.ThrowIfCancellationRequested();
                    FindMathTypeFormula(target).Delete();
                }
                catch
                {
                    if (converted != null) converted.Delete();
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
            if (target.Metadata.NumberingMode != NumberingMode.None)
                throw new InvalidOperationException(WordAddInText.Get("MathTypeNumberedUnsupported"));
            using (UseDocument(target.Document))
            using (BeginUndoRecord())
            {
                dynamic original = TryFindOleInlineShapeById(target.Metadata.Identity.EquationId)
                    ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                cancellationToken.ThrowIfCancellationRequested();
                dynamic insertion = original.Range.Duplicate;
                insertion.Collapse(0);
                float width = Convert.ToSingle(original.Width);
                float height = Convert.ToSingle(original.Height);
                string package = MathTypeWordPackage.Create(compoundFile, presentation, width, height);
                string expected = MathTypeNativeEquation.ReadMathMl(MathTypeCompoundFile.ReadNative(compoundFile));
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
                    if (!MathTypeOleBridge.IsEquation((object)converted))
                        throw new InvalidOperationException(WordAddInText.Get("MathTypeNativeRequired"));
                    converted.AlternativeText = string.Empty;
                    string actual = MathTypeNativeEquation.ReadMathMl(MathTypeWordPackage.ReadNative(Convert.ToString(converted.Range.WordOpenXML)!));
                    if (actual != expected || Convert.ToInt32(CurrentDocument.InlineShapes.Count) != originalCount + 1
                        || Math.Abs(Convert.ToSingle(converted.Width) - width) > 0.1f
                        || Math.Abs(Convert.ToSingle(converted.Height) - height) > 0.1f)
                        throw new InvalidOperationException("MathType insertion content, count or dimensions failed validation.");
                    cancellationToken.ThrowIfCancellationRequested();
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
                    throw;
                }
                TryCom(() => converted.Range.Select());
            }
            return true;
        }, cancellationToken);
}
