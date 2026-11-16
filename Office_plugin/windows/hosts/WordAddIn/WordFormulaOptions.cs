using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaOptions
{
    public WordFormulaOptions(bool display, NumberingMode numberingMode, string manualNumber)
    {
        Display = display;
        NumberingMode = numberingMode;
        ManualNumber = manualNumber ?? string.Empty;
    }

    public bool Display { get; }

    public NumberingMode NumberingMode { get; }

    public string ManualNumber { get; }
}
