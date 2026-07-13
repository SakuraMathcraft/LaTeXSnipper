using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEditTarget
{
    internal PowerPointFormulaEditTarget(FormulaMetadata metadata, object presentation)
    {
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        Presentation = presentation ?? throw new ArgumentNullException(nameof(presentation));
    }

    public FormulaMetadata Metadata { get; }

    internal object Presentation { get; }
}
