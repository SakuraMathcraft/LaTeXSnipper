namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointFormulaOptionsProvider
{
    string CurrentLatex { get; }

    void ResetFormulaDraft();

    void ShowFormulaPreview(int windowHandle, string latex);

    void RestoreFormulaDraft(int windowHandle);
}
