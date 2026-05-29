using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class SelectedWordFormula
{
    public SelectedWordFormula(object contentControl, FormulaMetadata metadata)
    {
        ContentControl = contentControl;
        Metadata = metadata;
    }

    public object ContentControl { get; }

    public FormulaMetadata Metadata { get; }
}
