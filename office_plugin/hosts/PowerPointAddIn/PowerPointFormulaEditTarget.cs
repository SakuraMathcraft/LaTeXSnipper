using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEditTarget
{
    internal PowerPointFormulaEditTarget(
        FormulaMetadata metadata,
        object presentation,
        object window,
        object shape,
        int shapeId,
        int windowHandle,
        bool isOle)
    {
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        Presentation = presentation ?? throw new ArgumentNullException(nameof(presentation));
        Window = window ?? throw new ArgumentNullException(nameof(window));
        Shape = shape ?? throw new ArgumentNullException(nameof(shape));
        ShapeId = shapeId;
        WindowHandle = windowHandle;
        IsOle = isOle;
    }

    public FormulaMetadata Metadata { get; }

    internal object Presentation { get; }

    internal object Window { get; }

    internal object Shape { get; }

    public int ShapeId { get; }

    public int WindowHandle { get; }

    public bool IsOle { get; }
}
