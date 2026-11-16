using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class DynamicPowerPointApplicationAdapter
{
    private byte[]? mathTypeTemplate;

    public Task<System.Collections.Generic.IReadOnlyList<PowerPointFormulaEntry>> LoadConversionEntriesAsync(bool includeMathType, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            var entries = new System.Collections.Generic.List<PowerPointFormulaEntry>(CollectFormulaEntries(false, cancellationToken));
            if (includeMathType)
            {
                dynamic selection = _application.ActiveWindow.Selection;
                if (selection.Type == 2)
                {
                    dynamic shapes = selection.ShapeRange;
                    string documentId = GetCurrentDocumentId();
                    for (int i = 1; i <= Convert.ToInt32(shapes.Count); i++)
                    {
                        dynamic shape = shapes.Item(i);
                        if (MathTypeOleBridge.IsEquation((object)shape))
                            entries.Add(new PowerPointFormulaEntry(new MathTypeFormulaTarget(_application.ActivePresentation, documentId,
                                Convert.ToInt32(shape.Id), Convert.ToInt32(shape.Parent.SlideIndex)), Convert.ToInt32(shape.Parent.SlideIndex)));
                    }
                }
            }
            return (System.Collections.Generic.IReadOnlyList<PowerPointFormulaEntry>)entries;
        }, cancellationToken);

    private static dynamic FindMathTypeFormula(MathTypeFormulaTarget target)
    {
        dynamic document = target.Document;
        dynamic shapes = document.Slides.Item(target.ContainerIndex).Shapes;
        for (int i = 1; i <= Convert.ToInt32(shapes.Count); i++)
        {
            dynamic shape = shapes.Item(i);
            if (Convert.ToInt32(shape.Id) == target.Location && MathTypeOleBridge.IsEquation((object)shape)) return shape;
        }
        throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
    }

    public Task<MathTypeFormulaContent> ReadMathTypeAsync(MathTypeFormulaTarget target, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic shape = FindMathTypeFormula(target);
            byte[] native = ReadMathTypeNative(target.Document, target.ContainerIndex, Convert.ToInt32(shape.Id));
            return new MathTypeFormulaContent(MathTypeNativeEquation.ReadMathMl(native), MathTypeNativeEquation.ReadFontSizePoints(native));
        }, cancellationToken);

    public Task ReplaceMathTypeWithOleAsync(MathTypeFormulaTarget target, FormulaMetadata metadata,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic original = FindMathTypeFormula(target);
            dynamic? converted = null;
            try
            {
                converted = CreateOleObjectAt(original.Parent, metadata, presentation,
                    Convert.ToSingle(original.Left), Convert.ToSingle(original.Top), Convert.ToSingle(original.Width), Convert.ToSingle(original.Height));
                PreserveMathTypeLayer(original, converted);
                cancellationToken.ThrowIfCancellationRequested();
                original.Delete();
            }
            catch
            {
                if (converted != null) TryDeleteShape(converted);
                throw;
            }
            TryCom(() => converted.Select());
            return true;
        }, cancellationToken);

    public Task<System.Collections.Generic.IReadOnlyList<PowerPointFormulaEditTarget>> LoadSelectedFormulaTargetsAsync(CancellationToken cancellationToken)
    {
        return _officeThread.InvokeAsync(() =>
        {
            object presentation = _application.ActivePresentation;
            var shapes = GetSelectedFormulaShapes();
            EnsureUniqueShapeIdentities(shapes);
            var targets = new System.Collections.Generic.List<PowerPointFormulaEditTarget>();
            foreach (object shape in shapes)
                targets.Add(new PowerPointFormulaEditTarget(PowerPointFormulaMetadataStore.LoadFromShape(shape), presentation));
            return (System.Collections.Generic.IReadOnlyList<PowerPointFormulaEditTarget>)targets;
        }, cancellationToken);
    }

    public Task ReplaceWithMathTypeAsync(PowerPointFormulaEditTarget target, byte[] compoundFile,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic original = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
            if (!OleFormulaContent.IsFormula((object)original))
                throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
            dynamic document = target.Presentation, slide = original.Parent;
            float left = Convert.ToSingle(original.Left), top = Convert.ToSingle(original.Top);
            float width = Convert.ToSingle(original.Width), height = Convert.ToSingle(original.Height);
            float rotation = Convert.ToSingle(original.Rotation);
            int shapeCount = Convert.ToInt32(slide.Shapes.Count);
            byte[] expected = MathTypeCompoundFile.ReadNative(compoundFile);
            byte[] package = MathTypePowerPointPackage.Create(GetMathTypeTemplate(), compoundFile, presentation,
                left, top, width, height, rotation,
                Convert.ToSingle(document.PageSetup.SlideWidth), Convert.ToSingle(document.PageSetup.SlideHeight));
            string path = MathTypeTemporaryPath();
            dynamic? staging = null, converted = null;
            try
            {
                File.WriteAllBytes(path, package);
                staging = _application.Presentations.Open(path, MsoTrue, MsoFalse, MsoFalse);
                if (Convert.ToInt32(staging.Slides.Item(1).Shapes.Count) != 1)
                    throw new InvalidDataException("MathType insertion package did not produce one shape.");
                object sourceShape = staging.Slides.Item(1).Shapes.Item(1);
                PowerPointClipboard.WithSavedClipboard(() =>
                {
                    ((dynamic)sourceShape).Copy();
                    dynamic pasted = slide.Shapes.Paste();
                    if (Convert.ToInt32(pasted.Count) != 1)
                    {
                        pasted.Delete();
                        throw new InvalidDataException("MathType insertion produced multiple shapes.");
                    }
                    converted = pasted.Item(1);
                    return true;
                });
                staging.Close();
                staging = null;
                File.Delete(path);
                dynamic inserted = converted ?? throw new InvalidDataException("PowerPoint did not insert the MathType object.");
                if (!MathTypeOleBridge.IsEquation((object)inserted))
                    throw new InvalidDataException("PowerPoint did not preserve the native MathType class.");
                // PowerPoint offsets pasted shapes even when their package has the correct coordinates.
                inserted.Left = left;
                inserted.Top = top;
                if (Convert.ToInt32(slide.Shapes.Count) != shapeCount + 1
                    || Math.Abs(Convert.ToSingle(inserted.Width) - width) > 0.1f
                    || Math.Abs(Convert.ToSingle(inserted.Height) - height) > 0.1f
                    || Math.Abs(Convert.ToSingle(inserted.Left) - left) > 0.1f
                    || Math.Abs(Convert.ToSingle(inserted.Top) - top) > 0.1f
                    || Math.Abs(Convert.ToSingle(inserted.Rotation) - rotation) > 0.1f)
                    throw new InvalidDataException($"PowerPoint did not preserve the equation geometry: "
                        + $"({left}, {top}, {width}, {height}, {rotation}) -> "
                        + $"({inserted.Left}, {inserted.Top}, {inserted.Width}, {inserted.Height}, {inserted.Rotation}).");
                byte[] actual = ReadMathTypeNative(target.Presentation, Convert.ToInt32(slide.SlideIndex), Convert.ToInt32(inserted.Id));
                if (MathTypeNativeEquation.ReadMathMl(actual) != MathTypeNativeEquation.ReadMathMl(expected)
                    || Math.Abs(MathTypeNativeEquation.ReadFontSizePoints(actual) - MathTypeNativeEquation.ReadFontSizePoints(expected)) > 0.001)
                    throw new InvalidDataException("PowerPoint did not preserve the native MathType content.");
                inserted.AlternativeText = string.Empty;
                PreserveMathTypeLayer(original, inserted);
                cancellationToken.ThrowIfCancellationRequested();
                original.Delete();
            }
            catch
            {
                if (converted != null) TryDeleteShape(converted);
                throw;
            }
            finally
            {
                if (staging != null) TryCom(() => staging.Close());
                File.Delete(path);
            }
            TryCom(() => converted.Select());
            return true;
        }, cancellationToken);

    private byte[] GetMathTypeTemplate()
    {
        if (mathTypeTemplate != null) return mathTypeTemplate;
        string path = MathTypeTemporaryPath();
        dynamic? blank = null;
        try
        {
            blank = _application.Presentations.Add(MsoFalse);
            blank.Slides.Add(1, 12);
            blank.SaveCopyAs(path, 24);
            mathTypeTemplate = File.ReadAllBytes(path);
            return mathTypeTemplate;
        }
        finally
        {
            if (blank != null) TryCom(() => blank.Close());
            File.Delete(path);
        }
    }

    private static byte[] ReadMathTypeNative(object presentation, int slideIndex, int shapeId)
    {
        string path = MathTypeTemporaryPath();
        try
        {
            ((dynamic)presentation).SaveCopyAs(path, 24);
            return MathTypePowerPointPackage.ReadNative(path, slideIndex, shapeId);
        }
        finally { File.Delete(path); }
    }

    private static string MathTypeTemporaryPath()
        => Path.Combine(Path.GetTempPath(), "latexsnipper-mathtype-" + Guid.NewGuid().ToString("N") + ".pptx");

    private static void PreserveMathTypeLayer(dynamic original, dynamic converted)
    {
        int position = Convert.ToInt32(original.ZOrderPosition) + 1;
        while (Convert.ToInt32(converted.ZOrderPosition) > position) converted.ZOrder(3);
        while (Convert.ToInt32(converted.ZOrderPosition) < position) converted.ZOrder(2);
    }

}
