using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class FormulaEditorAcceptedEventArgs : EventArgs
{
    public FormulaEditorAcceptedEventArgs(
        FormulaMetadata initialFormula,
        bool updateMode,
        string latex,
        bool display,
        long sessionGeneration,
        FormulaTypography? typography = null)
    {
        InitialFormula = initialFormula ?? throw new ArgumentNullException(nameof(initialFormula));
        UpdateMode = updateMode;
        Latex = latex ?? string.Empty;
        Display = display;
        SessionGeneration = sessionGeneration;
        Typography = typography ?? initialFormula.Typography;
    }

    public FormulaMetadata InitialFormula { get; }

    public bool UpdateMode { get; }

    public string Latex { get; }

    public bool Display { get; }

    public long SessionGeneration { get; }

    public FormulaTypography Typography { get; }

}
