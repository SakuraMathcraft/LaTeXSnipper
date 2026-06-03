using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class DynamicPowerPointApplicationAdapter : IPowerPointApplicationAdapter
{
    private const int MsoFalse = 0;
    private const int MsoTrue = -1;
    private const float DefaultLeftPoints = 72f;
    private const float DefaultTopPoints = 96f;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _application;

    public DynamicPowerPointApplicationAdapter(object application)
    {
        _application = application ?? throw new ArgumentNullException(nameof(application));
    }

    public Task InsertFormulaImageAsync(PowerPointRenderedImage image, FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (image == null)
        {
            throw new ArgumentNullException(nameof(image));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        dynamic slide = GetActiveSlide();
        InsertionPoint insertionPoint = GetInsertionPoint(slide, image.WidthPoints, image.HeightPoints);
        return InsertPictureAtAsync(slide, image, metadata, insertionPoint.Left, insertionPoint.Top);
    }

    public Task InsertFormulaImageAtPositionAsync(PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float scale, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (image == null)
        {
            throw new ArgumentNullException(nameof(image));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (scale <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(scale), "Shape scale must be positive.");
        }

        dynamic slide = GetActiveSlide();
        return InsertPictureAtAsync(
            slide,
            image,
            metadata,
            left,
            top,
            image.WidthPoints * scale,
            image.HeightPoints * scale);
    }

    public Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, OlePresentationResult presentation, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        dynamic slide = GetActiveSlide();
        InsertionPoint insertionPoint = GetInsertionPoint(slide, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
        return InsertOleObjectAtAsync(slide, metadata, presentation, insertionPoint.Left, insertionPoint.Top);
    }

    public Task InsertOleFormulaObjectAtPositionAsync(FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float shapeScale, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        if (shapeScale <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(shapeScale), "Shape scale must be positive.");
        }

        dynamic slide = GetActiveSlide();
        return InsertOleObjectAtAsync(
            slide,
            metadata,
            presentation,
            left,
            top,
            (float)presentation.WidthPoints * shapeScale,
            (float)presentation.HeightPoints * shapeScale);
    }

    private static Task InsertPictureAtAsync(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top)
    {
        return InsertPictureAtAsync(slide, image, metadata, left, top, image.WidthPoints, image.HeightPoints);
    }

    private static Task InsertPictureAtAsync(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float width, float height)
    {
        dynamic picture = slide.Shapes.AddPicture(image.Path, MsoFalse, MsoTrue, left, top, width, height);
        PowerPointFormulaMetadataStore.ApplyToShape(picture, metadata, image.WidthPoints, image.HeightPoints);
        PowerPointFormulaMetadataStore.ApplyImagePath(picture, image.Path);
        return Task.CompletedTask;
    }

    private static Task InsertOleObjectAtAsync(dynamic slide, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top)
    {
        return InsertOleObjectAtAsync(slide, metadata, presentation, left, top, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
    }

    private static Task InsertOleObjectAtAsync(dynamic slide, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float width, float height)
    {
        OleFormulaPendingPayloadStore.SavePendingPayload(metadata, presentation);
        dynamic shape = slide.Shapes.AddOLEObject(
            left,
            top,
            width,
            height,
            OleFormulaProgId,
            string.Empty,
            MsoFalse,
            string.Empty,
            0,
            string.Empty,
            MsoFalse);
        PowerPointFormulaMetadataStore.ApplyToShape(shape, metadata, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
        return Task.CompletedTask;
    }

    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic shape = GetSelectedShape();
        return Task.FromResult(ReadMetadataFromShape(shape));
    }

    public (float Left, float Top, float ShapeScale) GetSelectedShapeFrame()
    {
        dynamic shape = GetSelectedShape();
        float naturalWidth = ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
        return ((float)shape.Left, (float)shape.Top, (float)shape.Width / naturalWidth);
    }

    public Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic shape = GetSelectedShape();
        CleanupImageFile(shape);
        shape.Delete();
        return Task.CompletedTask;
    }

    public Task<int> DeleteSelectedFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var shapes = new System.Collections.Generic.List<object>(GetSelectedFormulaShapes());
        if (shapes.Count == 0)
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
        }

        foreach (object item in shapes)
        {
            cancellationToken.ThrowIfCancellationRequested();
            dynamic shape = item;
            CleanupImageFile(shape);
            shape.Delete();
        }

        return Task.FromResult(shapes.Count);
    }

    private dynamic GetSelectedShape()
    {
        var shapes = new System.Collections.Generic.List<object>(GetSelectedFormulaShapes());
        if (shapes.Count > 0)
        {
            return shapes[0];
        }

        throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
    }

    private System.Collections.Generic.IReadOnlyList<object> GetSelectedFormulaShapes()
    {
        var shapes = new System.Collections.Generic.List<object>();
        try
        {
            dynamic selection = _application.ActiveWindow.Selection;
            if (selection.Type != 2)
            {
                throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
            }

            dynamic shapeRange = selection.ShapeRange;
            if (shapeRange.Count < 1)
            {
                throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
            }

            for (int i = 1; i <= Convert.ToInt32(shapeRange.Count); i++)
            {
                dynamic shape = shapeRange[i];
                string equationId = ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag);
                if (!string.IsNullOrWhiteSpace(equationId))
                {
                    shapes.Add(shape);
                }
            }
        }
        catch (InvalidOperationException)
        {
            throw;
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"), exc);
        }

        return shapes;
    }

    private static FormulaMetadata ReadMetadataFromShape(dynamic shape)
    {
        string equationId = ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag);
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        string latex = ReadTag(shape, PowerPointFormulaMetadataStore.LatexTag);
        string displayModeText = ReadTag(shape, PowerPointFormulaMetadataStore.DisplayModeTag);
        string schemaVersionText = ReadTag(shape, PowerPointFormulaMetadataStore.SchemaVersionTag);

        FormulaDisplayMode displayMode = displayModeText == "Inline" ? FormulaDisplayMode.Inline : FormulaDisplayMode.Display;
        int schemaVersion = int.TryParse(schemaVersionText, out int version) ? version : 1;

        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", equationId),
            latex,
            displayMode,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion);
    }

    private static void CleanupImageFile(dynamic shape)
    {
        try
        {
            string path = ReadTag(shape, PowerPointFormulaMetadataStore.ImagePathTag);
            if (string.IsNullOrWhiteSpace(path))
            {
                return;
            }

            string tempRoot = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "LaTeXSnipper", "OfficePlugin", "PowerPoint");
            string fullPath = System.IO.Path.GetFullPath(path);
            string fullTempRoot = System.IO.Path.GetFullPath(tempRoot);
            if (!fullPath.StartsWith(fullTempRoot, StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            if (System.IO.File.Exists(fullPath))
            {
                System.IO.File.Delete(fullPath);
            }
        }
        catch
        {
        }
    }

    private static string ReadTag(dynamic shape, string tagName)
    {
        try
        {
            return shape.Tags[tagName] ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private static float ReadRequiredFloatTag(dynamic shape, string tagName)
    {
        string value = ReadTag(shape, tagName);
        if (!float.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float result) || result <= 0)
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return result;
    }

    private dynamic GetActiveSlide()
    {
        try
        {
            return _application.ActiveWindow.View.Slide;
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException("Open a PowerPoint slide before inserting a formula.", exc);
        }
    }

    private static InsertionPoint GetInsertionPoint(dynamic slide, float widthPoints, float heightPoints)
    {
        try
        {
            float width = Convert.ToSingle(slide.Parent.PageSetup.SlideWidth, System.Globalization.CultureInfo.InvariantCulture);
            float height = Convert.ToSingle(slide.Parent.PageSetup.SlideHeight, System.Globalization.CultureInfo.InvariantCulture);
            float left = Math.Max(DefaultLeftPoints, (width - widthPoints) / 2f);
            float top = Math.Max(DefaultTopPoints, (height - heightPoints) / 2f);
            return new InsertionPoint(left, top);
        }
        catch
        {
            return new InsertionPoint(DefaultLeftPoints, DefaultTopPoints);
        }
    }

    private readonly struct InsertionPoint
    {
        public InsertionPoint(float left, float top)
        {
            Left = left;
            Top = top;
        }

        public float Left { get; }

        public float Top { get; }
    }
}
