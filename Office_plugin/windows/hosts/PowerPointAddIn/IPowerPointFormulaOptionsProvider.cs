namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointFormulaOptionsProvider
{
    string CurrentLatex { get; }

    void ResetFormulaDraft();
}
