using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class FormulaEditorAcceptedEventArgs : EventArgs
{
    public FormulaEditorAcceptedEventArgs(FormulaMetadata? initialFormula, bool updateMode, string latex)
    {
        InitialFormula = initialFormula;
        UpdateMode = updateMode;
        Latex = latex ?? string.Empty;
    }

    public FormulaMetadata? InitialFormula { get; }

    public bool UpdateMode { get; }

    public string Latex { get; }
}
