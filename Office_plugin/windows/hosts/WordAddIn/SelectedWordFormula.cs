using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class SelectedWordFormula
{
    public SelectedWordFormula(object contentControl, FormulaMetadata metadata)
        : this(contentControl, metadata, isOleInlineShape: false)
    {
    }

    public SelectedWordFormula(object contentControl, FormulaMetadata metadata, bool isOleInlineShape)
    {
        ContentControl = contentControl;
        Metadata = metadata;
        IsOleInlineShape = isOleInlineShape;
    }

    public object ContentControl { get; }

    public FormulaMetadata Metadata { get; }

    public bool IsOleInlineShape { get; }
}
