using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaEntry
{
    public WordFormulaEntry(int start, FormulaMetadata metadata)
    {
        Start = start;
        Metadata = metadata;
    }

    public int Start { get; }

    public FormulaMetadata Metadata { get; }
}
