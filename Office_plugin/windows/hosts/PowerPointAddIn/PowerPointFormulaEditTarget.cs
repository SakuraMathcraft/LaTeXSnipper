using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEditTarget
{
    internal PowerPointFormulaEditTarget(FormulaMetadata metadata, object presentation, MathTypeFormulaTarget? mathType = null)
    {
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        Presentation = presentation ?? throw new ArgumentNullException(nameof(presentation));
        MathType = mathType;
    }

    public FormulaMetadata Metadata { get; }

    internal object Presentation { get; }

    internal MathTypeFormulaTarget? MathType { get; }
}
