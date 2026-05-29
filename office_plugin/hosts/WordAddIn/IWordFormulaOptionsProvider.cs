using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public interface IWordFormulaOptionsProvider
{
    string CurrentLatex { get; }

    WordFormulaOptions GetFormulaOptions();

    void ApplyFormulaMetadata(FormulaMetadata metadata, bool updateMode);

    void ResetFormulaDraft();
}
