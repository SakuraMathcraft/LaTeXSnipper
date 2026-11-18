using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaEditTarget
{
    internal WordFormulaEditTarget(
        object document,
        object formulaObject,
        FormulaMetadata metadata,
        bool isOle,
        MathTypeFormulaTarget? mathType = null)
    {
        Document = document ?? throw new ArgumentNullException(nameof(document));
        FormulaObject = formulaObject ?? throw new ArgumentNullException(nameof(formulaObject));
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        IsOle = isOle;
        MathType = mathType;
    }

    internal object Document { get; }

    internal object FormulaObject { get; }

    public FormulaMetadata Metadata { get; }

    public bool IsOle { get; }

    internal MathTypeFormulaTarget? MathType { get; }
}
