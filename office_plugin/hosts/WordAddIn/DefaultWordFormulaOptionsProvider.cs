using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class DefaultWordFormulaOptionsProvider : IWordFormulaOptionsProvider
{
    public static DefaultWordFormulaOptionsProvider Instance { get; } = new();

    public string CurrentLatex => "e^{i\\pi}+1=0";

    public WordFormulaOptions GetFormulaOptions()
    {
        return new WordFormulaOptions(display: true, NumberingMode.None, string.Empty);
    }

    public void ApplyFormulaMetadata(FormulaMetadata metadata, bool updateMode)
    {
    }

    public void ResetFormulaDraft()
    {
    }

    public void ShowFormulaPreview(int windowHandle, FormulaMetadata metadata)
    {
    }

    public void RestoreFormulaDraft(int windowHandle)
    {
    }
}
