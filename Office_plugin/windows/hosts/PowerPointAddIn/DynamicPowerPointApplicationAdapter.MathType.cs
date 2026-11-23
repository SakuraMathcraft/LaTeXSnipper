using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class DynamicPowerPointApplicationAdapter
{
    private byte[]? mathTypeTemplate;

    public MathTypeFormulaTarget? CaptureMathTypeFormula(object? selection)
    {
        try
        {
            return CreateMathTypeTarget(GetSelectedShape(selection ?? (object)_application.ActiveWindow.Selection));
        }
        catch (COMException) { return null; }
    }

    public MathTypeFormulaTarget? CaptureMathTypeFormulaAtPoint(IntPtr hitWindow, int x, int y)
    {
        IntPtr frame = GetActiveWindow();
        if (frame == IntPtr.Zero || GetAncestor(hitWindow, 2) != GetAncestor(frame, 2)) return null;
        dynamic window = _application.ActiveWindow;
        if (Convert.ToInt32((object)window.Active) != MsoTrue || Convert.ToInt32((object)window.ActivePane.ViewType) != 1)
            return null;
        object? selected = GetSelectedShape((object)window.Selection);
        return selected != null && IsShapeAtPoint((object)window, selected, x, y)
            ? CreateMathTypeTarget(selected) : null;
    }

    private MathTypeFormulaTarget? CreateMathTypeTarget(object? selected)
    {
        if (selected == null || !MathTypeOleBridge.IsEquation(selected)) return null;
        dynamic shape = selected;
        return new MathTypeFormulaTarget((object)_application.ActivePresentation, GetCurrentDocumentId(),
            Convert.ToInt32((object)shape.Id), Convert.ToInt32((object)shape.Parent.SlideIndex), selected);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetAncestor(IntPtr window, uint flags);

    [DllImport("user32.dll")]
    private static extern IntPtr GetActiveWindow();

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
        dynamic slide = target.Anchor is object anchor
            ? document.Slides.FindBySlideID(Convert.ToInt32((object)((dynamic)anchor).Parent.SlideID))
            : document.Slides.Item(target.ContainerIndex);
        dynamic shapes = slide.Shapes;
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
            return ReadMathTypeContent(target.Document, Convert.ToInt32((object)shape.Parent.SlideIndex), Convert.ToInt32((object)shape.Id));
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
            return ReplaceMathTypeShape(target.Presentation, (object)original, compoundFile, presentation, preserveSize: true, cancellationToken);
        }, cancellationToken);

    public Task InsertMathTypeAsync(byte[] compoundFile, OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            object document = _application.ActivePresentation;
            dynamic slide = GetActiveSlide();
            float width = (float)presentation.WidthPoints, height = (float)presentation.HeightPoints;
            InsertionPoint point = GetInsertionPoint(slide, width, height);
            InsertMathTypeShape(document, (object)slide, compoundFile, presentation,
                point.Left, point.Top, width, height, 0, null, cancellationToken);
            return true;
        }, cancellationToken);

    public Task UpdateMathTypeAsync(MathTypeFormulaTarget target, byte[] compoundFile,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() => ReplaceMathTypeShape(target.Document, (object)FindMathTypeFormula(target),
            compoundFile, presentation, preserveSize: false, cancellationToken), cancellationToken);

    private bool ReplaceMathTypeShape(object document, object originalShape, byte[] compoundFile,
        OlePresentationResult presentation, bool preserveSize, CancellationToken cancellationToken)
    {
        dynamic original = originalShape;
        InsertMathTypeShape(document, (object)original.Parent, compoundFile, presentation,
            Convert.ToSingle((object)original.Left), Convert.ToSingle((object)original.Top),
            preserveSize ? Convert.ToSingle((object)original.Width) : (float)presentation.WidthPoints,
            preserveSize ? Convert.ToSingle((object)original.Height) : (float)presentation.HeightPoints,
            Convert.ToSingle((object)original.Rotation), originalShape, cancellationToken);
        return true;
    }

    private void InsertMathTypeShape(object targetDocument, object targetSlide, byte[] compoundFile,
        OlePresentationResult presentation, float left, float top, float width, float height, float rotation,
        object? original, CancellationToken cancellationToken)
    {
        dynamic document = targetDocument, slide = targetSlide;
        int shapeCount = Convert.ToInt32(slide.Shapes.Count);
        var expected = MathTypeCompoundFile.ReadContent(compoundFile);
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
            var actual = ReadMathTypeContent(targetDocument, Convert.ToInt32((object)slide.SlideIndex), Convert.ToInt32((object)inserted.Id));
            if (actual.MathMl != expected.MathMl || actual.DisplayMode != expected.DisplayMode
                || Math.Abs(actual.FontSizePoints - expected.FontSizePoints) > 0.001
                || actual.OriginalLatex != expected.OriginalLatex || !Equals(actual.OriginalTypography, expected.OriginalTypography))
                throw new InvalidDataException("PowerPoint did not preserve the native MathType content.");
            if (original != null)
            {
                inserted.AlternativeText = MathTypeOleBridge.IsEquation(original) ? ((dynamic)original).AlternativeText : string.Empty;
                PreserveMathTypeLayer(original, inserted);
            }
            cancellationToken.ThrowIfCancellationRequested();
            if (original != null) ((dynamic)original).Delete();
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
        if (original != null)
        {
            TryCom(() => converted.Select());
            return;
        }
        TryCom(() =>
        {
            dynamic selection = _application.ActiveWindow.Selection;
            object? selected = GetSelectedShape((object)selection);
            if (selected != null && ((dynamic)selected).Id == converted!.Id)
                selection.Unselect();
        });
    }

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

    private static MathTypeFormulaContent ReadMathTypeContent(object presentation, int slideIndex, int shapeId)
    {
        string path = MathTypeTemporaryPath();
        try
        {
            ((dynamic)presentation).SaveCopyAs(path, 24);
            return MathTypePowerPointPackage.ReadContent(path, slideIndex, shapeId);
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
