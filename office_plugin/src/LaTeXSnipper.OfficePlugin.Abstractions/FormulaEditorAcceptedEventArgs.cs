using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class FormulaEditorAcceptedEventArgs : EventArgs
{
    public FormulaEditorAcceptedEventArgs(
        FormulaMetadata? initialFormula,
        bool updateMode,
        string latex,
        bool display,
        FormulaFontStyle fontStyle)
    {
        InitialFormula = initialFormula;
        UpdateMode = updateMode;
        Latex = latex ?? string.Empty;
        Display = display;
        FontStyle = fontStyle;
    }

    public FormulaMetadata? InitialFormula { get; }

    public bool UpdateMode { get; }

    public string Latex { get; }

    public bool Display { get; }

    public FormulaFontStyle FontStyle { get; }
}
