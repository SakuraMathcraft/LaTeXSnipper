namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordRenumberResult
{
    public WordRenumberResult(int renumberedCount, int skippedCount)
    {
        RenumberedCount = renumberedCount;
        SkippedCount = skippedCount;
    }

    public int RenumberedCount { get; }

    public int SkippedCount { get; }
}
