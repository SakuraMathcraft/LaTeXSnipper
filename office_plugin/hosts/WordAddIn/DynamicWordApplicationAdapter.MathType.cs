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

    public Task<string> ReadMathTypeMathMlAsync(MathTypeFormulaTarget target, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic shape = FindMathTypeFormula(target);
            shape.OLEFormat.Activate();
            object server = shape.OLEFormat.Object;
            try { return MathTypeOleBridge.ReadAndCloseMathMl(server); }
            finally { if (System.Runtime.InteropServices.Marshal.IsComObject(server)) System.Runtime.InteropServices.Marshal.ReleaseComObject(server); }
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

    public Task ReplaceWithMathTypeAsync(WordFormulaEditTarget target, string mathMl, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            if (!target.IsOle || !IsFormulaEditTargetValid(target))
                throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
            if (target.Metadata.NumberingMode != NumberingMode.None)
                throw new InvalidOperationException(WordAddInText.Get("MathTypeNumberedUnsupported"));
            MathTypeOleBridge.EnsureAvailable();
            using (UseDocument(target.Document))
            using (BeginUndoRecord())
            {
                dynamic original = TryFindOleInlineShapeById(target.Metadata.Identity.EquationId)
                    ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                float width = Convert.ToSingle(original.Width), height = Convert.ToSingle(original.Height);
                string objectXml = CreateMathTypeObjectXml(mathMl, width, height);
                cancellationToken.ThrowIfCancellationRequested();
                dynamic insertion = original.Range.Duplicate;
                insertion.Collapse(0);
                int insertionStart = GetRangeStart(insertion);
                dynamic? converted = null;
                try
                {
                    // Insert an already saved native object: the SDK never updates
                    // this document's placeholder or its cached scaling factors.
                    insertion.InsertXML(objectXml);
                    converted = FindMathTypeFormula(new MathTypeFormulaTarget(target.Document,
                        target.Metadata.Identity.DocumentId, insertionStart));
                    if (!MathTypeOleBridge.IsEquation((object)converted))
                        throw new InvalidOperationException(WordAddInText.Get("MathTypeNativeRequired"));
                    converted.AlternativeText = string.Empty;
                    if (Math.Abs(Convert.ToSingle(converted.Width) - width) > Math.Max(0.5f, width * 0.01f)
                        || Math.Abs(Convert.ToSingle(converted.Height) - height) > Math.Max(0.5f, height * 0.01f))
                        throw new InvalidOperationException("MathType 对象未能恢复转换前的宽度和高度。");
                    original = TryFindOleInlineShapeById(target.Metadata.Identity.EquationId)
                        ?? throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
                    original.Delete();
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

    private string CreateMathTypeObjectXml(string mathMl, float width, float height)
    {
        dynamic scratch = _wordApplication.Documents.Add(Visible: false);
        try
        {
            dynamic shape = scratch.InlineShapes.AddOLEObject(MathTypeOleBridge.ProgId);
            object server = shape.OLEFormat.Object;
            try { MathTypeOleBridge.WriteMathMl(server, mathMl); }
            finally { if (System.Runtime.InteropServices.Marshal.IsComObject(server)) System.Runtime.InteropServices.Marshal.ReleaseComObject(server); }
            string objectXml = Convert.ToString(shape.Range.WordOpenXML);
            var xml = System.Xml.Linq.XDocument.Parse(objectXml);
            System.Xml.Linq.XNamespace word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
            System.Xml.Linq.XNamespace vml = "urn:schemas-microsoft-com:vml";
            var frame = xml.Descendants(word + "object").Single().Element(vml + "shape")
                ?? throw new InvalidOperationException(WordAddInText.Get("MathTypeNativeRequired"));
            // Persist each original dimension explicitly in points. Importing the
            // complete native storage and frame avoids Word's late OLE resizing.
            frame.SetAttributeValue("style", FormattableString.Invariant($"width:{width:R}pt;height:{height:R}pt"));
            return xml.ToString(System.Xml.Linq.SaveOptions.DisableFormatting);
        }
        finally { scratch.Close(0); }
    }
}
