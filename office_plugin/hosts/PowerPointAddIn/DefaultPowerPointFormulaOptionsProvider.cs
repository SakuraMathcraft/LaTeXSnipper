namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class DefaultPowerPointFormulaOptionsProvider : IPowerPointFormulaOptionsProvider
{
    public static readonly DefaultPowerPointFormulaOptionsProvider Instance = new DefaultPowerPointFormulaOptionsProvider();

    private DefaultPowerPointFormulaOptionsProvider()
    {
    }

    public string CurrentLatex => string.Empty;

    public void ResetFormulaDraft()
    {
    }

    public void ShowFormulaPreview(int windowHandle, string latex)
    {
    }

    public void RestoreFormulaDraft(int windowHandle)
    {
    }
}
