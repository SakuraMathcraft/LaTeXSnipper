using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEntry
{
    public PowerPointFormulaEntry(MathTypeFormulaTarget target, int slideIndex)
    {
        MathTypeTarget = target;
        SlideIndex = slideIndex;
    }

    public MathTypeFormulaTarget? MathTypeTarget { get; }
    private readonly FormulaMetadata? _metadata;
    public PowerPointFormulaEntry(FormulaMetadata metadata, int slideIndex, float left, float top, float scale)
    {
        _metadata = metadata;
        SlideIndex = slideIndex;
        Left = left;
        Top = top;
        Scale = scale;
    }

    public FormulaMetadata Metadata => _metadata ?? throw new System.InvalidOperationException("MathType 内容尚未读取。");

    public int SlideIndex { get; }

    public float Left { get; }

    public float Top { get; }

    public float Scale { get; }
}
