using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class DynamicPowerPointApplicationAdapter
{
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

    public Task<string> ReadMathTypeMathMlAsync(MathTypeFormulaTarget target, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic shape = FindMathTypeFormula(target);
            shape.OLEFormat.Activate();
            object server = shape.OLEFormat.Object;
            try { return MathTypeOleBridge.ReadAndCloseMathMl(server); }
            finally { if (Marshal.IsComObject(server)) Marshal.ReleaseComObject(server); }
        }, cancellationToken);

    public Task ReplaceMathTypeWithOleAsync(MathTypeFormulaTarget target, FormulaMetadata metadata,
        OlePresentationResult presentation, CancellationToken cancellationToken)
        => _officeThread.InvokeAsync(() =>
        {
            dynamic original = FindMathTypeFormula(target);
            float height = Convert.ToSingle(original.Height);
            float width = (float)(height * presentation.WidthPoints / presentation.HeightPoints);
            dynamic? converted = null;
            try
            {
                converted = CreateOleObjectAt(original.Parent, metadata, presentation,
                    Convert.ToSingle(original.Left), Convert.ToSingle(original.Top), width, height);
                original.Delete();
            }
            catch
            {
                if (converted != null) converted.Delete();
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

    public async Task ReplaceWithMathTypeAsync(PowerPointFormulaEditTarget target, string mathMl, CancellationToken cancellationToken)
    {
        object? replacement = null;
        float left = 0, top = 0, width = 0, height = 0;
        try
        {
            await _officeThread.InvokeAsync(() =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                dynamic original = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
                if (!OleFormulaContent.IsFormula((object)original))
                    throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
                MathTypeOleBridge.EnsureAvailable();
                dynamic slide = original.Parent;
                left = Convert.ToSingle(original.Left);
                top = Convert.ToSingle(original.Top);
                width = Convert.ToSingle(original.Width);
                height = Convert.ToSingle(original.Height);
                dynamic converted = slide.Shapes.AddOLEObject(
                        Left: original.Left, Top: original.Top, Width: original.Width, Height: original.Height,
                        ClassName: MathTypeOleBridge.ProgId, DisplayAsIcon: false, Link: false);
                replacement = converted;
                if (Convert.ToString(converted.OLEFormat.ProgID) != MathTypeOleBridge.ProgId)
                    throw new InvalidOperationException(PowerPointAddInText.Get("MathTypeNativeRequired"));
                object server = converted.OLEFormat.Object;
                try { MathTypeOleBridge.WriteMathMl(server, mathMl); }
                finally { if (Marshal.IsComObject(server)) Marshal.ReleaseComObject(server); }
                return true;
            }, cancellationToken).ConfigureAwait(false);

            // Wait until the native save has returned to Office before undoing
            // its width/height changes with the source object's dimensions.
            await _officeThread.InvokeAsync(() =>
            {
                dynamic converted = replacement!;
                dynamic original = FindFormulaShapeById(target.Presentation, target.Metadata.Identity.EquationId);
                converted.LockAspectRatio = 0;
                converted.Width = width;
                converted.Height = height;
                converted.Left = left;
                converted.Top = top;
                if (Math.Abs(Convert.ToSingle(converted.Width) - width) > 0.1f
                    || Math.Abs(Convert.ToSingle(converted.Height) - height) > 0.1f)
                    throw new InvalidOperationException("MathType 对象未能恢复转换前的宽度和高度。");
                converted.LockAspectRatio = -1;
                original.Delete();
                TryCom(() => converted.Select());
                return true;
            }, cancellationToken, defer: true).ConfigureAwait(false);
        }
        catch
        {
            if (replacement != null)
                await _officeThread.InvokeAsync(() =>
                {
                    dynamic converted = replacement;
                    converted.Delete();
                    return true;
                }, CancellationToken.None).ConfigureAwait(false);
            throw;
        }
    }

}
