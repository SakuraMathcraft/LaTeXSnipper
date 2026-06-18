using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaEntry
{
    public WordFormulaEntry(int start, FormulaMetadata metadata)
        : this(start, metadata, string.Empty, FormulaDisplayMode.Inline, false)
    {
    }

    public WordFormulaEntry(int start, string nativeMathMl, FormulaDisplayMode nativeDisplayMode)
        : this(start, null, nativeMathMl, nativeDisplayMode, true)
    {
    }

    private WordFormulaEntry(
        int start,
        FormulaMetadata? metadata,
        string nativeMathMl,
        FormulaDisplayMode nativeDisplayMode,
        bool isNativeWordFormula)
    {
        Start = start;
        Metadata = metadata;
        NativeMathMl = nativeMathMl ?? string.Empty;
        NativeDisplayMode = nativeDisplayMode;
        IsNativeWordFormula = isNativeWordFormula;
    }

    public int Start { get; }

    public FormulaMetadata? Metadata { get; }

    public string NativeMathMl { get; }

    public FormulaDisplayMode NativeDisplayMode { get; }

    public bool IsNativeWordFormula { get; }
}
