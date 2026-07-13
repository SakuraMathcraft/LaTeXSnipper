using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
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
    private const float FormulaSizeTolerancePoints = 0.1f;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _application;

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    public DynamicPowerPointApplicationAdapter(object application)
    {
        _application = application ?? throw new ArgumentNullException(nameof(application));
    }

    public Task ActivateForEditingAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        TryCom(() => _application.Activate());
        TryCom(() => _application.ActiveWindow.Activate());
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_application.ActiveWindow.HWND))));
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_application.HWND))));
        return Task.CompletedTask;
    }

    private static void TryCom(Action action)
    {
        try
        {
            action();
        }
        catch
        {
        }
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

    public Task InsertFormulaImageOnSlideAsync(
        int slideIndex,
        PowerPointRenderedImage image,
        FormulaMetadata metadata,
        float left,
        float top,
        float scale,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic slide = _application.ActivePresentation.Slides.Item(slideIndex);
        return InsertPictureAtAsync(
            slide,
            image,
            metadata,
            left,
            top,
            image.WidthPoints * scale,
            image.HeightPoints * scale);
    }

    public Task UpdateFormulaImageAsync(
        PowerPointFormulaEditTarget target,
        PowerPointRenderedImage image,
        FormulaMetadata metadata,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ValidateEditTarget(target, metadata);
        dynamic shape = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
        dynamic slide = shape.Parent;
        float left = Convert.ToSingle(shape.Left, System.Globalization.CultureInfo.InvariantCulture);
        float top = Convert.ToSingle(shape.Top, System.Globalization.CultureInfo.InvariantCulture);
        float scale = Convert.ToSingle(shape.Width, System.Globalization.CultureInfo.InvariantCulture)
            / ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
        string oldImagePath = ReadTag(shape, PowerPointFormulaMetadataStore.ImagePathTag);
        dynamic replacement = CreatePictureAt(
            slide,
            image,
            metadata,
            left,
            top,
            image.WidthPoints * scale,
            image.HeightPoints * scale);
        CommitReplacement(shape, replacement, oldImagePath);
        return Task.CompletedTask;
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

    public Task InsertOleFormulaObjectOnSlideAsync(
        int slideIndex,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        float left,
        float top,
        float shapeScale,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic slide = _application.ActivePresentation.Slides.Item(slideIndex);
        return InsertOleObjectAtAsync(
            slide,
            metadata,
            presentation,
            left,
            top,
            (float)presentation.WidthPoints * shapeScale,
            (float)presentation.HeightPoints * shapeScale);
    }

    public Task UpdateOleFormulaObjectAsync(
        PowerPointFormulaEditTarget target,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ValidateEditTarget(target, metadata);
        dynamic shape = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
        dynamic slide = shape.Parent;
        float left = Convert.ToSingle(shape.Left, System.Globalization.CultureInfo.InvariantCulture);
        float top = Convert.ToSingle(shape.Top, System.Globalization.CultureInfo.InvariantCulture);
        float scale = Convert.ToSingle(shape.Width, System.Globalization.CultureInfo.InvariantCulture)
            / ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
        string oldImagePath = ReadTag(shape, PowerPointFormulaMetadataStore.ImagePathTag);
        dynamic replacement = CreateOleObjectAt(
            slide,
            metadata,
            presentation,
            left,
            top,
            (float)presentation.WidthPoints * scale,
            (float)presentation.HeightPoints * scale);
        CommitReplacement(shape, replacement, oldImagePath);
        return Task.CompletedTask;
    }

    private static Task InsertPictureAtAsync(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top)
    {
        return InsertPictureAtAsync(slide, image, metadata, left, top, image.WidthPoints, image.HeightPoints);
    }

    private static Task InsertPictureAtAsync(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float width, float height)
    {
        CreatePictureAt(slide, image, metadata, left, top, width, height);
        return Task.CompletedTask;
    }

    public Task ActivateFormulaEditTargetAsync(
        PowerPointFormulaEditTarget target,
        CancellationToken cancellationToken)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        cancellationToken.ThrowIfCancellationRequested();
        dynamic window = target.Window;
        TryCom(() => _application.Activate());
        TryCom(() => window.Activate());
        TryCom(() => SetForegroundWindow(new IntPtr(target.WindowHandle)));
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_application.HWND))));
        return Task.CompletedTask;
    }

    public string GetCurrentDocumentId()
    {
        return PowerPointDocumentIdentityStore.GetOrCreate(_application.ActivePresentation);
    }

    private static dynamic CreatePictureAt(dynamic slide, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float width, float height)
    {
        dynamic picture = slide.Shapes.AddPicture(image.Path, MsoFalse, MsoTrue, left, top, width, height);
        try
        {
            PowerPointFormulaMetadataStore.ApplyImagePath(picture, image.Path);
            PowerPointFormulaMetadataStore.ApplyToShape(picture, metadata, image.WidthPoints, image.HeightPoints);
            return picture;
        }
        catch
        {
            CleanupImageFile(picture);
            TryDeleteShape(picture);
            throw;
        }
    }

    private static Task InsertOleObjectAtAsync(dynamic slide, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top)
    {
        return InsertOleObjectAtAsync(slide, metadata, presentation, left, top, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
    }

    private static Task InsertOleObjectAtAsync(dynamic slide, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float width, float height)
    {
        CreateOleObjectAt(slide, metadata, presentation, left, top, width, height);
        return Task.CompletedTask;
    }

    private static dynamic CreateOleObjectAt(dynamic slide, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float width, float height)
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
        try
        {
            PowerPointFormulaMetadataStore.ApplyToShape(shape, metadata, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
            return shape;
        }
        catch
        {
            TryDeleteShape(shape);
            throw;
        }
    }

    public Task<PowerPointFormulaEditTarget> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        object presentation = _application.ActivePresentation;
        object window = _application.ActiveWindow;
        object selection = ((dynamic)window).Selection;
        PowerPointFormulaEditTarget? target = TryCaptureFormulaEditTarget(presentation, window, selection);
        return Task.FromResult(target ?? throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired")));
    }

    public PowerPointFormulaEditTarget? TryCaptureFormulaEditTarget(
        object presentation,
        object window,
        object selection)
    {
        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        if (window == null)
        {
            throw new ArgumentNullException(nameof(window));
        }

        if (selection == null)
        {
            throw new ArgumentNullException(nameof(selection));
        }

        dynamic selected = selection;
        if (Convert.ToInt32(selected.Type) != 2)
        {
            return null;
        }

        dynamic shapeRange = selected.ShapeRange;
        if (Convert.ToInt32(shapeRange.Count) != 1)
        {
            return null;
        }

        dynamic shape = shapeRange.Item(1);
        if (string.IsNullOrWhiteSpace(ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag)))
        {
            return null;
        }

        EnsureUniqueShapeIdentity(shape, presentation);
        FormulaMetadata metadata = ReadMetadataFromShape(shape);
        bool isOle = IsFormulaOleShape(shape);
        if (isOle == (metadata.RenderEngine == RenderEngineKind.Image))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return new PowerPointFormulaEditTarget(
            metadata,
            presentation,
            window,
            shape,
            Convert.ToInt32(shape.Id),
            Convert.ToInt32(((dynamic)window).HWND),
            isOle);
    }

    public bool IsFormulaEditTargetValid(PowerPointFormulaEditTarget target)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        try
        {
            if (!string.Equals(
                PowerPointDocumentIdentityStore.GetOrCreate(target.Presentation),
                target.Metadata.Identity.DocumentId,
                StringComparison.Ordinal))
            {
                return false;
            }

            dynamic shape = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
            if (CountFormulaShapesById(target.Presentation, target.Metadata.Identity.EquationId) != 1
                || Convert.ToInt32(shape.Id) != target.ShapeId)
            {
                return false;
            }

            FormulaMetadata metadata = ReadMetadataFromShape(shape);
            return IsFormulaOleShape(shape) == target.IsOle
                && string.Equals(
                    metadata.Identity.DocumentId,
                    target.Metadata.Identity.DocumentId,
                    StringComparison.Ordinal)
                && string.Equals(
                    metadata.Identity.EquationId,
                    target.Metadata.Identity.EquationId,
                    StringComparison.Ordinal);
        }
        catch
        {
            return false;
        }
    }

    public Task<IReadOnlyList<PowerPointFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var entries = new List<PowerPointFormulaEntry>();
        IReadOnlyList<object> shapes = GetSelectedFormulaShapes();
        EnsureUniqueShapeIdentities(shapes);
        foreach (object item in shapes)
        {
            dynamic shape = item;
            entries.Add(CreateEntry(shape, Convert.ToInt32(shape.Parent.SlideIndex)));
        }

        return Task.FromResult<IReadOnlyList<PowerPointFormulaEntry>>(entries);
    }

    public bool ContainsFormula(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return false;
        }

        dynamic presentation = _application.ActivePresentation;
        int slideCount = Convert.ToInt32(presentation.Slides.Count);
        for (int slideIndex = 1; slideIndex <= slideCount; slideIndex++)
        {
            dynamic shapes = presentation.Slides.Item(slideIndex).Shapes;
            int shapeCount = Convert.ToInt32(shapes.Count);
            for (int shapeIndex = 1; shapeIndex <= shapeCount; shapeIndex++)
            {
                dynamic shape = shapes.Item(shapeIndex);
                if (string.Equals(
                    ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag),
                    equationId,
                    StringComparison.Ordinal))
                {
                    return true;
                }
            }
        }

        return false;
    }

    public Task<int> ResetCustomFormulaSizesAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        int resetCount = 0;
        dynamic presentation = _application.ActivePresentation;
        int slideCount = Convert.ToInt32(presentation.Slides.Count);
        for (int slideIndex = 1; slideIndex <= slideCount; slideIndex++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            dynamic shapes = presentation.Slides.Item(slideIndex).Shapes;
            int shapeCount = Convert.ToInt32(shapes.Count);
            for (int shapeIndex = 1; shapeIndex <= shapeCount; shapeIndex++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic shape = shapes.Item(shapeIndex);
                if (string.IsNullOrWhiteSpace(ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag)))
                {
                    continue;
                }

                float naturalWidth = ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
                float naturalHeight = ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalHeightPointsTag);
                float currentWidth = Convert.ToSingle(shape.Width, System.Globalization.CultureInfo.InvariantCulture);
                float currentHeight = Convert.ToSingle(shape.Height, System.Globalization.CultureInfo.InvariantCulture);
                if (Math.Abs(currentWidth - naturalWidth) <= FormulaSizeTolerancePoints
                    && Math.Abs(currentHeight - naturalHeight) <= FormulaSizeTolerancePoints)
                {
                    continue;
                }

                shape.Width = naturalWidth;
                shape.Height = naturalHeight;
                resetCount++;
            }
        }

        return Task.FromResult(resetCount);
    }

    public Task DeleteFormulaByIdAsync(string equationId, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic shape = FindFormulaShapeById(equationId);
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

    private void EnsureUniqueShapeIdentities(IEnumerable<object> shapes)
    {
        foreach (object item in shapes)
        {
            EnsureUniqueShapeIdentity(item);
        }
    }

    private void EnsureUniqueShapeIdentity(object shape)
    {
        EnsureUniqueShapeIdentity(shape, _application.ActivePresentation);
    }

    private static void EnsureUniqueShapeIdentity(object shape, object presentation)
    {
        dynamic formulaShape = shape;
        string documentId = PowerPointDocumentIdentityStore.GetOrCreate(presentation);
        string equationId = ReadTag(formulaShape, PowerPointFormulaMetadataStore.EquationIdTag);
        FormulaMetadata current = ReadMetadataFromShape(formulaShape);
        if (string.Equals(current.Identity.DocumentId, documentId, StringComparison.Ordinal)
            && CountFormulaShapesById(presentation, equationId) <= 1)
        {
            return;
        }

        FormulaMetadata metadata = WithNewIdentity(current, documentId);
        float naturalWidth = ReadRequiredFloatTag(formulaShape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
        float naturalHeight = ReadRequiredFloatTag(formulaShape, PowerPointFormulaMetadataStore.NaturalHeightPointsTag);
        PowerPointFormulaMetadataStore.ApplyToShape(formulaShape, metadata, naturalWidth, naturalHeight);
    }

    private int CountFormulaShapesById(string equationId)
    {
        return CountFormulaShapesById(_application.ActivePresentation, equationId);
    }

    private static int CountFormulaShapesById(object presentationObject, string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            return 0;
        }

        int count = 0;
        dynamic presentation = presentationObject;
        int slideCount = Convert.ToInt32(presentation.Slides.Count);
        for (int slideIndex = 1; slideIndex <= slideCount; slideIndex++)
        {
            dynamic shapes = presentation.Slides.Item(slideIndex).Shapes;
            int shapeCount = Convert.ToInt32(shapes.Count);
            for (int shapeIndex = 1; shapeIndex <= shapeCount; shapeIndex++)
            {
                dynamic shape = shapes.Item(shapeIndex);
                if (string.Equals(
                    ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag),
                    equationId,
                    StringComparison.Ordinal))
                {
                    count++;
                }
            }
        }

        return count;
    }

    private static bool IsFormulaOleShape(dynamic shape)
    {
        try
        {
            if (Convert.ToInt32(shape.Type) != 7)
            {
                return false;
            }

            string progId = Convert.ToString(shape.OLEFormat.ProgID) ?? string.Empty;
            return string.Equals(progId, OleFormulaProgId, StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static FormulaMetadata ReadMetadataFromShape(dynamic shape)
    {
        return PowerPointFormulaMetadataStore.LoadFromShape(shape);
    }

    private static FormulaMetadata WithNewIdentity(FormulaMetadata metadata, string documentId)
    {
        return new FormulaMetadata(
            new FormulaIdentity(documentId, Guid.NewGuid().ToString("N")),
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            metadata.RenderEngine,
            metadata.SchemaVersion,
            metadata.FontScale);
    }

    private static PowerPointFormulaEntry CreateEntry(dynamic shape, int slideIndex)
    {
        FormulaMetadata metadata = ReadMetadataFromShape(shape);
        float naturalWidth = ReadRequiredFloatTag(shape, PowerPointFormulaMetadataStore.NaturalWidthPointsTag);
        return new PowerPointFormulaEntry(
            metadata,
            slideIndex,
            Convert.ToSingle(shape.Left, System.Globalization.CultureInfo.InvariantCulture),
            Convert.ToSingle(shape.Top, System.Globalization.CultureInfo.InvariantCulture),
            Convert.ToSingle(shape.Width, System.Globalization.CultureInfo.InvariantCulture) / naturalWidth);
    }

    private dynamic FindFormulaShapeById(string equationId)
    {
        return FindFormulaShapeById(_application.ActivePresentation, equationId);
    }

    private static dynamic FindFormulaShapeById(object presentationObject, string equationId)
    {
        dynamic presentation = presentationObject;
        int slideCount = Convert.ToInt32(presentation.Slides.Count);
        for (int slideIndex = 1; slideIndex <= slideCount; slideIndex++)
        {
            dynamic shapes = presentation.Slides.Item(slideIndex).Shapes;
            int shapeCount = Convert.ToInt32(shapes.Count);
            for (int shapeIndex = 1; shapeIndex <= shapeCount; shapeIndex++)
            {
                dynamic shape = shapes.Item(shapeIndex);
                if (string.Equals(
                    ReadTag(shape, PowerPointFormulaMetadataStore.EquationIdTag),
                    equationId,
                    StringComparison.Ordinal))
                {
                    return shape;
                }
            }
        }

        throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
    }

    private void ValidateEditTarget(PowerPointFormulaEditTarget target, FormulaMetadata metadata)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (!IsFormulaEditTargetValid(target)
            || !string.Equals(
                target.Metadata.Identity.DocumentId,
                metadata.Identity.DocumentId,
                StringComparison.Ordinal)
            || !string.Equals(
                target.Metadata.Identity.EquationId,
                metadata.Identity.EquationId,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
        }
    }

    private static void CommitReplacement(dynamic original, dynamic replacement, string originalImagePath)
    {
        try
        {
            original.Delete();
        }
        catch
        {
            CleanupImageFile(replacement);
            TryDeleteShape(replacement);
            throw;
        }

        try
        {
            CleanupImageFilePath(originalImagePath);
        }
        catch
        {
        }
    }

    private static void TryDeleteShape(dynamic shape)
    {
        try
        {
            shape.Delete();
        }
        catch
        {
        }
    }

    private static void CleanupImageFile(dynamic shape)
    {
        try
        {
            CleanupImageFilePath(ReadTag(shape, PowerPointFormulaMetadataStore.ImagePathTag));
        }
        catch
        {
        }
    }

    private static void CleanupImageFilePath(string path)
    {
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
