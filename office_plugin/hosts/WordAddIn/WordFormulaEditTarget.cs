using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaEditTarget
{
    internal WordFormulaEditTarget(
        object document,
        object formulaObject,
        int windowHandle,
        FormulaMetadata metadata,
        bool isOle)
    {
        Document = document ?? throw new ArgumentNullException(nameof(document));
        FormulaObject = formulaObject ?? throw new ArgumentNullException(nameof(formulaObject));
        WindowHandle = windowHandle;
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        IsOle = isOle;
    }

    internal object Document { get; }

    internal object FormulaObject { get; }

    public int WindowHandle { get; }

    public FormulaMetadata Metadata { get; }

    public bool IsOle { get; }
}
