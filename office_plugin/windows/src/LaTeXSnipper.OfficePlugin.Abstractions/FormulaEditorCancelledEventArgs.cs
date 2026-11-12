using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class FormulaEditorCancelledEventArgs : EventArgs
{
    public FormulaEditorCancelledEventArgs(long sessionGeneration)
    {
        SessionGeneration = sessionGeneration;
    }

    public long SessionGeneration { get; }
}
