namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class NullPowerPointStatusSink : IPowerPointStatusSink
{
    public static readonly NullPowerPointStatusSink Instance = new NullPowerPointStatusSink();

    private NullPowerPointStatusSink()
    {
    }

    public void Post(PowerPointStatusKind kind, string message)
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
