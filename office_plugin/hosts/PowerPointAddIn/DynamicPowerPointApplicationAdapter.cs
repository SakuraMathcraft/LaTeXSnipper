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

    public Task InsertFormulaImageAtPositionAsync(PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, CancellationToken cancellationToken)
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
        return InsertPictureAtAsync(slide, image, metadata, left, top);
    }

    private static Task InsertPictureAtAsync(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top)
    {
        dynamic picture = slide.Shapes.AddPicture(image.Path, MsoFalse, MsoTrue, left, top, image.WidthPoints, image.HeightPoints);
        PowerPointFormulaMetadataStore.ApplyToShape(picture, metadata);
        return Task.CompletedTask;
    }

    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic shape = GetSelectedShape();
        return Task.FromResult(ReadMetadataFromShape(shape));
    }

    public (float Left, float Top) GetSelectedShapePosition()
    {
        dynamic shape = GetSelectedShape();
        try
        {
            return ((float)shape.Left, (float)shape.Top);
        }
        catch
        {
            return (DefaultLeftPoints, DefaultTopPoints);
        }
    }

    public Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic shape = GetSelectedShape();
        CleanupImageFile(shape);
        shape.Delete();
        return Task.CompletedTask;
    }

    private dynamic GetSelectedShape()
    {
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

            dynamic shape = shapeRange[1];
            string equationId = ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag);
            if (string.IsNullOrWhiteSpace(equationId))
            {
                throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
            }

            return shape;
        }
        catch (InvalidOperationException)
        {
            throw;
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"), exc);
        }
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
        string numberingModeText = ReadTag(shape, PowerPointFormulaMetadataStore.NumberingModeTag);
        string numberText = ReadTag(shape, PowerPointFormulaMetadataStore.NumberTextTag);
        string schemaVersionText = ReadTag(shape, PowerPointFormulaMetadataStore.SchemaVersionTag);

        FormulaDisplayMode displayMode = displayModeText == "Inline" ? FormulaDisplayMode.Inline : FormulaDisplayMode.Display;
        NumberingMode numberingMode = numberingModeText switch
        {
            "Automatic" => NumberingMode.Automatic,
            "Manual" => NumberingMode.Manual,
            _ => NumberingMode.None,
        };
        int schemaVersion = int.TryParse(schemaVersionText, out int version) ? version : 1;

        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", equationId),
            latex,
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Image,
            schemaVersion);
    }

    private static void CleanupImageFile(dynamic shape)
    {
        try
        {
            string equationId = ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag);
            if (string.IsNullOrWhiteSpace(equationId))
            {
                return;
            }

            string tempRoot = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "LaTeXSnipper", "OfficePlugin", "PowerPoint");
            if (!System.IO.Directory.Exists(tempRoot))
            {
                return;
            }

            foreach (string file in System.IO.Directory.GetFiles(tempRoot, "*.png"))
            {
                string fileName = System.IO.Path.GetFileNameWithoutExtension(file);
                if (fileName.Contains(equationId))
                {
                    System.IO.File.Delete(file);
                }
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
