namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointFormulaOptionsProvider
{
    string CurrentLatex { get; }

    PowerPointFormulaOptions GetFormulaOptions();

    void ResetFormulaDraft();
}
