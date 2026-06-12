using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEntry
{
    public PowerPointFormulaEntry(FormulaMetadata metadata, int slideIndex, float left, float top, float scale)
    {
        Metadata = metadata;
        SlideIndex = slideIndex;
        Left = left;
        Top = top;
        Scale = scale;
    }

    public FormulaMetadata Metadata { get; }

    public int SlideIndex { get; }

    public float Left { get; }

    public float Top { get; }

    public float Scale { get; }
}
