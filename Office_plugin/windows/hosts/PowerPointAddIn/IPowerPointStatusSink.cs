namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointStatusSink
{
    void Post(PowerPointStatusKind kind, string message);

    void SetBusy(bool busy);

    void SetOcrActive(bool active);

    void SetCurrentFormula(string latex, bool updateMode);
}
