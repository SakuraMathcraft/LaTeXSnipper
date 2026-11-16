namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public interface IWordStatusSink
{
    void Post(WordStatusKind kind, string message);

    void SetBusy(bool busy);

    void SetOcrActive(bool active);

    void SetCurrentFormula(string latex, bool updateMode);
}
