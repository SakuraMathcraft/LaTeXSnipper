using System;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointTextInsertionTarget
{
    internal PowerPointTextInsertionTarget(object shape, string documentId, int slideId, int shapeId,
        int start, int textLength, string originalText, double fontSizePoints)
    {
        Shape = shape ?? throw new ArgumentNullException(nameof(shape));
        DocumentId = documentId;
        SlideId = slideId;
        ShapeId = shapeId;
        Start = start;
        TextLength = textLength;
        OriginalText = originalText;
        FontSizePoints = fontSizePoints;
    }

    internal object Shape { get; }
    internal string DocumentId { get; }
    internal int SlideId { get; }
    internal int ShapeId { get; }
    internal int Start { get; }
    internal int TextLength { get; }
    internal string OriginalText { get; }
    public double FontSizePoints { get; }
}
