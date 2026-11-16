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
}
