namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordRenumberResult
{
    public WordRenumberResult(int renumberedCount, int skippedMetadataCount, int skippedNumberingCount)
    {
        RenumberedCount = renumberedCount;
        SkippedMetadataCount = skippedMetadataCount;
        SkippedNumberingCount = skippedNumberingCount;
    }

    public int RenumberedCount { get; }

    public int SkippedMetadataCount { get; }

    public int SkippedNumberingCount { get; }

    public int SkippedCount => SkippedMetadataCount + SkippedNumberingCount;
}
