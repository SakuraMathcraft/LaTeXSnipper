namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class NullWordStatusSink : IWordStatusSink
{
    public static readonly NullWordStatusSink Instance = new NullWordStatusSink();

    private NullWordStatusSink()
    {
    }

    public void Post(WordStatusKind kind, string message)
    {
    }

    public void SetBusy(bool busy)
    {
    }

    public void SetOcrActive(bool active)
    {
    }

    public void SetCurrentFormula(string latex, bool updateMode)
    {
    }
}
