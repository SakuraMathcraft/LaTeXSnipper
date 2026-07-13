using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class FormulaEditorAcceptedEventArgs : EventArgs
{
    public FormulaEditorAcceptedEventArgs(
        FormulaMetadata initialFormula,
        bool updateMode,
        string latex,
        bool display)
    {
        InitialFormula = initialFormula ?? throw new ArgumentNullException(nameof(initialFormula));
        UpdateMode = updateMode;
        Latex = latex ?? string.Empty;
        Display = display;
    }

    public FormulaMetadata InitialFormula { get; }

    public bool UpdateMode { get; }

    public string Latex { get; }

    public bool Display { get; }

}
