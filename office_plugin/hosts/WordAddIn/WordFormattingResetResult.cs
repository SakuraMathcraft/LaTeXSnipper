namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormattingResetResult
{
    public WordFormattingResetResult(int formulaCount, int resetCount)
    {
        FormulaCount = formulaCount;
        ResetCount = resetCount;
    }

    public int FormulaCount { get; }

    public int ResetCount { get; }
}
